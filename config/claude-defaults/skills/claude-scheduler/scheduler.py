"""
scheduler.py - Cross-platform task runner with adaptive backoff.

Manages recurring tasks, tracks state, and integrates with OS schedulers.
3 consecutive failures -> stop task + warn via SessionStart hook.

Usage:
    python scheduler.py list
    python scheduler.py add --name "X" --command "Y" --interval weekly
    python scheduler.py remove <task-id>
    python scheduler.py status
    python scheduler.py reset <task-id>
    python scheduler.py run <task-id>
    python scheduler.py run-all
"""
import sys
import os
import json
import subprocess
import datetime
import argparse

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
TASKS_FILE = os.path.join(SKILL_DIR, "tasks.json")
STATE_FILE = os.path.join(SKILL_DIR, "state.json")

INTERVAL_MAP = {
    "hourly": 60,
    "daily": 1440,
    "weekly": 10080,
}


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

def _load_tasks():
    if not os.path.isfile(TASKS_FILE):
        return []
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("tasks", [])


def _save_tasks(tasks):
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump({"tasks": tasks}, f, indent=2)


def _load_state():
    if not os.path.isfile(STATE_FILE):
        return {}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)


def _get_task_state(state, task_id):
    return state.get(task_id, {
        "consecutive_errors": 0,
        "stopped": False,
        "stopped_reason": None,
        "last_error": None,
        "last_run": None,
        "last_result": None,
        "total_runs": 0,
        "total_errors": 0,
    })


def _expand_home(cmd):
    """Expand ~ to actual home directory in command strings."""
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE", "")
    return cmd.replace("~", home)


# ---------------------------------------------------------------------------
# Task execution
# ---------------------------------------------------------------------------

def _is_due(task, task_state):
    """Check if a task is due to run based on interval and last run time."""
    last_run = task_state.get("last_run")
    if not last_run:
        return True
    try:
        last_dt = datetime.datetime.fromisoformat(last_run)
    except (ValueError, TypeError):
        return True
    interval = task.get("interval_minutes", 10080)
    next_run = last_dt + datetime.timedelta(minutes=interval)
    return datetime.datetime.now() >= next_run


def run_task(task_id):
    """Run a single task by ID. Returns (success, message)."""
    tasks = _load_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return False, f"Task not found: {task_id}"
    if not task.get("enabled", True):
        return False, f"Task disabled: {task_id}"

    state = _load_state()
    ts = _get_task_state(state, task_id)

    if ts.get("stopped"):
        return False, (f"Task stopped after {ts['consecutive_errors']} errors. "
                       f"Last error: {ts.get('last_error', 'unknown')}. "
                       f"Run: python scheduler.py reset {task_id}")

    cmd = _expand_home(task["command"])
    now = datetime.datetime.now().isoformat()

    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=300,
        )
        ts["last_run"] = now
        ts["total_runs"] = ts.get("total_runs", 0) + 1

        if result.returncode == 0:
            ts["consecutive_errors"] = 0
            ts["last_result"] = "success"
            ts["last_error"] = None
            state[task_id] = ts
            _save_state(state)
            stdout_preview = result.stdout.strip()[:200] if result.stdout else ""
            return True, f"OK: {stdout_preview}"
        else:
            # Non-zero exit = error (exit 2 = warnings, still counts as success for backoff)
            if result.returncode == 2:
                ts["consecutive_errors"] = 0
                ts["last_result"] = "warnings"
                ts["last_error"] = None
                state[task_id] = ts
                _save_state(state)
                return True, f"Completed with warnings (exit 2)"
            # Actual failure
            ts["consecutive_errors"] = ts.get("consecutive_errors", 0) + 1
            ts["total_errors"] = ts.get("total_errors", 0) + 1
            ts["last_result"] = "error"
            err_msg = (result.stderr.strip() or result.stdout.strip())[:200]
            ts["last_error"] = err_msg

            max_retries = task.get("max_retries", 3)
            if ts["consecutive_errors"] >= max_retries:
                ts["stopped"] = True
                ts["stopped_reason"] = f"Failed {max_retries}x consecutively"

            state[task_id] = ts
            _save_state(state)

            if ts["stopped"]:
                return False, f"STOPPED: {max_retries} consecutive failures. Last: {err_msg}"
            return False, f"Error (retry {ts['consecutive_errors']}/{max_retries}): {err_msg}"

    except subprocess.TimeoutExpired:
        ts["consecutive_errors"] = ts.get("consecutive_errors", 0) + 1
        ts["total_errors"] = ts.get("total_errors", 0) + 1
        ts["last_result"] = "timeout"
        ts["last_error"] = "Command timed out (300s)"
        ts["last_run"] = now

        max_retries = task.get("max_retries", 3)
        if ts["consecutive_errors"] >= max_retries:
            ts["stopped"] = True
            ts["stopped_reason"] = f"Timed out {max_retries}x consecutively"

        state[task_id] = ts
        _save_state(state)
        return False, f"Timeout after 300s"

    except Exception as e:
        ts["consecutive_errors"] = ts.get("consecutive_errors", 0) + 1
        ts["total_errors"] = ts.get("total_errors", 0) + 1
        ts["last_result"] = "exception"
        ts["last_error"] = str(e)[:200]
        ts["last_run"] = now

        max_retries = task.get("max_retries", 3)
        if ts["consecutive_errors"] >= max_retries:
            ts["stopped"] = True
            ts["stopped_reason"] = f"Exception {max_retries}x consecutively"

        state[task_id] = ts
        _save_state(state)
        return False, f"Exception: {e}"


