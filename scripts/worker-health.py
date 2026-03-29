#!/usr/bin/env python3
"""
worker-health.py -- HTTP health/control endpoint for CCC workers.

Runs on each worker instance (port 8081). Provides:
  GET  /health     Current task, pipeline stage, uptime, idle time
  POST /interrupt  Kill current Claude process, return to idle
  POST /pull       Force git pull on next iteration

Started by bootstrap.sh or continuous-claude.sh on worker boot.

Environment:
  WORKER_HEALTH_PORT    Port to listen on (default: 8081)
  WORKER_ID             Instance identifier (default: hostname)
  WORKER_WORKDIR        continuous-claude working directory (default: /workspace/continuous-claude)
"""

import json
import os
import re
import signal
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("WORKER_HEALTH_PORT", "8081"))
WORKER_ID = os.environ.get("WORKER_ID", os.environ.get("CLAUDE_PORTABLE_ID", ""))
WORKDIR = os.environ.get("WORKER_WORKDIR", "/workspace/continuous-claude")
START_TIME = time.time()

# Flags that continuous-claude.sh checks
PULL_FLAG = "/data/.force-pull"
INTERRUPT_FLAG = "/data/.interrupt"


def _get_hostname():
    try:
        return os.uname().nodename
    except AttributeError:
        import socket
        return socket.gethostname()


if not WORKER_ID:
    WORKER_ID = _get_hostname()


def _get_current_branch():
    try:
        r = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=WORKDIR, capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _get_current_task():
    """Extract task number and description from current branch name."""
    branch = _get_current_branch()
    if not branch or not branch.startswith("continuous-claude/"):
        return {"branch": branch, "task_num": None, "description": ""}

    m = re.search(r"task-(\d+)", branch)
    if not m:
        return {"branch": branch, "task_num": None, "description": ""}

    task_num = int(m.group(1))
    # Read task description from TODO.md
    todo_path = os.path.join(WORKDIR, "TODO.md")
    try:
        with open(todo_path, "r") as f:
            lines = f.readlines()
        unchecked_count = 0
        for line in lines:
            if re.match(r"^\s*-\s+\[\s+\]", line):
                unchecked_count += 1
                if unchecked_count == task_num:
                    desc = re.sub(r"^\s*-\s+\[\s+\]\s+", "", line).strip()
                    return {"branch": branch, "task_num": task_num, "description": desc}
    except Exception:
        pass
    return {"branch": branch, "task_num": task_num, "description": ""}


PIPELINE_STATE_FILE = os.environ.get("PIPELINE_STATE_FILE", "/data/pipeline-state.json")


def _get_pipeline_stage():
    """Read current pipeline stage from pipeline-state.json (primary) or legacy stage log."""
    # Primary: read from worker-pipeline.py state file
    try:
        with open(PIPELINE_STATE_FILE, "r") as f:
            state = json.load(f)
        if state.get("status") == "idle":
            return {"stage": "idle", "stages_complete": 0}
        current = state.get("current_phase") or "idle"
        phases = state.get("phases", {})
        complete = sum(1 for p in phases.values() if p.get("status") == "passed")
        return {"stage": current, "stages_complete": complete, "phases": phases}
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # Fallback: legacy per-task stage log
    branch = _get_current_branch()
    m = re.search(r"task-(\d+)", branch) if branch else None
    if not m:
        return {"stage": "idle", "stages_complete": 0}

    task_n = m.group(1)
    stage_file = f"/data/task-{task_n}-stages.json"
    try:
        with open(stage_file, "r") as f:
            stages = json.load(f)
        stage_names = ["RESEARCH", "PLAN", "TESTS", "IMPLEMENT", "VERIFY", "PR"]
        current = "idle"
        complete = 0
        for s in stage_names:
            if s in stages:
                status = stages[s].get("status", "?")
                if status == "running":
                    current = s
                elif status == "passed":
                    complete += 1
        return {"stage": current, "stages_complete": complete}
    except Exception:
        return {"stage": "unknown", "stages_complete": 0}


def _is_claude_running():
    """Check if a Claude CLI process is active."""
    try:
        r = subprocess.run(
            ["pgrep", "-f", "node.*claude"],
            capture_output=True, text=True, timeout=5,
        )
        return bool(r.stdout.strip())
    except Exception:
        return False


def _is_maintenance():
    return os.path.isfile("/data/.maintenance")


def _get_idle_time():
    """Seconds since last Claude process finished (approximation from branch age)."""
    if _is_claude_running():
        return 0
    # Check last modification of stage log or continuous-claude.log
    for path in ["/data/continuous-claude.log"]:
        try:
            mtime = os.path.getmtime(path)
            return int(time.time() - mtime)
        except Exception:
            continue
    return -1


class WorkerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/health", "/"):
            task = _get_current_task()
            pipeline = _get_pipeline_stage()
            data = {
                "worker_id": WORKER_ID,
                "uptime_seconds": int(time.time() - START_TIME),
                "claude_running": _is_claude_running(),
                "maintenance": _is_maintenance(),
                "idle_seconds": _get_idle_time(),
                "task": task,
                "pipeline": pipeline,
                "pull_pending": os.path.isfile(PULL_FLAG),
                "interrupt_pending": os.path.isfile(INTERRUPT_FLAG),
            }
            body = json.dumps(data, indent=2).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/interrupt":
            # Kill current Claude process
            try:
                r = subprocess.run(
                    ["pkill", "-f", "node.*claude"],
                    capture_output=True, text=True, timeout=10,
                )
                killed = r.returncode == 0
            except Exception:
                killed = False

            # Also set flag for continuous-claude.sh to see
            try:
                with open(INTERRUPT_FLAG, "w") as f:
                    f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            except Exception:
                pass

            data = {"status": "interrupted" if killed else "no_process", "worker_id": WORKER_ID}
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/pull":
            # Set flag for continuous-claude.sh to force git pull
            try:
                with open(PULL_FLAG, "w") as f:
                    f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                status = "pull_scheduled"
            except Exception as e:
                status = f"error: {e}"

            data = {"status": status, "worker_id": WORKER_ID}
            body = json.dumps(data).encode()
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


def main():
    server = HTTPServer(("0.0.0.0", PORT), WorkerHandler)
    print(f"Worker health endpoint listening on port {PORT} (worker_id={WORKER_ID})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
