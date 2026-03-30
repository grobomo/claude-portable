#!/usr/bin/env python3
"""
worker-agent.py -- Lightweight daemon that runs alongside Claude in the worker container.

Combines two roles:
  1. Heartbeat client: sends periodic heartbeats to the dispatcher, detects progress
     via git log, and reports task completion or failure.
  2. HTTP monitoring server: exposes local endpoints for container health checks.

Heartbeat mode (requires DISPATCHER_IP and DISPATCH_API_TOKEN):
  POST /worker/heartbeat     -> dispatcher
  POST /task/{id}/complete   -> dispatcher
  POST /task/{id}/fail       -> dispatcher

HTTP monitoring endpoints (always available on port 8090):
  GET /status    Claude PID, CPU%, memory, uptime, task state
  GET /output    Last 200 lines of /tmp/claude-output.log
  GET /activity  Recent file changes, git commits, zombie processes
  GET /health    Disk, container uptime, task counts, errors

Environment:
  DISPATCHER_IP        Dispatcher host (e.g. 10.0.1.5, optional)
  DISPATCH_API_TOKEN   Bearer token for dispatcher auth (optional)
  WORKER_ID            Worker identifier (default: hostname)
  HEARTBEAT_INTERVAL   Seconds between heartbeats (default: 30)
  WORKER_WORKDIR       Git working directory to monitor (default: /workspace/task)
  TASK_ID              Current task ID (set by bootstrap, updated at runtime)
  WORKER_AGENT_PORT    HTTP monitoring port (default: 8090)
  CLAUDE_OUTPUT_LOG    Path to Claude output log (default: /tmp/claude-output.log)
  WORKSPACE            Workspace root for monitoring (default: /workspace)

Usage:
  python3 scripts/worker-agent.py &
"""

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer

# ---------------------------------------------------------------------------
# Configuration -- Heartbeat
# ---------------------------------------------------------------------------

DISPATCHER_IP = os.environ.get("DISPATCHER_IP", "")
API_TOKEN = os.environ.get("DISPATCH_API_TOKEN", "")
WORKER_ID = os.environ.get("WORKER_ID", "")
HEARTBEAT_INTERVAL = int(os.environ.get("HEARTBEAT_INTERVAL", "30"))
WORKDIR = os.environ.get("WORKER_WORKDIR", "/workspace/task")
TASK_ID = os.environ.get("TASK_ID", "")

# ---------------------------------------------------------------------------
# Configuration -- HTTP Monitoring
# ---------------------------------------------------------------------------

PORT = int(os.environ.get("WORKER_AGENT_PORT", "8090"))
OUTPUT_LOG = os.environ.get("CLAUDE_OUTPUT_LOG", "/tmp/claude-output.log")
WORKSPACE = os.environ.get("WORKSPACE", "/workspace")
START_TIME = time.time()

# Cumulative error counter
_error_count = 0
_total_tasks = 0

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

# ===========================================================================
# Git helpers
# ===========================================================================

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


# ===========================================================================
# Process detection
# ===========================================================================

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