def run_all():
    """Run all due and enabled tasks. Called by OS scheduler."""
    tasks = _load_tasks()
    state = _load_state()
    ran = 0
    skipped = 0
    errors = 0

    for task in tasks:
        tid = task["id"]
        if not task.get("enabled", True):
            skipped += 1
            continue

        ts = _get_task_state(state, tid)
        if ts.get("stopped"):
            skipped += 1
            continue

        if not _is_due(task, ts):
            skipped += 1
            continue

        success, msg = run_task(tid)
        if success:
            ran += 1
        else:
            errors += 1
        print(f"  [{tid}] {msg}")

    print(f"\nRan: {ran}, Skipped: {skipped}, Errors: {errors}")
    return 0 if errors == 0 else 1


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_list():
    tasks = _load_tasks()
    state = _load_state()
    if not tasks:
        print("No tasks registered.")
        return

    print()
    print(f"{'ID':<25} {'Interval':<10} {'Enabled':<8} {'Status':<10} {'Last Run':<20}")
    print("-" * 75)
    for task in tasks:
        tid = task["id"]
        interval = task.get("interval_minutes", "?")
        enabled = "ON" if task.get("enabled", True) else "OFF"
        ts = _get_task_state(state, tid)
        status = "STOPPED" if ts.get("stopped") else (ts.get("last_result") or "pending")
        last_run = ts.get("last_run") or "-"
        if last_run != "-":
            last_run = last_run[:19]
        print(f"{tid:<25} {str(interval)+'m':<10} {enabled:<8} {status:<10} {last_run:<20}")
    print()


def cmd_status():
    tasks = _load_tasks()
    state = _load_state()
    if not tasks:
        print("No tasks registered.")
        return

    print()
    for task in tasks:
        tid = task["id"]
        ts = _get_task_state(state, tid)
        print(f"=== {tid} ===")
        print(f"  Name: {task.get('name', tid)}")
        print(f"  Command: {task['command']}")
        print(f"  Interval: {task.get('interval_minutes', '?')} minutes")
        print(f"  Enabled: {task.get('enabled', True)}")
        print(f"  Status: {'STOPPED' if ts.get('stopped') else 'active'}")
        if ts.get("stopped"):
            print(f"  Stopped reason: {ts.get('stopped_reason', '?')}")
        print(f"  Last run: {ts.get('last_run', 'never')}")
        print(f"  Last result: {ts.get('last_result', 'n/a')}")
        if ts.get("last_error"):
            print(f"  Last error: {ts['last_error']}")
        print(f"  Consecutive errors: {ts.get('consecutive_errors', 0)}")
        print(f"  Total runs: {ts.get('total_runs', 0)}")
        print(f"  Total errors: {ts.get('total_errors', 0)}")

        # Next run calculation
        if ts.get("last_run") and not ts.get("stopped"):
            try:
                last_dt = datetime.datetime.fromisoformat(ts["last_run"])
                interval = task.get("interval_minutes", 10080)
                next_dt = last_dt + datetime.timedelta(minutes=interval)
                print(f"  Next run: {next_dt.isoformat()[:19]}")
            except (ValueError, TypeError):
                pass
        print()


