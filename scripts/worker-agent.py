#!/usr/bin/env python3
"""
worker-agent.py -- Lightweight HTTP server for Claude process monitoring.

Runs on port 8090 alongside Claude. Exposes:
  GET /status    Claude PID, CPU%, memory, uptime, task state
  GET /output    Last 200 lines of /tmp/claude-output.log
  GET /activity  Recent file changes, git commits, zombie processes
  GET /health    Disk, container uptime, task counts, errors

Usage:
  python3 scripts/worker-agent.py &
"""

import json
import os
import re
import subprocess
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("WORKER_AGENT_PORT", "8090"))
OUTPUT_LOG = os.environ.get("CLAUDE_OUTPUT_LOG", "/tmp/claude-output.log")
WORKSPACE = os.environ.get("WORKSPACE", "/workspace")
START_TIME = time.time()

# Cumulative error counter
_error_count = 0
_total_tasks = 0


def _find_claude_pid():
    """Find Claude CLI process PID via pgrep."""
    try:
        r = subprocess.run(
            ["pgrep", "-f", "claude -p"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            # Return first matching PID
            return int(r.stdout.strip().splitlines()[0])
    except Exception:
        pass
    return None


def _read_proc_stat_cpu(pid):
    """Read CPU time from /proc/PID/stat. Returns (utime+stime) in clock ticks."""
    try:
        with open(f"/proc/{pid}/stat", "r") as f:
            fields = f.read().split()
        # fields[13] = utime, fields[14] = stime (0-indexed)
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
                    # Value is in kB
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


def _get_task_id():
    """Read current task ID from environment or branch name."""
    task_id = os.environ.get("TASK_ID", "")
    if task_id:
        return task_id
    # Try to extract from git branch
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
            # Skip hidden dirs and .git
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
    """Hours since container started (from /proc/1/stat or /proc/uptime)."""
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


def main():
    server = HTTPServer(("0.0.0.0", PORT), AgentHandler)
    print(f"worker-agent listening on port {PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
