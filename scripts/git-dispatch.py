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
MAX_WORKERS = int(os.environ.get("DISPATCHER_MAX_WORKERS", "5"))
HEALTH_PORT = int(os.environ.get("DISPATCHER_HEALTH_PORT", "8080"))

# EC2 tags used to find worker instances
WORKER_TAG_KEY = "Role"
WORKER_TAG_VALUE = "worker"
PROJECT_TAG_KEY = "Project"
PROJECT_TAG_VALUE = "claude-portable"

# ── State ──────────────────────────────────────────────────────────────────────

_state_lock = threading.Lock()
_state = {
    "status": "starting",
    "last_poll": None,
    "pending_tasks": 0,
    "active_workers": 0,
    "active_branches": 0,
    "total_dispatches": 0,
    "last_error": None,
    "errors": 0,
    "uptime_start": time.time(),
}


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


def get_pending_tasks(repo_dir: str) -> list:
    """Read TODO.md and return list of unchecked tasks."""
    todo_path = os.path.join(repo_dir, "TODO.md")
    try:
        with open(todo_path, "r") as f:
            content = f.read()
    except FileNotFoundError:
        log.warning("TODO.md not found at %s", todo_path)
        return []

    tasks = []
    lines = content.splitlines()
    for i, line in enumerate(lines):
        # Match unchecked items: "- [ ] description"
        match = re.match(r"^\s*-\s+\[\s+\]\s+(.+)$", line)
        if match:
            description = match.group(1).strip()
            # Look for PR title on next line
            pr_title = None
            if i + 1 < len(lines):
                pr_match = re.match(r'^\s*-\s+PR title:\s*["\']?(.+?)["\']?\s*$', lines[i + 1])
                if pr_match:
                    pr_title = pr_match.group(1).strip()
            tasks.append({
                "line": i + 1,
                "description": description,
                "pr_title": pr_title,
            })
    return tasks


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
        for i in range(workers_to_launch):
            worker_name = f"worker-{int(time.time())}-{i}"
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


# ── Health endpoint ────────────────────────────────────────────────────────────

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/health", "/"):
            state = get_state()
            uptime_start = state.pop("uptime_start", time.time())
            state["uptime_seconds"] = int(time.time() - uptime_start)
            body = json.dumps(state, indent=2).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass  # suppress per-request noise


def start_health_server():
    server = HTTPServer(("0.0.0.0", HEALTH_PORT), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    log.info("Health endpoint listening on port %d", HEALTH_PORT)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Git-based dispatcher for claude-portable fleet")
    parser.add_argument("--repo-dir", default=REPO_DIR, help="Path to claude-portable repo")
    parser.add_argument("--interval", type=int, default=POLL_INTERVAL, help="Poll interval in seconds")
    parser.add_argument("--max-workers", type=int, default=MAX_WORKERS, help="Max concurrent workers")
    args = parser.parse_args()

    global POLL_INTERVAL, REPO_DIR, MAX_WORKERS
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

    start_health_server()
    dispatch_loop(region)


if __name__ == "__main__":
    main()