def cmd_add(args):
    name = args.name
    command = args.command
    interval_str = args.interval or "weekly"
    interval = INTERVAL_MAP.get(interval_str)
    if interval is None:
        try:
            interval = int(interval_str)
        except ValueError:
            print(f"Invalid interval: {interval_str}")
            print("Use: hourly, daily, weekly, or a number (minutes)")
            sys.exit(1)

    task_id = name.lower().replace(" ", "-")
    tasks = _load_tasks()
    if any(t["id"] == task_id for t in tasks):
        print(f"Task already exists: {task_id}")
        sys.exit(1)

    tasks.append({
        "id": task_id,
        "name": name,
        "command": command,
        "interval_minutes": interval,
        "enabled": True,
        "max_retries": 3,
        "notify_on_failure": True,
    })
    _save_tasks(tasks)
    print(f"Added task: {task_id} (every {interval} minutes)")


def cmd_remove(task_id):
    tasks = _load_tasks()
    new_tasks = [t for t in tasks if t["id"] != task_id]
    if len(new_tasks) == len(tasks):
        print(f"Task not found: {task_id}")
        sys.exit(1)
    _save_tasks(new_tasks)

    # Clean state
    state = _load_state()
    state.pop(task_id, None)
    _save_state(state)
    print(f"Removed task: {task_id}")


def cmd_reset(task_id):
    state = _load_state()
    ts = state.get(task_id, {})
    ts["consecutive_errors"] = 0
    ts["stopped"] = False
    ts["stopped_reason"] = None
    ts["last_error"] = None
    state[task_id] = ts
    _save_state(state)
    print(f"Reset task: {task_id} (cleared stopped state, errors)")


def cmd_run(task_id):
    success, msg = run_task(task_id)
    print(msg)
    sys.exit(0 if success else 1)


def cmd_run_all():
    code = run_all()
    sys.exit(code)


def get_stopped_tasks():
    """Return list of stopped task warnings for SessionStart hook integration."""
    tasks = _load_tasks()
    state = _load_state()
    warnings = []
    for task in tasks:
        tid = task["id"]
        ts = _get_task_state(state, tid)
        if ts.get("stopped") and task.get("notify_on_failure", True):
            warnings.append(
                f"[Scheduler] Task '{tid}' failed {ts.get('consecutive_errors', '?')} times. "
                f"Last error: {ts.get('last_error', 'unknown')}. "
                f"Run: python scheduler.py reset {tid}"
            )
    return warnings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Claude Scheduler - Task Runner")
    sub = parser.add_subparsers(dest="subcommand")

    sub.add_parser("list", help="List tasks and status")
    sub.add_parser("status", help="Detailed task status")

    add_p = sub.add_parser("add", help="Add a new task")
    add_p.add_argument("--name", required=True, help="Task name")
    add_p.add_argument("--command", required=True, help="Command to run")
    add_p.add_argument("--interval", default="weekly", help="hourly|daily|weekly|<minutes>")

    rem_p = sub.add_parser("remove", help="Remove a task")
    rem_p.add_argument("task_id", help="Task ID")

    reset_p = sub.add_parser("reset", help="Clear stopped state")
    reset_p.add_argument("task_id", help="Task ID")

    run_p = sub.add_parser("run", help="Run a single task now")
    run_p.add_argument("task_id", help="Task ID")

    sub.add_parser("run-all", help="Run all due tasks (OS scheduler calls this)")

    args = parser.parse_args()

    if args.subcommand == "list":
        cmd_list()
    elif args.subcommand == "status":
        cmd_status()
    elif args.subcommand == "add":
        cmd_add(args)
    elif args.subcommand == "remove":
        cmd_remove(args.task_id)
    elif args.subcommand == "reset":
        cmd_reset(args.task_id)
    elif args.subcommand == "run":
        cmd_run(args.task_id)
    elif args.subcommand == "run-all":
        cmd_run_all()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
