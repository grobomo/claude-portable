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
  DISPATCHER_URL        Dispatcher base URL for heartbeats (e.g. http://10.0.1.5:8080)
  HEARTBEAT_INTERVAL    Seconds between heartbeat POSTs (default: 30)
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
        stage_names = ["WHY", "RESEARCH", "REVIEW", "PLAN", "TESTS", "IMPLEMENT", "VERIFY", "PR"]
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


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_pipeline_state():
    try:
        with open(PIPELINE_STATE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_pipeline_state(state):
    os.makedirs(os.path.dirname(PIPELINE_STATE_FILE) or ".", exist_ok=True)
    with open(PIPELINE_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_pipeline_state():
    """Return current pipeline state for HTTP API."""
    state = _read_pipeline_state()
    if not state:
        return {"phase": "idle", "task_num": None, "phase_history": [], "gates": {}}
    return {
        "phase": state.get("current_phase") or "idle",
        "task_num": state.get("task_num"),
        "phase_start": state.get("phases", {}).get(
            state.get("current_phase", ""), {}
        ).get("start"),
        "phase_history": state.get("phase_history", []),
        "gates": state.get("gates", {}),
        "status": state.get("status", "idle"),
    }


def set_pipeline_phase(task_num, phase):
    """Set current pipeline phase. Resets history if task_num changes."""
    state = _read_pipeline_state()
    old_task = state.get("task_num")
    old_phase = state.get("current_phase")

    if old_task != task_num:
        # New task — reset
        old_phase = None
        state = {
            "worker_id": WORKER_ID,
            "task_num": task_num,
            "status": "running",
            "current_phase": phase,
            "updated_at": _now(),
            "phases": {},
            "phase_history": [],
            "gates": {},
        }
    else:
        state["current_phase"] = phase
        state["updated_at"] = _now()

    # Record in phases dict
    state.setdefault("phases", {})[phase] = {
        "status": "running",
        "start": _now(),
    }

    # Append to history
    state.setdefault("phase_history", []).append({
        "phase": phase,
        "started_at": _now(),
    })

    _write_pipeline_state(state)

    # Notify dispatcher immediately (best-effort, non-blocking)
    if DISPATCHER_URL:
        try:
            send_phase_change(DISPATCHER_URL, task_num, old_phase, phase)
        except Exception:
            pass


def record_gate_result(task_num, phase, passed, detail=""):
    """Record a gate result for a phase."""
    state = _read_pipeline_state()
    state.setdefault("gates", {})[phase] = {
        "passed": passed,
        "detail": detail,
        "timestamp": _now(),
    }
    state["updated_at"] = _now()
    _write_pipeline_state(state)


def set_pipeline_idle():
    """Reset pipeline to idle state."""
    state = {
        "worker_id": WORKER_ID,
        "task_num": None,
        "status": "idle",
        "current_phase": None,
        "updated_at": _now(),
        "phases": {},
        "phase_history": [],
        "gates": {},
    }
    _write_pipeline_state(state)


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
    def _send_json(self, data, status=200):
        body = json.dumps(data, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

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
            self._send_json(data)
        elif self.path == "/status":
            self._send_json(get_pipeline_state())
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
            try:
                with open(PULL_FLAG, "w") as f:
                    f.write(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                status = "pull_scheduled"
            except Exception as e:
                status = f"error: {e}"
            self._send_json({"status": status, "worker_id": WORKER_ID})

        elif self.path == "/phase":
            payload = self._read_body()
            task_num = payload.get("task_num")
            phase = payload.get("phase", "").upper()
            if task_num is None or not phase:
                self._send_json({"status": "error", "message": "task_num and phase required"}, 400)
                return
            set_pipeline_phase(task_num, phase)
            self._send_json({"status": "ok", "task_num": task_num, "phase": phase})

        elif self.path == "/gate":
            payload = self._read_body()
            task_num = payload.get("task_num")
            phase = payload.get("phase", "").upper()
            passed = payload.get("passed", False)
            detail = payload.get("detail", "")
            if task_num is None or not phase:
                self._send_json({"status": "error", "message": "task_num and phase required"}, 400)
                return
            record_gate_result(task_num, phase, passed, detail)
            self._send_json({"status": "ok", "task_num": task_num, "phase": phase, "passed": passed})

        elif self.path == "/answer":
            payload = self._read_body()
            answer_text = payload.get("answer", "")
            if not answer_text:
                self._send_json({"status": "error", "message": "answer required"}, 400)
                return
            # Write answer to pipeline state
            state = _read_pipeline_state()
            if state:
                state["status"] = "running"
                state["blocked_answer"] = answer_text
                state["unblocked_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                if state.get("blocked_phase"):
                    state["current_phase"] = state["blocked_phase"]
                _write_pipeline_state(state)
            # Also write to a file that continuous-claude.sh can read
            answer_file = "/data/.answer"
            try:
                with open(answer_file, "w") as f:
                    f.write(answer_text)
            except Exception:
                pass
            self._send_json({"status": "ok", "answer_received": True})

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass  # suppress per-request noise


HEARTBEAT_INTERVAL = int(os.environ.get("HEARTBEAT_INTERVAL", "30"))
DISPATCHER_URL = os.environ.get("DISPATCHER_URL", "")


_error_count = 0


def _get_cpu_percent():
    """Read CPU usage from /proc/stat (two samples 100ms apart)."""
    try:
        def read_cpu():
            with open("/proc/stat") as f:
                line = f.readline()
            parts = line.split()[1:]
            vals = [int(x) for x in parts[:8]]
            idle = vals[3] + vals[4]  # idle + iowait
            total = sum(vals)
            return idle, total

        idle1, total1 = read_cpu()
        time.sleep(0.1)
        idle2, total2 = read_cpu()

        idle_delta = idle2 - idle1
        total_delta = total2 - total1
        if total_delta == 0:
            return 0.0
        return round((1.0 - idle_delta / total_delta) * 100, 1)
    except Exception:
        return None


def _get_memory_info():
    """Read memory from /proc/meminfo. Returns (percent, {used, total})."""
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if parts[0] in ("MemTotal:", "MemAvailable:"):
                    info[parts[0].rstrip(":")] = int(parts[1])  # kB
        total_kb = info.get("MemTotal", 0)
        avail_kb = info.get("MemAvailable", 0)
        if total_kb == 0:
            return None, None
        used_kb = total_kb - avail_kb
        pct = round(used_kb / total_kb * 100, 1)
        return pct, {"used": round(used_kb / 1024), "total": round(total_kb / 1024)}
    except Exception:
        return None, None


def _get_disk_info():
    """Read disk usage from df. Returns (percent, {used, total})."""
    try:
        r = subprocess.run(
            ["df", "-B1", WORKDIR],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return None, None
        lines = r.stdout.strip().split("\n")
        if len(lines) < 2:
            return None, None
        parts = lines[1].split()
        total = int(parts[1])
        used = int(parts[2])
        if total == 0:
            return None, None
        pct = round(used / total * 100, 1)
        return pct, {"used": round(used / (1024**3), 1), "total": round(total / (1024**3), 1)}
    except Exception:
        return None, None


def _build_heartbeat_payload():
    """Build the heartbeat payload with current worker state and resource metrics."""
    pipeline = _get_pipeline_stage()
    task = _get_current_task()

    cpu = _get_cpu_percent()
    mem_pct, mem_mb = _get_memory_info()
    disk_pct, disk_gb = _get_disk_info()

    payload = {
        "worker_id": WORKER_ID,
        "task": task,
        "pipeline": pipeline,
        "idle_seconds": _get_idle_time(),
        "claude_running": _is_claude_running(),
        "maintenance": _is_maintenance(),
        "uptime_seconds": int(time.time() - START_TIME),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "error_count": _error_count,
    }
    if cpu is not None:
        payload["cpu_percent"] = cpu
    if mem_pct is not None:
        payload["memory_percent"] = mem_pct
        payload["memory_mb"] = mem_mb
    if disk_pct is not None:
        payload["disk_percent"] = disk_pct
        payload["disk_gb"] = disk_gb
    return payload


def send_heartbeat(dispatcher_url):
    """POST heartbeat to dispatcher. Returns True on success."""
    url = f"{dispatcher_url.rstrip('/')}/worker/heartbeat"
    payload = json.dumps(_build_heartbeat_payload()).encode()
    try:
        import urllib.request
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


def send_phase_change(dispatcher_url, task_num, old_phase, new_phase, gate_result=None):
    """POST immediate phase transition event to dispatcher. Best-effort."""
    url = f"{dispatcher_url.rstrip('/')}/worker/phase-change"
    payload = {
        "worker_id": WORKER_ID,
        "task_num": task_num,
        "old_phase": old_phase,
        "new_phase": new_phase,
        "gate_result": gate_result,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    data = json.dumps(payload).encode()
    try:
        import urllib.request
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


def heartbeat_loop():
    """Background thread: send heartbeat to dispatcher every HEARTBEAT_INTERVAL seconds."""
    if not DISPATCHER_URL:
        return
    while True:
        try:
            send_heartbeat(DISPATCHER_URL)
        except Exception:
            pass
        time.sleep(HEARTBEAT_INTERVAL)


def main():
    import threading

    # Start heartbeat thread if dispatcher URL configured
    if DISPATCHER_URL:
        t = threading.Thread(target=heartbeat_loop, daemon=True, name="heartbeat")
        t.start()
        print(f"Heartbeat started (interval={HEARTBEAT_INTERVAL}s, dispatcher={DISPATCHER_URL})")

    server = HTTPServer(("0.0.0.0", PORT), WorkerHandler)
    print(f"Worker health endpoint listening on port {PORT} (worker_id={WORKER_ID})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