def _find_claude_pid():
    """Find Claude CLI process PID via pgrep."""
    try:
        r = subprocess.run(
            ["pgrep", "-f", "claude -p"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return int(r.stdout.strip().splitlines()[0])
    except Exception:
        pass
    return None


def _read_proc_stat_cpu(pid):
    """Read CPU time from /proc/PID/stat. Returns (utime+stime) in clock ticks."""
    try:
        with open(f"/proc/{pid}/stat", "r") as f:
            fields = f.read().split()
        utime = int(fields[13])
        stime = int(fields[14])
        return utime + stime
    except Exception:
        return None


def _get_cpu_percent(pid):
    """Estimate CPU% by sampling /proc/PID/stat twice, 200ms apart."""
    ticks_per_sec = os.sysconf("SC_CLK_TCK")
    t1 = _read_proc_stat_cpu(pid)
    wall1 = time.monotonic()
    if t1 is None:
        return 0.0
    time.sleep(0.2)
    t2 = _read_proc_stat_cpu(pid)
    wall2 = time.monotonic()
    if t2 is None:
        return 0.0
    cpu_delta = (t2 - t1) / ticks_per_sec
    wall_delta = wall2 - wall1
    if wall_delta <= 0:
        return 0.0
    return round(cpu_delta / wall_delta * 100, 1)


def _get_memory_mb(pid):
    """Read VmRSS from /proc/PID/status."""
    try:
        with open(f"/proc/{pid}/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    kb = int(line.split()[1])
                    return round(kb / 1024, 1)
    except Exception:
        pass
    return 0.0


def _get_running_seconds(pid):
    """Seconds since process started, from /proc/PID/stat starttime."""
    try:
        ticks_per_sec = os.sysconf("SC_CLK_TCK")
        with open(f"/proc/{pid}/stat", "r") as f:
            fields = f.read().split()
        starttime_ticks = int(fields[21])
        with open("/proc/uptime", "r") as f:
            uptime_secs = float(f.read().split()[0])
        start_secs = starttime_ticks / ticks_per_sec
        return round(uptime_secs - start_secs, 1)
    except Exception:
        return 0.0


# ===========================================================================
# Dispatcher HTTP helpers (heartbeat client)
# ===========================================================================

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


# ===========================================================================
# Task ID discovery
# ===========================================================================

def _read_task_id():
    """Read task ID from env or /data/.task-id file."""
    if TASK_ID:
        return TASK_ID
    try:
        with open("/data/.task-id", "r") as f:
            return f.read().strip()
    except Exception:
        return ""


def _get_task_id():
    """Read current task ID from environment, file, or branch name."""
    tid = _read_task_id()
    if tid:
        return tid
    try:
        r = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=WORKSPACE, capture_output=True, text=True, timeout=5,
        )
        branch = r.stdout.strip()
        m = re.search(r"task-(\d+)", branch)
        if m:
            return m.group(0)
    except Exception:
        pass
    return ""


# ===========================================================================
# Heartbeat client
# ===========================================================================

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


# ===========================================================================
# Completion detection
# ===========================================================================

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


# ===========================================================================
# HTTP Monitoring Server handlers
# ===========================================================================

def handle_status():
    """GET /status -- Claude process metrics."""
    pid = _find_claude_pid()
    if pid is None:
        return {
            "pid": None,
            "cpu_percent": 0.0,
            "memory_mb": 0.0,
            "running_seconds": 0.0,
            "task_id": _get_task_id(),
            "state": "idle",
        }
    return {
        "pid": pid,
        "cpu_percent": _get_cpu_percent(pid),
        "memory_mb": _get_memory_mb(pid),
        "running_seconds": _get_running_seconds(pid),
        "task_id": _get_task_id(),
        "state": "busy",
    }


def handle_output():
    """GET /output -- Last 200 lines of claude output log."""
    try:
        with open(OUTPUT_LOG, "r") as f:
            lines = deque(f, maxlen=200)
        return {"lines": list(lines), "count": len(lines), "path": OUTPUT_LOG}
    except FileNotFoundError:
        return {"lines": [], "count": 0, "path": OUTPUT_LOG, "error": "log file not found"}
    except Exception as e:
        return {"lines": [], "count": 0, "path": OUTPUT_LOG, "error": str(e)}


def _last_stdout_time():
    """Modification time of the output log."""
    try:
        mtime = os.path.getmtime(OUTPUT_LOG)
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(mtime))
    except Exception:
        return None


def _last_file_modified():
    """Find most recently modified file under /workspace (non-hidden, non-.git)."""
    best_path = None
    best_time = 0
    try:
        for root, dirs, files in os.walk(WORKSPACE):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fname in files:
                if fname.startswith("."):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    mt = os.path.getmtime(fpath)
                    if mt > best_time:
                        best_time = mt
                        best_path = fpath
                except OSError:
                    continue
    except Exception:
        pass
    if best_path:
        return {
            "path": best_path,
            "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(best_time)),
        }
    return {"path": None, "time": None}


def _last_git_commit():
    """Most recent git commit in /workspace."""
    try:
        r = subprocess.run(
            ["git", "log", "-1", "--format=%H%n%s%n%aI"],
            cwd=WORKSPACE, capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            parts = r.stdout.strip().splitlines()
            return {
                "hash": parts[0] if len(parts) > 0 else "",
                "message": parts[1] if len(parts) > 1 else "",
                "time": parts[2] if len(parts) > 2 else "",
            }
    except Exception:
        pass
    return {"hash": "", "message": "", "time": ""}


def _count_zombies():
    """Count zombie processes from /proc."""
    count = 0
    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                with open(f"/proc/{entry}/status", "r") as f:
                    for line in f:
                        if line.startswith("State:") and "Z" in line.split(":")[1]:
                            count += 1
                        if line.startswith("State:"):
                            break
            except (OSError, PermissionError):
                continue
    except Exception:
        pass
    return count


def handle_activity():
    """GET /activity -- Recent activity indicators."""
    return {
        "last_stdout_time": _last_stdout_time(),
        "last_file_modified": _last_file_modified(),
        "last_git_commit": _last_git_commit(),
        "zombie_count": _count_zombies(),
    }


def _disk_free_gb():
    """Free disk space on /workspace in GB."""
    try:
        st = os.statvfs(WORKSPACE)
        return round(st.f_bavail * st.f_frsize / (1024 ** 3), 2)
    except Exception:
        return 0.0


def _container_uptime_hours():
    """Hours since container started (from /proc/uptime)."""
    try:
        with open("/proc/uptime", "r") as f:
            secs = float(f.read().split()[0])
        return round(secs / 3600, 2)
    except Exception:
        return round((time.time() - START_TIME) / 3600, 2)


def _count_tasks():
    """Count completed tasks from TODO.md if it exists."""
    count = 0
    todo_path = os.path.join(WORKSPACE, "TODO.md")
    try:
        with open(todo_path, "r") as f:
            for line in f:
                if re.match(r"^\s*-\s+\[x\]", line, re.IGNORECASE):
                    count += 1
    except Exception:
        pass
    return count


def handle_health():
    """GET /health -- Container and system health."""
    return {
        "disk_free_gb": _disk_free_gb(),
        "container_uptime_hours": _container_uptime_hours(),
        "total_tasks": _count_tasks(),
        "error_count": _error_count,
    }


ROUTES = {
    "/status": handle_status,
    "/output": handle_output,
    "/activity": handle_activity,
    "/health": handle_health,
}


class AgentHandler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        body = json.dumps(data, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        global _error_count
        handler = ROUTES.get(self.path)
        if handler:
            try:
                self._send_json(handler())
            except Exception as e:
                _error_count += 1
                self._send_json({"error": str(e)}, 500)
        else:
            self._send_json({"error": "not found", "endpoints": list(ROUTES.keys())}, 404)

    def log_message(self, fmt, *args):
        pass  # Suppress per-request logging


# ===========================================================================
# Heartbeat loop (runs in background thread when dispatcher is configured)
# ===========================================================================

def _heartbeat_loop():
    """Background thread: send heartbeats and check for task completion."""
    global _running

    _detect_new_commit()  # Seed last-seen commit

    while _running:
        ok = send_heartbeat()
        if not ok:
            print("worker-agent: heartbeat failed", file=sys.stderr)

        if _detect_new_commit():
            task_id = _read_task_id()
            files = _get_files_changed()
            print(f"worker-agent: new commit detected (task={task_id}, files_changed={files})")

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

        for _ in range(HEARTBEAT_INTERVAL):
            if not _running:
                break
            time.sleep(1)


# ===========================================================================
# Main
# ===========================================================================

def _handle_signal(signum, frame):
    global _running
    _running = False


def main():
    global _running

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # Start heartbeat thread if dispatcher is configured
    if DISPATCHER_IP and API_TOKEN:
        print(f"worker-agent: heartbeat enabled (worker={RESOLVED_WORKER_ID}, "
              f"dispatcher={DISPATCHER_IP}, interval={HEARTBEAT_INTERVAL}s)")
        hb_thread = threading.Thread(target=_heartbeat_loop, daemon=True)
        hb_thread.start()
    else:
        print("worker-agent: heartbeat disabled (DISPATCHER_IP or DISPATCH_API_TOKEN not set)")

    # Start HTTP monitoring server (always)
    server = HTTPServer(("0.0.0.0", PORT), AgentHandler)
    print(f"worker-agent: HTTP monitoring on port {PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _running = False
        server.shutdown()
        print("worker-agent: shutting down")


if __name__ == "__main__":
    main()
