#!/usr/bin/env python3
"""
worker-pipeline.py -- Pipeline state tracker for CCC workers.

Tracks the current task through TDD pipeline phases:
  RESEARCH → REVIEW → PLAN → TESTS → IMPLEMENT → VERIFY → PR

Writes state to /data/pipeline-state.json. Called by continuous-claude.sh
at each phase transition. Worker-health.py reads this file for HTTP API.

Usage (from continuous-claude.sh):
  python3 worker-pipeline.py start <task_num> <description>
  python3 worker-pipeline.py phase <phase_name> running
  python3 worker-pipeline.py phase <phase_name> passed [output_file]
  python3 worker-pipeline.py phase <phase_name> failed [error_msg]
  python3 worker-pipeline.py gate <phase_name> passed
  python3 worker-pipeline.py gate <phase_name> failed <reason>
  python3 worker-pipeline.py done
  python3 worker-pipeline.py idle
  python3 worker-pipeline.py status   (print current state as JSON)

Environment:
  PIPELINE_STATE_FILE   Path to state file (default: /data/pipeline-state.json)
  WORKER_ID             Instance identifier (default: hostname)
"""

import json
import os
import socket
import sys
import time

PHASES = ["RESEARCH", "REVIEW", "PLAN", "TESTS", "IMPLEMENT", "VERIFY", "PR"]

STATE_FILE = os.environ.get("PIPELINE_STATE_FILE", "/data/pipeline-state.json")
WORKER_ID = os.environ.get(
    "WORKER_ID",
    os.environ.get("CLAUDE_PORTABLE_ID", socket.gethostname()),
)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_state(state):
    os.makedirs(os.path.dirname(STATE_FILE) or ".", exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def cmd_start(args):
    """Start tracking a new task."""
    if len(args) < 2:
        print("Usage: worker-pipeline.py start <task_num> <description>", file=sys.stderr)
        return 1
    task_num = int(args[0])
    description = " ".join(args[1:])
    state = {
        "worker_id": WORKER_ID,
        "task_num": task_num,
        "description": description,
        "status": "running",
        "current_phase": None,
        "started_at": _now(),
        "updated_at": _now(),
        "phases": {},
    }
    _write_state(state)
    return 0


def cmd_phase(args):
    """Update phase status: phase <name> <running|passed|failed> [detail]."""
    if len(args) < 2:
        print("Usage: worker-pipeline.py phase <name> <status> [detail]", file=sys.stderr)
        return 1
    phase_name = args[0].upper()
    status = args[1].lower()
    detail = " ".join(args[2:]) if len(args) > 2 else None

    state = _read_state()
    if not state:
        print("No active task. Run 'start' first.", file=sys.stderr)
        return 1

    if phase_name not in state.get("phases", {}):
        state.setdefault("phases", {})[phase_name] = {}

    phase = state["phases"][phase_name]

    if status == "running":
        phase["status"] = "running"
        phase["start"] = _now()
        state["current_phase"] = phase_name
    elif status == "passed":
        phase["status"] = "passed"
        phase["end"] = _now()
        if detail:
            phase["output_file"] = detail
    elif status == "failed":
        phase["status"] = "failed"
        phase["end"] = _now()
        if detail:
            phase["error"] = detail
    else:
        print(f"Unknown status: {status}", file=sys.stderr)
        return 1

    state["updated_at"] = _now()
    _write_state(state)
    return 0


def cmd_gate(args):
    """Record gate result: gate <phase> <passed|failed> [reason]."""
    if len(args) < 2:
        print("Usage: worker-pipeline.py gate <phase> <passed|failed> [reason]", file=sys.stderr)
        return 1
    phase_name = args[0].upper()
    result = args[1].lower()
    reason = " ".join(args[2:]) if len(args) > 2 else None

    state = _read_state()
    if not state:
        print("No active task.", file=sys.stderr)
        return 1

    phase = state.setdefault("phases", {}).setdefault(phase_name, {})
    phase["gate_result"] = result
    if reason:
        phase["gate_reason"] = reason
    state["updated_at"] = _now()
    _write_state(state)
    return 0


def cmd_done(args):
    """Mark current task as done."""
    state = _read_state()
    if not state:
        return 0
    state["status"] = "done"
    state["current_phase"] = None
    state["completed_at"] = _now()
    state["updated_at"] = _now()
    _write_state(state)
    return 0


def cmd_idle(args):
    """Set worker to idle state."""
    state = {
        "worker_id": WORKER_ID,
        "task_num": None,
        "description": "",
        "status": "idle",
        "current_phase": None,
        "updated_at": _now(),
        "phases": {},
    }
    _write_state(state)
    return 0


def cmd_status(args):
    """Print current pipeline state as JSON."""
    state = _read_state()
    print(json.dumps(state, indent=2))
    return 0


COMMANDS = {
    "start": cmd_start,
    "phase": cmd_phase,
    "gate": cmd_gate,
    "done": cmd_done,
    "idle": cmd_idle,
    "status": cmd_status,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: worker-pipeline.py <{'|'.join(COMMANDS)}> [args...]", file=sys.stderr)
        return 1
    return COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main() or 0)
