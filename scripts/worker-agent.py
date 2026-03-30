#!/usr/bin/env python3
"""
worker-agent.py -- Lightweight daemon that runs alongside Claude in the worker container.

Sends heartbeats to the dispatcher, detects progress via git log, and reports
task completion or failure.

Environment:
  DISPATCHER_IP        Dispatcher host (required, e.g. 10.0.1.5)
  DISPATCH_API_TOKEN   Bearer token for dispatcher auth (required)
  WORKER_ID            Worker identifier (default: hostname)
  HEARTBEAT_INTERVAL   Seconds between heartbeats (default: 30)
  WORKER_WORKDIR       Git working directory to monitor (default: /workspace/task)
  TASK_ID              Current task ID (set by bootstrap, updated at runtime)

Usage:
  python3 scripts/worker-agent.py &
"""

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DISPATCHER_IP = os.environ.get("DISPATCHER_IP", "")
API_TOKEN = os.environ.get("DISPATCH_API_TOKEN", "")
WORKER_ID = os.environ.get("WORKER_ID", "")
HEARTBEAT_INTERVAL = int(os.environ.get("HEARTBEAT_INTERVAL", "30"))
WORKDIR = os.environ.get("WORKER_WORKDIR", "/workspace/task")
TASK_ID = os.environ.get("TASK_ID", "")

_running = True


def _resolve_worker_id():
    if WORKER_ID:
        return WORKER_ID
    try:
        return os.uname().nodename
    except AttributeError:
        import socket
        return socket.gethostname()


RESOLVED_WORKER_ID = _resolve_worker_id()

# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git(*args, cwd=None):
    """Run a git command, return stdout or empty string on failure."""
    try:
        r = subprocess.run(
            ["git"] + list(args),
            cwd=cwd or WORKDIR,
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


_last_seen_commit = None


def _get_last_commit_time():
    """ISO timestamp of the most recent commit."""
    ts = _git("log", "-1", "--format=%aI")
    return ts or None


def _get_files_changed():
    """Number of files changed in the most recent commit."""
    out = _git("diff", "--name-only", "HEAD~1", "HEAD")
    if not out:
        return 0
    return len(out.splitlines())


def _detect_new_commit():
    """Return True if there's a new commit since last check."""
    global _last_seen_commit
    head = _git("rev-parse", "HEAD")
    if not head:
        return False
    if _last_seen_commit is None:
        _last_seen_commit = head
        return False
    if head != _last_seen_commit:
        _last_seen_commit = head
        return True
    return False


# ---------------------------------------------------------------------------
# Process detection
# ---------------------------------------------------------------------------

def _is_claude_alive():
    """Check if a Claude process is running."""
    try:
        r = subprocess.run(
            ["pgrep", "-f", "node.*claude"],
            capture_output=True, text=True, timeout=5,
        )
        return bool(r.stdout.strip())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _base_url():
    return f"http://{DISPATCHER_IP}:8080"


def _headers():
    h = {"Content-Type": "application/json"}
    if API_TOKEN:
        h["Authorization"] = f"Bearer {API_TOKEN}"
    return h


def _post(path, payload):
    """POST JSON to dispatcher. Returns (status_code, body) or (0, error)."""
    url = f"{_base_url()}{path}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode()
            return resp.status, body
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return 0, str(e)


# ---------------------------------------------------------------------------
# Task ID discovery
# ---------------------------------------------------------------------------

def _read_task_id():
    """Read task ID from env or /data/.task-id file."""
    if TASK_ID:
        return TASK_ID
    try:
        with open("/data/.task-id", "r") as f:
            return f.read().strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------

def send_heartbeat():
    """POST heartbeat to dispatcher."""
    task_id = _read_task_id()
    claude_alive = _is_claude_alive()
    payload = {
        "worker_id": RESOLVED_WORKER_ID,
        "status": "working" if claude_alive else "idle",
        "task_id": task_id or None,
        "last_commit_time": _get_last_commit_time(),
        "files_changed": _get_files_changed(),
        "claude_alive": claude_alive,
    }
    status, body = _post("/worker/heartbeat", payload)
    return status == 200


# ---------------------------------------------------------------------------
# Task completion / failure
# ---------------------------------------------------------------------------

def report_complete(task_id, summary=""):
    """POST task completion to dispatcher."""
    payload = {"worker_id": RESOLVED_WORKER_ID}
    if summary:
        payload["summary"] = summary
    status, body = _post(f"/task/{task_id}/complete", payload)
    return status == 200


def report_failure(task_id, reason=""):
    """POST task failure to dispatcher."""
    payload = {"worker_id": RESOLVED_WORKER_ID}
    if reason:
        payload["reason"] = reason
    status, body = _post(f"/task/{task_id}/fail", payload)
    return status == 200


# ---------------------------------------------------------------------------
# Completion detection
# ---------------------------------------------------------------------------

def _check_completion_marker():
    """Check if Claude left a completion or failure marker."""
    for path in ["/data/.task-complete", os.path.join(WORKDIR, ".task-complete")]:
        if os.path.isfile(path):
            try:
                with open(path, "r") as f:
                    summary = f.read().strip()
                os.remove(path)
                return "complete", summary
            except Exception:
                return "complete", ""

    for path in ["/data/.task-failed", os.path.join(WORKDIR, ".task-failed")]:
        if os.path.isfile(path):
            try:
                with open(path, "r") as f:
                    reason = f.read().strip()
                os.remove(path)
                return "failed", reason
            except Exception:
                return "failed", ""

    return None, ""


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def _handle_signal(signum, frame):
    global _running
    _running = False


def main():
    global _running

    if not DISPATCHER_IP:
        print("worker-agent: DISPATCHER_IP not set, exiting", file=sys.stderr)
        sys.exit(1)
    if not API_TOKEN:
        print("worker-agent: DISPATCH_API_TOKEN not set, exiting", file=sys.stderr)
        sys.exit(1)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    print(f"worker-agent: started (worker={RESOLVED_WORKER_ID}, "
          f"dispatcher={DISPATCHER_IP}, interval={HEARTBEAT_INTERVAL}s)")

    # Seed the last-seen commit so we don't report a false "new commit" on first tick
    _detect_new_commit()

    while _running:
        # 1. Send heartbeat
        ok = send_heartbeat()
        if not ok:
            print("worker-agent: heartbeat failed", file=sys.stderr)

        # 2. Check for new commits (progress detection)
        if _detect_new_commit():
            task_id = _read_task_id()
            files = _get_files_changed()
            print(f"worker-agent: new commit detected (task={task_id}, files_changed={files})")

        # 3. Check for task completion/failure markers
        result, detail = _check_completion_marker()
        if result:
            task_id = _read_task_id()
            if task_id:
                if result == "complete":
                    print(f"worker-agent: reporting task {task_id} complete")
                    report_complete(task_id, detail)
                else:
                    print(f"worker-agent: reporting task {task_id} failed")
                    report_failure(task_id, detail)

        # 4. Sleep until next heartbeat
        for _ in range(HEARTBEAT_INTERVAL):
            if not _running:
                break
            time.sleep(1)

    print("worker-agent: shutting down")


if __name__ == "__main__":
    main()
