#!/usr/bin/env python3
"""
git-dispatch.py -- git-based dispatcher for claude-portable fleet.

Polls TODO.md on main every POLL_INTERVAL seconds.
Launches new workers when unclaimed tasks exist and capacity allows.
Workers pick up tasks themselves via continuous-claude.sh.

Environment variables:
  TODO_POLL_INTERVAL        Seconds between git polls (default: 60)
  DISPATCHER_REPO_DIR       Path to claude-portable repo (default: /workspace/claude-portable)
  DISPATCHER_MAX_WORKERS    Max concurrent worker instances (default: 5)
  DISPATCHER_HEALTH_PORT    Health endpoint port (default: 8080)
  AWS_DEFAULT_REGION        AWS region (default: auto-detected from EC2 metadata)
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────

POLL_INTERVAL = int(os.environ.get("TODO_POLL_INTERVAL", "60"))
REPO_DIR = os.environ.get("DISPATCHER_REPO_DIR", "/workspace/claude-portable")
HEALTH_PORT = int(os.environ.get("DISPATCHER_HEALTH_PORT", "8080"))

_DEFAULT_MAX_WORKERS = 5


def load_ccc_config(repo_dir: str) -> dict:
    """Load ccc.config.json from repo_dir. Returns empty dict on any error."""
    config_path = os.path.join(repo_dir, "ccc.config.json")
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        log.debug("ccc.config.json not found at %s", config_path)
        return {}
    except json.JSONDecodeError as e:
        log.warning("ccc.config.json parse error: %s", e)
        return {}
    except Exception as e:
        log.warning("Could not load ccc.config.json: %s", e)
        return {}


def get_max_workers(repo_dir: str) -> int:
    """Return max worker cap.

    Priority (highest first):
    1. DISPATCHER_MAX_WORKERS env var
    2. max_workers in ccc.config.json
    3. max_instances in ccc.config.json (legacy key used by ccc launcher)
    4. Built-in default (5)
    """
    env_val = os.environ.get("DISPATCHER_MAX_WORKERS")
    if env_val:
        try:
            return int(env_val)
        except ValueError:
            log.warning("Invalid DISPATCHER_MAX_WORKERS=%r, ignoring", env_val)

    cfg = load_ccc_config(repo_dir)
    for key in ("max_workers", "max_instances"):
        val = cfg.get(key)
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                log.warning("Invalid %s=%r in ccc.config.json, ignoring", key, val)

    return _DEFAULT_MAX_WORKERS


MAX_WORKERS = get_max_workers(REPO_DIR)

# EC2 tags used to find worker instances
WORKER_TAG_KEY = "Role"
WORKER_TAG_VALUE = "worker"
PROJECT_TAG_KEY = "Project"
PROJECT_TAG_VALUE = "claude-portable"

# How long a launched worker has to register before being terminated (seconds)
REGISTRATION_TIMEOUT = int(os.environ.get("WORKER_REGISTRATION_TIMEOUT", "300"))  # 5 minutes

# ── State ──────────────────────────────────────────────────────────────────────

_state_lock = threading.Lock()
_state = {
    "status": "starting",
    "last_poll": None,
    "pending_tasks": 0,
    "active_workers": 0,
    "active_branches": 0,
    "total_dispatches": 0,
    "total_completions": 0,
    "last_error": None,
    "errors": 0,
    "uptime_start": time.time(),
}

# worker_id -> {status, last_task, last_report, completions, registered, registered_at, ip, role, capabilities}
_fleet_roster: dict = {}
_fleet_roster_lock = threading.Lock()

# Workers launched by the dispatcher but not yet registered.
# worker_name -> {launched_at: float}
_launched_workers: dict = {}
_launched_workers_lock = threading.Lock()


def update_state(**kwargs):
    with _state_lock:
        _state.update(kwargs)


def get_state():
    with _state_lock:
        return dict(_state)


# ── Git helpers ────────────────────────────────────────────────────────────────

def git_pull(repo_dir: str) -> bool:
    """Pull latest main branch. Returns True on success."""
    try:
        result = subprocess.run(
            ["git", "pull", "--rebase", "origin", "main"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            log.debug("git pull succeeded: %s", result.stdout.strip())
            return True
        else:
            log.warning("git pull failed: %s", result.stderr.strip())
            return False
    except subprocess.TimeoutExpired:
        log.warning("git pull timed out")
        return False
    except Exception as e:
        log.warning("git pull error: %s", e)
        return False


def _parse_all_tasks(content: str) -> tuple[list, set]:
    """Parse TODO.md content into (all_tasks, completed_lines).

    Returns:
      all_tasks: list of dicts with line, description, checked, pr_title, depends_on
      completed_lines: set of line numbers for checked tasks (for dependency resolution)
    """
    tasks = []
    completed_lines: set[int] = set()
    lines = content.splitlines()

    for i, line in enumerate(lines):
        # Match checked items: "- [x] description"
        checked_match = re.match(r"^\s*-\s+\[x\]\s+(.+)$", line, re.IGNORECASE)
        # Match unchecked items: "- [ ] description"
        unchecked_match = re.match(r"^\s*-\s+\[\s+\]\s+(.+)$", line)

        match = checked_match or unchecked_match
        if not match:
            continue

        is_checked = checked_match is not None
        description = match.group(1).strip()
        line_num = i + 1

        if is_checked:
            completed_lines.add(line_num)

        # Scan indented sub-lines for metadata
        pr_title = None
        depends_on: list[int] = []
        j = i + 1
        while j < len(lines):
            sub = lines[j]
            # Stop at next task item or blank line followed by non-indented content
            if re.match(r"^\s*-\s+\[", sub):
                break
            if not sub.strip():
                j += 1
                continue
            # Not indented = end of sub-lines
            if not sub.startswith(" ") and not sub.startswith("\t"):
                break

            pr_match = re.match(r'^\s*-\s+PR title:\s*["\']?(.+?)["\']?\s*$', sub)
            if pr_match:
                pr_title = pr_match.group(1).strip()

            dep_match = re.match(r'^\s*-\s+depends-on:\s*(.+)$', sub, re.IGNORECASE)
            if dep_match:
                # Parse comma-separated line numbers or task-N references
                for ref in re.split(r'[,\s]+', dep_match.group(1)):
                    ref = ref.strip()
                    # "task-5" or "line-5" or just "5"
                    num_match = re.search(r'(\d+)', ref)
                    if num_match:
                        depends_on.append(int(num_match.group(1)))

            j += 1

        tasks.append({
            "line": line_num,
            "description": description,
            "checked": is_checked,
            "pr_title": pr_title,
            "depends_on": depends_on,
        })

    return tasks, completed_lines


def get_pending_tasks(repo_dir: str) -> list:
    """Read TODO.md and return list of unchecked tasks with dependency info."""
    todo_path = os.path.join(repo_dir, "TODO.md")
    try:
        with open(todo_path, "r") as f:
            content = f.read()
    except FileNotFoundError:
        log.warning("TODO.md not found at %s", todo_path)
        return []

    all_tasks, completed_lines = _parse_all_tasks(content)

    pending = []
    for task in all_tasks:
        if task["checked"]:
            continue
        # Check if all dependencies are satisfied (their line is in completed_lines)
        unmet = [d for d in task["depends_on"] if d not in completed_lines]
        pending.append({
            "line": task["line"],
            "description": task["description"],
            "pr_title": task["pr_title"],
            "area": route_task_to_area(task["description"]),
            "depends_on": task["depends_on"],
            "blocked_by": unmet,
            "blocked": len(unmet) > 0,
        })
    return pending


# ── Task routing by app area ─────────────────────────────────────────────────

AREA_KEYWORDS = {
    "dispatcher": [
        "dispatch", "dispatcher", "git-dispatch", "relay", "poll",
        "leader election", "heartbeat", "standby", "primary",
    ],
    "fleet": [
        "fleet", "ccc", "launcher", "ec2", "instance", "scale",
        "worker", "idle", "monitor", "maintenance", "ssh key",
    ],
    "teams-integration": [
        "teams", "rone", "chatbot", "web-chat", "web chat", "lambda",
        "graph api", "teams-chat", "bridge", "phone",
    ],
    "tdd-pipeline": [
        "tdd", "pipeline", "test", "continuous-claude", "stage",
        "research", "plan", "implement", "verify", "gate",
    ],
    "infrastructure": [
        "docker", "dockerfile", "bootstrap", "container", "credential",
        "secret", "s3", "state-sync", "browser", "chrome", "vnc",
        "session", "component", "install",
    ],
}


def route_task_to_area(description: str) -> str | None:
    """Match a task description to an app area by keyword. Returns area name or None."""
    desc_lower = description.lower()
    scores: dict[str, int] = {}
    for area, keywords in AREA_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in desc_lower)
        if score > 0:
            scores[area] = score
    if not scores:
        return None
    return max(scores, key=scores.get)


def get_area_context(repo_dir: str, area: str) -> str:
    """Read the CONTEXT.md for an area. Returns content or empty string."""
    path = os.path.join(repo_dir, "areas", area, "CONTEXT.md")
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def pick_worker_for_area(area: str | None) -> tuple[str, str]:
    """Pick the best idle worker for a task area. Returns (worker_name, worker_ip).

    Prefers workers whose last_area matches the requested area (area affinity).
    Falls back to any idle worker if no affinity match exists.
    Returns ("", "") if no idle worker is available.
    """
    with _fleet_roster_lock:
        affinity_match = None
        any_idle = None
        for wid, winfo in _fleet_roster.items():
            if winfo.get("status") != "idle" or not winfo.get("ip"):
                continue
            if any_idle is None:
                any_idle = (wid, winfo)
            if area and winfo.get("last_area") == area:
                affinity_match = (wid, winfo)
                break  # perfect match, stop looking

        chosen = affinity_match or any_idle
        if chosen:
            wid, winfo = chosen
            winfo["status"] = "busy"
            return (wid, winfo["ip"])
        return ("", "")


def get_active_worker_branches(repo_dir: str) -> list:
    """Return list of active continuous-claude/* remote branches."""
    try:
        # Fetch remote refs so we see current branches
        subprocess.run(
            ["git", "fetch", "--prune", "origin"],
            cwd=repo_dir,
            capture_output=True,
            timeout=30,
        )
        result = subprocess.run(
            ["git", "branch", "-r"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            log.warning("git branch -r failed: %s", result.stderr.strip())
            return []
        branches = []
        for line in result.stdout.splitlines():
            branch = line.strip()
            if "continuous-claude/" in branch:
                branches.append(branch)
        return branches
    except Exception as e:
        log.warning("Error listing branches: %s", e)
        return []


# ── EC2 helpers ────────────────────────────────────────────────────────────────

def get_own_private_ip() -> str:
    """Return this instance's private IP via IMDSv2, or empty string if unavailable."""
    try:
        token_result = subprocess.run(
            ["curl", "-s", "-X", "PUT",
             "http://169.254.169.254/latest/api/token",
             "-H", "X-aws-ec2-metadata-token-ttl-seconds: 21600",
             "--connect-timeout", "2"],
            capture_output=True, text=True, timeout=5,
        )
        if token_result.returncode == 0 and token_result.stdout:
            token = token_result.stdout.strip()
            ip_result = subprocess.run(
                ["curl", "-s",
                 "-H", f"X-aws-ec2-metadata-token: {token}",
                 "http://169.254.169.254/latest/meta-data/local-ipv4",
                 "--connect-timeout", "2"],
                capture_output=True, text=True, timeout=5,
            )
            if ip_result.returncode == 0 and ip_result.stdout.strip():
                return ip_result.stdout.strip()
    except Exception:
        pass
    return ""


def ensure_dispatcher_url_in_env(repo_dir: str, dispatcher_url: str) -> None:
    """Write DISPATCHER_URL to the .env file in repo_dir so workers launched via ccc
    will automatically receive it and know where to register.

    If the key already exists with the correct value, the file is left unchanged.
    If it exists with a different value, it is updated.
    If it is absent, it is appended.
    """
    env_path = os.path.join(repo_dir, ".env")
    key = "DISPATCHER_URL"
    new_line = f"{key}={dispatcher_url}\n"

    # Read existing file (ok if missing)
    try:
        with open(env_path, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = []

    updated = False
    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            if line.strip() == f"{key}={dispatcher_url}":
                # Already correct -- no-op
                log.debug("DISPATCHER_URL already set correctly in .env")
                return
            new_lines.append(new_line)
            updated = True
        else:
            new_lines.append(line)

    if not updated:
        new_lines.append(new_line)

    try:
        with open(env_path, "w") as f:
            f.writelines(new_lines)
        log.info("Set %s=%s in %s", key, dispatcher_url, env_path)
    except Exception as e:
        log.warning("Could not write DISPATCHER_URL to %s: %s", env_path, e)


def get_aws_region() -> str:
    """Get current AWS region from instance metadata or env."""
    region = os.environ.get("AWS_DEFAULT_REGION", "")
    if region:
        return region
    try:
        # IMDSv2: get token first
        token_result = subprocess.run(
            ["curl", "-s", "-X", "PUT",
             "http://169.254.169.254/latest/api/token",
             "-H", "X-aws-ec2-metadata-token-ttl-seconds: 21600",
             "--connect-timeout", "2"],
            capture_output=True, text=True, timeout=5
        )
        if token_result.returncode == 0 and token_result.stdout:
            token = token_result.stdout.strip()
            region_result = subprocess.run(
                ["curl", "-s",
                 "-H", f"X-aws-ec2-metadata-token: {token}",
                 "http://169.254.169.254/latest/meta-data/placement/region",
                 "--connect-timeout", "2"],
                capture_output=True, text=True, timeout=5
            )
            if region_result.returncode == 0 and region_result.stdout:
                return region_result.stdout.strip()
    except Exception:
        pass
    return "us-east-2"


def get_running_workers(region: str) -> list:
    """List running/pending EC2 worker instances."""
    try:
        result = subprocess.run(
            [
                "aws", "ec2", "describe-instances",
                "--filters",
                f"Name=tag:{WORKER_TAG_KEY},Values={WORKER_TAG_VALUE}",
                f"Name=tag:{PROJECT_TAG_KEY},Values={PROJECT_TAG_VALUE}",
                "Name=instance-state-name,Values=running,pending",
                "--query",
                "Reservations[].Instances[]."
                "{InstanceId:InstanceId,State:State.Name,LaunchTime:LaunchTime}",
                "--output", "json",
                "--region", region,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            log.warning("describe-instances failed: %s", result.stderr.strip())
            return []
    except Exception as e:
        log.warning("Error listing workers: %s", e)
        return []


def find_instance_id_by_name(worker_id: str, region: str) -> str | None:
    """Find EC2 instance ID by Name tag or treat worker_id as instance ID directly."""
    # If it already looks like an instance ID, use it directly
    if re.match(r"^i-[0-9a-f]{8,17}$", worker_id):
        return worker_id

    # Look up by Name tag
    try:
        result = subprocess.run(
            [
                "aws", "ec2", "describe-instances",
                "--filters",
                f"Name=tag:Name,Values={worker_id}",
                f"Name=tag:{PROJECT_TAG_KEY},Values={PROJECT_TAG_VALUE}",
                "Name=instance-state-name,Values=running,pending",
                "--query", "Reservations[0].Instances[0].InstanceId",
                "--output", "text",
                "--region", region,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode == 0:
            instance_id = result.stdout.strip()
            if instance_id and instance_id != "None":
                return instance_id
    except Exception as e:
        log.warning("find_instance_id_by_name error: %s", e)
    return None


def stop_worker_instance(worker_id: str, region: str) -> bool:
    """Stop an EC2 worker instance. Returns True if stop command succeeded."""
    instance_id = find_instance_id_by_name(worker_id, region)
    if not instance_id:
        log.warning("stop_worker_instance: no instance found for worker_id=%s", worker_id)
        return False

    log.info("Stopping worker instance: worker_id=%s instance_id=%s", worker_id, instance_id)
    try:
        result = subprocess.run(
            [
                "aws", "ec2", "stop-instances",
                "--instance-ids", instance_id,
                "--region", region,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            log.info("stop-instances succeeded for %s (%s)", worker_id, instance_id)
            return True
        else:
            log.warning("stop-instances failed for %s: %s", worker_id, result.stderr.strip())
            return False
    except Exception as e:
        log.warning("stop_worker_instance error for %s: %s", worker_id, e)
        return False


def get_next_worker_name(running_workers: list) -> str:
    """Generate a non-colliding worker name.

    Finds the highest numeric suffix among existing worker-N instances and
    returns worker-(N+1). Falls back to a timestamp-based name if no
    numeric suffixes exist.
    """
    max_n = 0
    for inst in running_workers:
        tags = inst.get("Tags") or []
        for tag in tags:
            if tag.get("Key") == "Name":
                name = tag.get("Value", "")
                parts = name.split("-")
                if len(parts) >= 2 and parts[0] == "worker":
                    try:
                        max_n = max(max_n, int(parts[-1]))
                    except ValueError:
                        pass
    if max_n > 0:
        return f"worker-{max_n + 1}"
    # No numeric names found -- use timestamp to avoid collisions
    return f"worker-{int(time.time())}"


def launch_worker(region: str, worker_name: str) -> bool:
    """Launch a new worker EC2 instance using ccc launcher."""
    log.info("Launching new worker: %s", worker_name)
    try:
        result = subprocess.run(
            ["ccc", "--name", worker_name, "--new"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            log.info("Worker %s launched successfully", worker_name)
            with _launched_workers_lock:
                _launched_workers[worker_name] = {"launched_at": time.time()}
            return True
        else:
            log.warning("Worker launch failed for %s: %s", worker_name, result.stderr.strip())
            return False
    except FileNotFoundError:
        log.warning("ccc command not found -- cannot launch workers")
        return False
    except Exception as e:
        log.warning("Error launching worker %s: %s", worker_name, e)
        return False


# ── Dispatch logic ─────────────────────────────────────────────────────────────

def get_open_prs_for_worker(worker_id: str, repo_dir: str) -> list:
    """Return open PRs on continuous-claude/* branches for the given worker.

    Branch names don't encode worker IDs, so we check the fleet roster to see
    if this worker's last_task matches an open PR title.  If the roster has no
    last_task we fall back to returning ALL open continuous-claude/* PRs so we
    err on the side of caution (don't stop a worker that may still have work).
    """
    try:
        result = subprocess.run(
            [
                "gh", "pr", "list", "--state", "open",
                "--json", "number,title,headRefName",
            ],
            capture_output=True, text=True, timeout=30, cwd=repo_dir,
        )
        if result.returncode != 0:
            log.warning("get_open_prs_for_worker: gh pr list failed: %s", result.stderr.strip())
            return []
        all_prs = json.loads(result.stdout or "[]")
        # Only care about worker branches
        worker_prs = [
            pr for pr in all_prs
            if "continuous-claude/" in pr.get("headRefName", "")
        ]
        if not worker_prs:
            return []

        # Try to narrow to PRs belonging to this specific worker via fleet roster
        with _fleet_roster_lock:
            entry = _fleet_roster.get(worker_id, {})
        last_task = entry.get("last_task") or ""
        if last_task:
            # Match PRs whose title contains a significant substring of last_task
            matched = [
                pr for pr in worker_prs
                if last_task[:40].lower() in pr.get("title", "").lower()
                   or pr.get("title", "").lower() in last_task.lower()
            ]
            if matched:
                return matched

        # Can't narrow down -- return all open worker PRs as a safety measure
        return worker_prs
    except Exception as e:
        log.warning("get_open_prs_for_worker error: %s", e)
        return []


def count_unclaimed_tasks(pending_tasks: list, active_branches: list) -> int:
    """Estimate tasks not yet claimed by a worker branch.

    Uses the heuristic: unclaimed = pending tasks - active continuous-claude branches.
    Each active branch represents one task in progress.
    """
    return max(0, len(pending_tasks) - len(active_branches))


def dispatch_loop(region: str):
    """Main dispatch loop -- polls git, manages workers."""
    log.info("Dispatch loop started (interval: %ds, max_workers: %d)", POLL_INTERVAL, MAX_WORKERS)
    update_state(status="running")

    while True:
        try:
            _dispatch_tick(region)
        except Exception as e:
            log.error("Dispatch tick error: %s", e)
            with _state_lock:
                _state["last_error"] = str(e)
                _state["errors"] = _state.get("errors", 0) + 1
        time.sleep(POLL_INTERVAL)


def _dispatch_tick(region: str):
    """Single dispatch iteration."""
    if not is_primary():
        log.debug("Standby mode — skipping dispatch tick")
        return
    log.info("Polling git state...")

    # Pull latest git state
    pulled = git_pull(REPO_DIR)
    if not pulled:
        log.warning("git pull failed, continuing with cached state")

    # Read pending tasks and active branches
    pending_tasks = get_pending_tasks(REPO_DIR)
    active_branches = get_active_worker_branches(REPO_DIR)
    running_workers = get_running_workers(region)

    pending_count = len(pending_tasks)
    branch_count = len(active_branches)
    worker_count = len(running_workers)

    log.info(
        "State: pending_tasks=%d, active_branches=%d, running_workers=%d",
        pending_count, branch_count, worker_count,
    )

    update_state(
        last_poll=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        pending_tasks=pending_count,
        active_branches=branch_count,
        active_workers=worker_count,
    )

    # Scale up: launch workers for unclaimed tasks if capacity allows
    unclaimed = count_unclaimed_tasks(pending_tasks, active_branches)
    if unclaimed > 0 and worker_count < MAX_WORKERS:
        workers_to_launch = min(unclaimed, MAX_WORKERS - worker_count)
        log.info(
            "Scaling up: %d unclaimed tasks, %d/%d workers running -- launching %d worker(s)",
            unclaimed, worker_count, MAX_WORKERS, workers_to_launch,
        )
        launched = 0
        current_workers = list(running_workers)  # snapshot for name generation
        for i in range(workers_to_launch):
            worker_name = get_next_worker_name(current_workers)
            # Add a synthetic entry so the next iteration picks a different name
            current_workers.append({"Tags": [{"Key": "Name", "Value": worker_name}]})
            if launch_worker(region, worker_name):
                launched += 1
        if launched:
            with _state_lock:
                _state["total_dispatches"] = _state.get("total_dispatches", 0) + launched
    elif pending_count == 0:
        log.info("No pending tasks -- fleet at rest")
    else:
        log.info(
            "All tasks claimed or workers at capacity (%d/%d)",
            worker_count, MAX_WORKERS,
        )


# ── Registration monitor ───────────────────────────────────────────────────────

def registration_monitor_loop(region: str):
    """Background thread: terminate workers that fail to register within REGISTRATION_TIMEOUT."""
    log.info(
        "Registration monitor started (timeout: %ds, check interval: 30s)",
        REGISTRATION_TIMEOUT,
    )
    while True:
        time.sleep(30)
        now = time.time()
        with _launched_workers_lock:
            pending = dict(_launched_workers)

        for worker_name, info in pending.items():
            age = now - info["launched_at"]
            if age < REGISTRATION_TIMEOUT:
                continue

            # Check if this worker has registered
            with _fleet_roster_lock:
                entry = _fleet_roster.get(worker_name, {})
            if entry.get("registered"):
                # Registered -- remove from pending tracker
                with _launched_workers_lock:
                    _launched_workers.pop(worker_name, None)
                continue

            # Not registered within timeout -- terminate
            log.warning(
                "Worker %s has not registered within %ds (age=%ds) -- terminating",
                worker_name, REGISTRATION_TIMEOUT, int(age),
            )
            terminated = stop_worker_instance(worker_name, region)
            with _launched_workers_lock:
                _launched_workers.pop(worker_name, None)
            if terminated:
                log.info("Unregistered worker %s terminated successfully", worker_name)
            else:
                log.warning("Could not terminate unregistered worker %s", worker_name)


# ── Fleet monitor (safety net) ────────────────────────────────────────────────
#
# Catches workers that stop self-reporting. Primary scale-down is via worker
# self-report (/worker/idle). This is the backup in case self-reporting fails.

FLEET_MONITOR_INTERVAL = 60  # seconds between checks
FLEET_MONITOR_STALE_THRESHOLD = 35 * 60  # 35 minutes with no self-report


def _parse_iso_timestamp(ts: str) -> float:
    """Parse ISO 8601 timestamp to epoch seconds. Returns 0 on failure."""
    if not ts:
        return 0.0
    try:
        # Handle both Z and +00:00 suffixes
        ts = ts.replace("Z", "+00:00")
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(ts)
        return dt.timestamp()
    except Exception:
        return 0.0


def _ssh_check_claude_process(worker_ip: str, worker_name: str) -> bool | None:
    """SSH to worker, check if a Claude process is running.

    Returns True if active, False if idle, None if SSH failed (unreachable).
    """
    key_dir = os.path.expanduser("~/.ssh/ccc-keys")
    key_path = os.path.join(key_dir, f"{worker_name}.pem")
    if not os.path.isfile(key_path):
        short_name = worker_name.replace("ccc-", "")
        key_path = os.path.join(key_dir, f"{short_name}.pem")
    if not os.path.isfile(key_path):
        log.debug("Fleet monitor: no SSH key for %s", worker_name)
        return None

    try:
        r = subprocess.run([
            "ssh", "-o", "StrictHostKeyChecking=no", "-o", "LogLevel=ERROR",
            "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
            "-i", key_path, f"ubuntu@{worker_ip}",
            "docker exec claude-portable pgrep -f 'node.*claude' || echo IDLE",
        ], capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            return None  # SSH failed — unreachable
        output = r.stdout.strip()
        return output != "IDLE"
    except Exception:
        return None


def fleet_monitor_loop(region: str):
    """Background thread: safety net for workers that stop self-reporting."""
    log.info(
        "Fleet monitor started (interval: %ds, stale threshold: %ds)",
        FLEET_MONITOR_INTERVAL, FLEET_MONITOR_STALE_THRESHOLD,
    )
    while True:
        time.sleep(FLEET_MONITOR_INTERVAL)
        try:
            _fleet_monitor_tick(region)
        except Exception as e:
            log.error("Fleet monitor tick error: %s", e)


def _fleet_monitor_tick(region: str):
    """Single fleet monitor iteration."""
    now = time.time()

    with _fleet_roster_lock:
        roster_snapshot = {k: dict(v) for k, v in _fleet_roster.items()}

    for worker_id, info in roster_snapshot.items():
        if not info.get("registered"):
            continue
        if info.get("status") == "stopping":
            continue

        last_report_ts = _parse_iso_timestamp(info.get("last_report", ""))
        if last_report_ts == 0:
            continue  # never reported — registration monitor handles this

        age = now - last_report_ts
        if age < FLEET_MONITOR_STALE_THRESHOLD:
            continue  # still fresh

        worker_ip = info.get("ip", "")
        if not worker_ip:
            log.warning(
                "Fleet monitor: worker %s stale (%ds) but no IP — skipping",
                worker_id, int(age),
            )
            continue

        # Worker hasn't self-reported in 35+ min — SSH check for activity
        log.info(
            "Fleet monitor: worker %s stale (%ds since last report) — checking via SSH",
            worker_id, int(age),
        )
        has_process = _ssh_check_claude_process(worker_ip, worker_id)

        if has_process is True:
            log.info("Fleet monitor: worker %s is busy (active Claude process) — leaving alone", worker_id)
            continue
        elif has_process is None:
            log.warning("Fleet monitor: worker %s unreachable via SSH — will retry next tick", worker_id)
            continue

        # Worker is idle AND stale — stop it
        log.warning(
            "Fleet monitor: worker %s idle + stale (%ds) — issuing stop-instances",
            worker_id, int(age),
        )
        with _fleet_roster_lock:
            entry = _fleet_roster.get(worker_id)
            if entry:
                entry["status"] = "stopping"
                entry["stopped_by"] = "fleet-monitor"

        t = threading.Thread(
            target=stop_worker_instance,
            args=(worker_id, region),
            daemon=True,
            name=f"monitor-stop-{worker_id}",
        )
        t.start()


# ── Health endpoint ────────────────────────────────────────────────────────────

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/health", "/"):
            state = get_state()
            uptime_start = state.pop("uptime_start", time.time())
            state["uptime_seconds"] = int(time.time() - uptime_start)
            with _fleet_roster_lock:
                state["fleet_roster"] = dict(_fleet_roster)
            with _relay_stats_lock:
                state["relay"] = dict(_relay_stats)
            with _leader_state_lock:
                state["leader"] = dict(_leader_state)
            body = json.dumps(state, indent=2).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/relay/status":
            with _relay_stats_lock:
                stats = dict(_relay_stats)
            body = json.dumps(stats, indent=2).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body_bytes)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return

        if self.path == "/worker/register":
            worker_id = str(payload.get("worker_id", "unknown"))
            ip = str(payload.get("ip", ""))
            role = str(payload.get("role", "worker"))
            capabilities = payload.get("capabilities", [])
            if not isinstance(capabilities, list):
                capabilities = []

            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            with _fleet_roster_lock:
                entry = _fleet_roster.setdefault(worker_id, {
                    "status": "idle",
                    "last_task": None,
                    "last_report": None,
                    "completions": 0,
                })
                entry["registered"] = True
                entry["registered_at"] = now
                entry["ip"] = ip
                entry["role"] = role
                entry["capabilities"] = capabilities
                entry["last_report"] = now

            # Remove from pending-registration tracker if present
            with _launched_workers_lock:
                _launched_workers.pop(worker_id, None)

            log.info(
                "Worker registered: worker_id=%s ip=%s role=%s capabilities=%s",
                worker_id, ip, role, capabilities,
            )

            resp = json.dumps({
                "status": "ok",
                "worker_id": worker_id,
                "message": "registered",
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

        elif self.path == "/worker/done":
            worker_id = str(payload.get("worker_id", "unknown"))
            task = str(payload.get("task", ""))
            duration = payload.get("duration", 0)

            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            with _fleet_roster_lock:
                entry = _fleet_roster.setdefault(worker_id, {
                    "status": "idle",
                    "last_task": None,
                    "last_report": None,
                    "completions": 0,
                })
                entry["status"] = "idle"
                entry["last_task"] = task
                entry["last_area"] = route_task_to_area(task) if task else None
                entry["last_report"] = now
                entry["completions"] = entry.get("completions", 0) + 1

            with _state_lock:
                _state["total_completions"] = _state.get("total_completions", 0) + 1

            log.info(
                "Worker done: worker_id=%s task=%s duration=%ss (total completions: %d)",
                worker_id, task, duration, _state["total_completions"],
            )

            resp = json.dumps({"status": "ok", "worker_id": worker_id}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

        elif self.path == "/worker/idle":
            worker_id = str(payload.get("worker_id", "unknown"))
            idle_since = str(payload.get("idle_since", ""))

            # Check whether there are unclaimed tasks before stopping the worker.
            # If tasks are available the worker should stay up.
            pending_tasks = get_pending_tasks(REPO_DIR)
            active_branches = get_active_worker_branches(REPO_DIR)
            unclaimed = count_unclaimed_tasks(pending_tasks, active_branches)

            if unclaimed > 0:
                log.info(
                    "Worker idle report from %s ignored -- %d unclaimed task(s) available",
                    worker_id, unclaimed,
                )
                resp = json.dumps({
                    "status": "busy",
                    "worker_id": worker_id,
                    "message": f"{unclaimed} unclaimed task(s) pending -- stay up",
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
                return

            # Confirm the worker isn't mid-task by checking for open PRs it owns.
            # A worker with an open PR on a continuous-claude/* branch has uncommitted
            # work -- don't stop it yet.
            open_prs = get_open_prs_for_worker(worker_id, REPO_DIR)
            if open_prs:
                pr_summaries = ", ".join(
                    f"#{pr['number']} ({pr['headRefName']})" for pr in open_prs
                )
                log.info(
                    "Worker idle report from %s rejected -- %d open PR(s) still pending: %s",
                    worker_id, len(open_prs), pr_summaries,
                )
                resp = json.dumps({
                    "status": "busy",
                    "worker_id": worker_id,
                    "message": f"{len(open_prs)} open PR(s) not yet merged -- stay up",
                    "open_prs": [pr["number"] for pr in open_prs],
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)
                return

            # No unclaimed tasks and no open PRs -- safe to scale down.
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            log.info(
                "SCALE-DOWN: worker_id=%s idle_since=%s unclaimed_tasks=0 open_prs=0"
                " -- confirming stop-instances at %s",
                worker_id, idle_since, now,
            )

            with _fleet_roster_lock:
                entry = _fleet_roster.setdefault(worker_id, {
                    "status": "idle",
                    "last_task": None,
                    "last_report": None,
                    "completions": 0,
                })
                entry["status"] = "stopping"
                entry["last_report"] = now
                entry["idle_since"] = idle_since
                entry["scale_down_at"] = now

            # Send response before attempting stop so the worker receives it
            resp = json.dumps({
                "status": "stopping",
                "worker_id": worker_id,
                "message": "scale-down confirmed -- awaiting stop-instances",
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)

            # Issue stop asynchronously so we don't block the HTTP handler
            region = get_aws_region()
            t = threading.Thread(
                target=stop_worker_instance,
                args=(worker_id, region),
                daemon=True,
                name=f"stop-{worker_id}",
            )
            t.start()

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass  # suppress per-request noise


# ── Git relay (RONE ↔ CCC bridge) ───────────────────────────────────────────
#
# Polls a shared git repo (ccc-rone-bridge) for relay requests from RONE.
# See .claude/rules/git-relay-design.md for the full architecture.
#
# Repo layout:
#   requests/pending/     RONE writes here
#   requests/dispatched/  dispatcher moves here when worker picks up
#   requests/completed/   worker moves here when done
#   requests/failed/      on error

RELAY_REPO = os.environ.get(
    "RELAY_REPO_URL",
    "https://github.com/joel-ginsberg_tmemu/ccc-rone-bridge.git",
)
RELAY_DIR = os.environ.get("RELAY_REPO_DIR", "/data/relay-repo")
RELAY_POLL_INTERVAL = int(os.environ.get("RELAY_POLL_INTERVAL", "30"))

_relay_stats = {
    "last_poll": None,
    "pending": 0,
    "dispatched": 0,
    "completed": 0,
    "failed": 0,
    "errors": 0,
}
_relay_stats_lock = threading.Lock()


def _relay_git_pull() -> bool:
    """Clone or pull the relay repo. Returns True on success."""
    if not os.path.isdir(os.path.join(RELAY_DIR, ".git")):
        try:
            os.makedirs(os.path.dirname(RELAY_DIR), exist_ok=True)
            r = subprocess.run(
                ["git", "clone", "--depth", "1", RELAY_REPO, RELAY_DIR],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode != 0:
                log.warning("relay git clone failed: %s", r.stderr.strip())
                return False
            log.info("Relay repo cloned to %s", RELAY_DIR)
            return True
        except Exception as e:
            log.warning("relay git clone error: %s", e)
            return False
    try:
        # Abort any stuck rebase/merge from previous failed pull
        subprocess.run(["git", "rebase", "--abort"], cwd=RELAY_DIR,
                        capture_output=True, timeout=5)
        subprocess.run(["git", "merge", "--abort"], cwd=RELAY_DIR,
                        capture_output=True, timeout=5)
        # Fetch and try fast-forward first
        subprocess.run(["git", "fetch", "origin", "main"], cwd=RELAY_DIR,
                        capture_output=True, text=True, timeout=30)
        r = subprocess.run(
            ["git", "reset", "--hard", "origin/main"],
            cwd=RELAY_DIR, capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            log.warning("relay git reset failed: %s", r.stderr.strip())
            return False
        return True
    except Exception as e:
        log.warning("relay git pull error: %s", e)
        return False


def _relay_git_push(message: str) -> bool:
    """Stage all changes and push to relay repo.

    On conflict: stash local changes, reset to remote, pop stash, recommit, push.
    """
    def _run(cmd, **kwargs):
        return subprocess.run(cmd, cwd=RELAY_DIR, capture_output=True,
                              text=True, timeout=kwargs.get("timeout", 10))

    try:
        _run(["git", "add", "-A"])
        r = _run(["git", "commit", "-m", message])
        if r.returncode != 0 and "nothing to commit" not in r.stdout:
            log.warning("relay git commit failed: %s", r.stderr.strip())
            return False

        r = _run(["git", "push", "origin", "main"], timeout=30)
        if r.returncode == 0:
            return True

        # Push rejected (concurrent push). Reset to remote, reapply our file moves.
        log.info("relay push conflict, resetting to remote and reapplying...")
        # Undo our commit but keep changes in working tree
        _run(["git", "reset", "--soft", "HEAD~1"])
        # Stash our changes
        _run(["git", "stash"])
        # Fast-forward to remote
        _run(["git", "fetch", "origin", "main"], timeout=30)
        _run(["git", "reset", "--hard", "origin/main"])
        # Pop stash (our file moves) back
        r = _run(["git", "stash", "pop"])
        if r.returncode != 0:
            # Stash conflict — drop stash, log, and let next poll cycle retry
            _run(["git", "checkout", "--", "."])
            _run(["git", "stash", "drop"])
            log.warning("relay stash pop conflict, will retry next cycle")
            return False
        # Recommit and push
        _run(["git", "add", "-A"])
        r = _run(["git", "commit", "-m", message])
        if r.returncode != 0 and "nothing to commit" not in r.stdout:
            return False
        r = _run(["git", "push", "origin", "main"], timeout=30)
        if r.returncode != 0:
            log.warning("relay retry push failed: %s", r.stderr.strip())
            return False
        return True
    except Exception as e:
        log.warning("relay git push error: %s", e)
        return False


def _move_relay_file(request_id: str, from_dir: str, to_dir: str, extra_fields: dict = None):
    """Move a relay request JSON between directories, optionally adding fields."""
    src = os.path.join(RELAY_DIR, "requests", from_dir, f"{request_id}.json")
    dst_dir = os.path.join(RELAY_DIR, "requests", to_dir)
    dst = os.path.join(dst_dir, f"{request_id}.json")
    try:
        os.makedirs(dst_dir, exist_ok=True)
        with open(src, "r") as f:
            data = json.load(f)
        if extra_fields:
            data.update(extra_fields)
        with open(dst, "w") as f:
            json.dump(data, f, indent=2)
        os.remove(src)
        return data
    except Exception as e:
        log.warning("Failed to move relay %s from %s to %s: %s", request_id, from_dir, to_dir, e)
        return None


def _dispatch_relay_request(request_id: str, request_data: dict):
    """Dispatch a relay request to a worker via SSH + claude -p."""
    sender = request_data.get("sender", "unknown")
    text = request_data.get("text", "")
    context = request_data.get("context", [])

    # Find an idle worker, preferring area affinity
    area = route_task_to_area(text) if text else None
    worker_name, worker_ip = pick_worker_for_area(area)

    if not worker_name:
        log.warning("RELAY %s: no idle worker available", request_id)
        _move_relay_file(request_id, "dispatched", "pending",
                         {"error": "no idle worker", "retry_after": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        return

    # Build prompt from request data
    context_str = "\n".join(str(c) for c in context[-25:])
    prompt = f"Request from {sender}.\n"
    if context_str:
        prompt += f"\nRecent conversation:\n{context_str}\n"
    prompt += f"\n{text}"

    escaped = prompt.replace("'", "'\\''").replace('"', '\\"')
    result_file = f"/tmp/relay-result-{request_id}.txt"

    # Find SSH key
    key_dir = os.path.expanduser("~/.ssh/ccc-keys")
    key_path = os.path.join(key_dir, f"{worker_name}.pem")
    if not os.path.isfile(key_path):
        short_name = worker_name.replace("ccc-", "")
        key_path = os.path.join(key_dir, f"{short_name}.pem")
    if not os.path.isfile(key_path):
        log.error("RELAY %s: no SSH key for %s", request_id, worker_name)
        _move_relay_file(request_id, "dispatched", "failed",
                         {"error": f"no SSH key for {worker_name}"})
        _relay_git_push(f"relay: {request_id} failed (no SSH key)")
        return

    cmd = (
        f"docker exec -w /workspace/claude-portable claude-portable bash -c '"
        f"claude -p \"{escaped}\" --dangerously-skip-permissions "
        f"> {result_file} 2>&1 && cat {result_file}'"
    )

    try:
        r = subprocess.run([
            "ssh", "-o", "StrictHostKeyChecking=no", "-o", "LogLevel=ERROR",
            "-o", "ConnectTimeout=10",
            "-i", key_path, f"ubuntu@{worker_ip}", cmd,
        ], capture_output=True, text=True, timeout=300)

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if r.returncode == 0 and r.stdout.strip():
            _move_relay_file(request_id, "dispatched", "completed", {
                "result": r.stdout.strip()[:5000],
                "completed_at": now,
                "worker": worker_name,
            })
            _relay_git_push(f"relay: {request_id} completed by {worker_name}")
            with _relay_stats_lock:
                _relay_stats["completed"] += 1
            log.info("RELAY %s completed by %s", request_id, worker_name)
        else:
            error_msg = r.stderr[:500] if r.stderr else "empty response"
            _move_relay_file(request_id, "dispatched", "failed", {
                "error": error_msg,
                "worker": worker_name,
                "failed_at": now,
            })
            _relay_git_push(f"relay: {request_id} failed on {worker_name}")
            with _relay_stats_lock:
                _relay_stats["failed"] += 1
            log.warning("RELAY %s failed on %s: %s", request_id, worker_name, error_msg[:100])
    except subprocess.TimeoutExpired:
        _move_relay_file(request_id, "dispatched", "failed", {
            "error": "timeout (300s)",
            "worker": worker_name,
        })
        _relay_git_push(f"relay: {request_id} timed out on {worker_name}")
        with _relay_stats_lock:
            _relay_stats["failed"] += 1
        log.warning("RELAY %s timed out on %s", request_id, worker_name)
    except Exception as e:
        _move_relay_file(request_id, "dispatched", "failed", {
            "error": str(e),
            "worker": worker_name,
        })
        _relay_git_push(f"relay: {request_id} error on {worker_name}")
        with _relay_stats_lock:
            _relay_stats["failed"] += 1
        log.error("RELAY %s error: %s", request_id, e)
    finally:
        with _fleet_roster_lock:
            entry = _fleet_roster.get(worker_name)
            if entry and entry.get("status") == "busy":
                entry["status"] = "idle"


def relay_poll_loop():
    """Background thread: poll relay repo for pending requests, dispatch to workers."""
    log.info("Relay poll loop started (interval: %ds, repo: %s)", RELAY_POLL_INTERVAL, RELAY_REPO)

    while True:
        try:
            _relay_poll_tick()
        except Exception as e:
            log.error("Relay poll tick error: %s", e)
            with _relay_stats_lock:
                _relay_stats["errors"] += 1
        time.sleep(RELAY_POLL_INTERVAL)


def _relay_poll_tick():
    """Single relay poll iteration."""
    if not is_primary():
        return
    if not _relay_git_pull():
        return

    pending_dir = os.path.join(RELAY_DIR, "requests", "pending")
    if not os.path.isdir(pending_dir):
        return

    pending_files = [f for f in os.listdir(pending_dir) if f.endswith(".json")]
    with _relay_stats_lock:
        _relay_stats["last_poll"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _relay_stats["pending"] = len(pending_files)

    if not pending_files:
        return

    log.info("RELAY: %d pending request(s)", len(pending_files))

    for filename in pending_files:
        request_id = filename.replace(".json", "")
        filepath = os.path.join(pending_dir, filename)
        try:
            with open(filepath, "r") as f:
                request_data = json.load(f)
        except Exception as e:
            log.warning("RELAY: bad JSON in %s: %s", filename, e)
            continue

        # Move to dispatched/ before processing
        moved = _move_relay_file(request_id, "pending", "dispatched", {
            "worker": "",
            "dispatched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        if not moved:
            continue

        _relay_git_push(f"relay: dispatching {request_id}")
        with _relay_stats_lock:
            _relay_stats["dispatched"] += 1

        # Dispatch in background thread so we can process multiple requests
        t = threading.Thread(
            target=_dispatch_relay_request,
            args=(request_id, request_data),
            daemon=True,
            name=f"relay-{request_id}",
        )
        t.start()


def start_health_server():
    server = HTTPServer(("0.0.0.0", HEALTH_PORT), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    log.info("Health endpoint listening on port %d", HEALTH_PORT)


# ── Leader election (S3-based) ────────────────────────────────────────────────
#
# Multiple dispatchers can run. Only the primary actively dispatches tasks and
# polls the relay repo. Standby instances monitor the primary's heartbeat and
# promote themselves if it goes stale.
#
# Heartbeat file: s3://{bucket}/dispatcher-heartbeat/{instance_name}.json
# Contains: {instance_name, role, ip, timestamp, region}
#
# Election rule: the heartbeat with the most recent timestamp where role=primary
# wins. If no fresh primary heartbeat exists (>LEADER_STALE_THRESHOLD), any
# standby may promote itself.

LEADER_HEARTBEAT_INTERVAL = 30  # seconds between heartbeat writes
LEADER_STALE_THRESHOLD = 5 * 60  # 5 minutes = primary considered dead
LEADER_CHECK_INTERVAL = 30  # how often standby checks primary's heartbeat

_leader_state_lock = threading.Lock()
_leader_state = {
    "role": "standby",  # "primary" or "standby"
    "promoted_at": None,
    "demoted_at": None,
    "primary_instance": None,
    "last_heartbeat_write": None,
    "last_heartbeat_check": None,
}


def _get_s3_bucket() -> str:
    """Derive the S3 state bucket name."""
    bucket = os.environ.get("CLAUDE_PORTABLE_STATE_BUCKET", "")
    if bucket:
        return bucket
    try:
        r = subprocess.run(
            ["aws", "sts", "get-caller-identity", "--query", "Account", "--output", "text"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            return f"claude-portable-state-{r.stdout.strip()}"
    except Exception:
        pass
    return ""


def _get_instance_name() -> str:
    """Get this dispatcher's instance name from env or EC2 tags."""
    name = os.environ.get("DISPATCHER_NAME", "")
    if name:
        return name
    # Try EC2 Name tag via metadata
    try:
        token_r = subprocess.run(
            ["curl", "-s", "-X", "PUT",
             "http://169.254.169.254/latest/api/token",
             "-H", "X-aws-ec2-metadata-token-ttl-seconds: 21600",
             "--connect-timeout", "2"],
            capture_output=True, text=True, timeout=5,
        )
        if token_r.returncode != 0:
            return "dispatcher-unknown"
        token = token_r.stdout.strip()
        iid_r = subprocess.run(
            ["curl", "-s", "-H", f"X-aws-ec2-metadata-token: {token}",
             "http://169.254.169.254/latest/meta-data/instance-id",
             "--connect-timeout", "2"],
            capture_output=True, text=True, timeout=5,
        )
        return iid_r.stdout.strip() if iid_r.returncode == 0 else "dispatcher-unknown"
    except Exception:
        return "dispatcher-unknown"


def write_heartbeat(bucket: str, instance_name: str, role: str, ip: str, region: str) -> bool:
    """Write heartbeat JSON to S3."""
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    data = json.dumps({
        "instance_name": instance_name,
        "role": role,
        "ip": ip,
        "timestamp": now,
        "region": region,
    })
    key = f"dispatcher-heartbeat/{instance_name}.json"
    try:
        r = subprocess.run(
            ["aws", "s3", "cp", "-", f"s3://{bucket}/{key}",
             "--region", region, "--content-type", "application/json"],
            input=data, capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            with _leader_state_lock:
                _leader_state["last_heartbeat_write"] = now
            return True
        log.warning("Heartbeat write failed: %s", r.stderr.strip())
        return False
    except Exception as e:
        log.warning("Heartbeat write error: %s", e)
        return False


def read_all_heartbeats(bucket: str, region: str) -> list:
    """Read all dispatcher heartbeat files from S3."""
    prefix = "dispatcher-heartbeat/"
    try:
        r = subprocess.run(
            ["aws", "s3api", "list-objects-v2",
             "--bucket", bucket, "--prefix", prefix,
             "--query", "Contents[].Key", "--output", "json",
             "--region", region],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return []
        keys = json.loads(r.stdout)
        if not keys:
            return []

        heartbeats = []
        for key in keys:
            try:
                gr = subprocess.run(
                    ["aws", "s3", "cp", f"s3://{bucket}/{key}", "-",
                     "--region", region],
                    capture_output=True, text=True, timeout=10,
                )
                if gr.returncode == 0 and gr.stdout.strip():
                    heartbeats.append(json.loads(gr.stdout))
            except Exception:
                pass
        return heartbeats
    except Exception as e:
        log.warning("Failed to read heartbeats: %s", e)
        return []


def find_active_primary(heartbeats: list) -> dict | None:
    """Find a fresh primary heartbeat. Returns None if no active primary."""
    now = time.time()
    for hb in heartbeats:
        if hb.get("role") != "primary":
            continue
        ts = _parse_iso_timestamp(hb.get("timestamp", ""))
        if ts == 0:
            continue
        age = now - ts
        if age < LEADER_STALE_THRESHOLD:
            return hb
    return None


def is_primary() -> bool:
    with _leader_state_lock:
        return _leader_state["role"] == "primary"


def promote_to_primary(instance_name: str):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _leader_state_lock:
        _leader_state["role"] = "primary"
        _leader_state["promoted_at"] = now
        _leader_state["primary_instance"] = instance_name
    update_state(leader_role="primary")
    log.info("=== PROMOTED TO PRIMARY ===")


def demote_to_standby(primary_name: str):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with _leader_state_lock:
        _leader_state["role"] = "standby"
        _leader_state["demoted_at"] = now
        _leader_state["primary_instance"] = primary_name
    update_state(leader_role="standby")
    log.info("=== DEMOTED TO STANDBY (primary: %s) ===", primary_name)


def heartbeat_loop(bucket: str, instance_name: str, ip: str, region: str):
    """Background thread: write heartbeat to S3 every LEADER_HEARTBEAT_INTERVAL seconds."""
    while True:
        with _leader_state_lock:
            role = _leader_state["role"]
        write_heartbeat(bucket, instance_name, role, ip, region)
        time.sleep(LEADER_HEARTBEAT_INTERVAL)


def standby_monitor_loop(bucket: str, instance_name: str, region: str):
    """Background thread: when in standby, check if primary is alive.

    If primary heartbeat goes stale, promote self to primary.
    If we're primary and see a newer primary, demote to standby.
    """
    while True:
        time.sleep(LEADER_CHECK_INTERVAL)
        try:
            heartbeats = read_all_heartbeats(bucket, region)
            active_primary = find_active_primary(heartbeats)
            now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

            with _leader_state_lock:
                current_role = _leader_state["role"]
                _leader_state["last_heartbeat_check"] = now_str

            if current_role == "standby":
                if active_primary is None:
                    log.warning("No active primary found — promoting self")
                    promote_to_primary(instance_name)
                elif active_primary.get("instance_name") != instance_name:
                    with _leader_state_lock:
                        _leader_state["primary_instance"] = active_primary["instance_name"]
                    log.debug("Primary is %s — staying standby", active_primary["instance_name"])

            elif current_role == "primary":
                if active_primary and active_primary.get("instance_name") != instance_name:
                    # Another instance also claims primary with a fresher heartbeat
                    my_ts = _parse_iso_timestamp(
                        _leader_state.get("last_heartbeat_write", ""))
                    their_ts = _parse_iso_timestamp(
                        active_primary.get("timestamp", ""))
                    if their_ts > my_ts:
                        log.warning(
                            "Newer primary detected: %s — demoting self",
                            active_primary["instance_name"],
                        )
                        demote_to_standby(active_primary["instance_name"])

        except Exception as e:
            log.error("Standby monitor error: %s", e)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    global POLL_INTERVAL, REPO_DIR, MAX_WORKERS
    parser = argparse.ArgumentParser(description="Git-based dispatcher for claude-portable fleet")
    parser.add_argument("--repo-dir", default=REPO_DIR, help="Path to claude-portable repo")
    parser.add_argument("--interval", type=int, default=POLL_INTERVAL, help="Poll interval in seconds")
    parser.add_argument("--max-workers", type=int, default=MAX_WORKERS, help="Max concurrent workers")
    parser.add_argument("--standby", action="store_true",
                        help="Start in standby mode (monitor primary, promote if stale)")
    args = parser.parse_args()

    POLL_INTERVAL = args.interval
    REPO_DIR = args.repo_dir
    MAX_WORKERS = args.max_workers

    log.info("=== Git Dispatcher ===")
    log.info("  Repo:          %s", REPO_DIR)
    log.info("  Poll interval: %ds", POLL_INTERVAL)
    log.info("  Max workers:   %d", MAX_WORKERS)
    log.info("  Health port:   %d", HEALTH_PORT)

    region = get_aws_region()
    log.info("  AWS region:    %s", region)

    own_ip = os.environ.get("DISPATCHER_IP", "") or get_own_private_ip()
    if own_ip:
        dispatcher_url = f"http://{own_ip}:{HEALTH_PORT}"
        log.info("  Dispatcher URL: %s", dispatcher_url)
        ensure_dispatcher_url_in_env(REPO_DIR, dispatcher_url)
    else:
        log.warning("Could not determine own IP -- DISPATCHER_URL not injected into .env")
        log.warning("Workers will not be able to auto-register unless DISPATCHER_URL is set manually")

    # Leader election setup
    s3_bucket = _get_s3_bucket()
    instance_name = _get_instance_name()
    log.info("  Instance name: %s", instance_name)
    log.info("  S3 bucket:     %s", s3_bucket or "(none)")

    if s3_bucket:
        # Check if there's already an active primary
        if args.standby:
            log.info("  Starting in STANDBY mode (--standby flag)")
            with _leader_state_lock:
                _leader_state["role"] = "standby"
            update_state(leader_role="standby")
        else:
            heartbeats = read_all_heartbeats(s3_bucket, region)
            active_primary = find_active_primary(heartbeats)
            if active_primary and active_primary.get("instance_name") != instance_name:
                log.info(
                    "  Active primary found: %s — starting in STANDBY",
                    active_primary["instance_name"],
                )
                demote_to_standby(active_primary["instance_name"])
            else:
                promote_to_primary(instance_name)

        # Start heartbeat writer
        hb_thread = threading.Thread(
            target=heartbeat_loop,
            args=(s3_bucket, instance_name, own_ip or "", region),
            daemon=True,
            name="heartbeat-writer",
        )
        hb_thread.start()

        # Start standby monitor (checks primary liveness)
        sm_thread = threading.Thread(
            target=standby_monitor_loop,
            args=(s3_bucket, instance_name, region),
            daemon=True,
            name="standby-monitor",
        )
        sm_thread.start()
    else:
        log.warning("No S3 bucket — leader election disabled, running as primary")
        promote_to_primary(instance_name)

    start_health_server()

    reg_monitor = threading.Thread(
        target=registration_monitor_loop,
        args=(region,),
        daemon=True,
        name="registration-monitor",
    )
    reg_monitor.start()

    # Start fleet monitor (safety net for stale workers)
    fleet_monitor = threading.Thread(
        target=fleet_monitor_loop,
        args=(region,),
        daemon=True,
        name="fleet-monitor",
    )
    fleet_monitor.start()

    # Start git relay poller (RONE ↔ CCC bridge)
    relay_thread = threading.Thread(
        target=relay_poll_loop,
        daemon=True,
        name="relay-poller",
    )
    relay_thread.start()
    log.info("  Relay repo:    %s", RELAY_REPO)
    log.info("  Relay dir:     %s", RELAY_DIR)
    log.info("  Relay poll:    %ds", RELAY_POLL_INTERVAL)

    dispatch_loop(region)


if __name__ == "__main__":
    main()
