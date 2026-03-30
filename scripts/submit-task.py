#!/usr/bin/env python3
"""CLI client for the claude-portable dispatcher API.

Usage:
    python3 scripts/submit-task.py 'task description'
    python3 scripts/submit-task.py --status TASK_ID
    python3 scripts/submit-task.py --wait TASK_ID --timeout 300
    python3 scripts/submit-task.py --list
    python3 scripts/submit-task.py --list --state running
    python3 scripts/submit-task.py --cancel TASK_ID

Environment variables:
    DISPATCHER_URL        Base URL of the dispatcher (e.g. http://10.0.1.50:8080)
    DISPATCH_API_TOKEN    Bearer token for API auth (optional if dispatcher has none)
"""
import argparse
import json
import os
import sys
import time

try:
    import requests
except ImportError:
    print("error: 'requests' library is required. Install with: pip install requests",
          file=sys.stderr)
    sys.exit(1)


def get_config():
    url = os.environ.get("DISPATCHER_URL", "").rstrip("/")
    if not url:
        print("error: DISPATCHER_URL environment variable is not set", file=sys.stderr)
        sys.exit(1)
    token = os.environ.get("DISPATCH_API_TOKEN", "")
    return url, token


def make_headers(token):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def submit_task(description):
    url, token = get_config()
    resp = requests.post(
        f"{url}/task",
        headers=make_headers(token),
        json={"text": description},
        timeout=30,
    )
    if resp.status_code == 201:
        task = resp.json()
        print(f"Task submitted: {task['id']}")
        print(f"  Description: {task.get('text', '')}")
        print(f"  Status:      {task.get('state', '')}")
        print(f"  Submitted:   {task.get('created_at', '')}")
        return task
    elif resp.status_code == 401:
        print("error: unauthorized -- check DISPATCH_API_TOKEN", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"error: submit failed (HTTP {resp.status_code})", file=sys.stderr)
        try:
            print(f"  {resp.json()}", file=sys.stderr)
        except Exception:
            print(f"  {resp.text[:200]}", file=sys.stderr)
        sys.exit(1)


def get_status(task_id):
    url, token = get_config()
    resp = requests.get(
        f"{url}/task/{task_id}",
        headers=make_headers(token),
        timeout=30,
    )
    if resp.status_code == 200:
        task = resp.json()
        print(f"Task {task['id']}:")
        print(f"  Description: {task.get('text', '')}")
        print(f"  Status:      {task.get('state', '')}")
        print(f"  Submitted:   {task.get('created_at', '')}")
        if task.get("priority"):
            print(f"  Priority:    {task['priority']}")
        if task.get("dispatched_at"):
            print(f"  Dispatched:  {task['dispatched_at']}")
        if task.get("completed_at"):
            print(f"  Completed:   {task['completed_at']}")
        if task.get("result"):
            print(f"  Result:      {task['result']}")
        if task.get("error"):
            print(f"  Error:       {task['error']}")
        return task
    elif resp.status_code == 404:
        print(f"error: task {task_id} not found", file=sys.stderr)
        sys.exit(1)
    elif resp.status_code == 401:
        print("error: unauthorized -- check DISPATCH_API_TOKEN", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"error: status check failed (HTTP {resp.status_code})", file=sys.stderr)
        sys.exit(1)


def wait_for_task(task_id, timeout, poll_interval=5):
    url, token = get_config()
    deadline = time.time() + timeout
    terminal_states = ("COMPLETED", "FAILED", "CANCELLED")

    print(f"Waiting for task {task_id} (timeout: {timeout}s)...")
    while time.time() < deadline:
        resp = requests.get(
            f"{url}/task/{task_id}",
            headers=make_headers(token),
            timeout=30,
        )
        if resp.status_code == 401:
            print("error: unauthorized -- check DISPATCH_API_TOKEN", file=sys.stderr)
            sys.exit(1)
        if resp.status_code != 200:
            print(f"error: status check failed (HTTP {resp.status_code})", file=sys.stderr)
            sys.exit(1)
        task = resp.json()
        status = task.get("state", "unknown")
        elapsed = int(time.time() + timeout - deadline)
        print(f"  [{elapsed:3d}s] state={status}", end="")
        if task.get("progress"):
            print(f"  progress={task['progress']}", end="")
        print()
        if status in terminal_states:
            print()
            get_status(task_id)
            sys.exit(0 if status == "completed" else 1)
        remaining = deadline - time.time()
        time.sleep(min(poll_interval, max(1, remaining)))

    print(f"\nerror: timed out after {timeout}s (last status: {status})", file=sys.stderr)
    sys.exit(2)


def list_tasks(state_filter=None):
    url, token = get_config()
    params = ""
    if state_filter:
        params = f"?status={state_filter}"
    resp = requests.get(
        f"{url}/tasks{params}",
        headers=make_headers(token),
        timeout=30,
    )
    if resp.status_code == 401:
        print("error: unauthorized -- check DISPATCH_API_TOKEN", file=sys.stderr)
        sys.exit(1)
    if resp.status_code != 200:
        print(f"error: list failed (HTTP {resp.status_code})", file=sys.stderr)
        sys.exit(1)
    data = resp.json()
    tasks = data.get("tasks", [])
    if not tasks:
        label = f" with state={state_filter}" if state_filter else ""
        print(f"No tasks found{label}.")
        return
    print(f"{'ID':<38} {'STATE':<12} {'CREATED':<22} TEXT")
    print("-" * 100)
    for t in tasks:
        desc = t.get("text", "")[:40]
        print(f"{t['id']:<38} {t.get('state',''):<12} {t.get('created_at',''):<22} {desc}")
    print(f"\n{data['count']} task(s)")


def cancel_task(task_id):
    url, token = get_config()
    resp = requests.delete(
        f"{url}/task/{task_id}",
        headers=make_headers(token),
        timeout=30,
    )
    if resp.status_code == 200:
        task = resp.json()
        print(f"Task {task_id} cancelled (was: {task.get('state', '?')})")
    elif resp.status_code == 404:
        print(f"error: task {task_id} not found", file=sys.stderr)
        sys.exit(1)
    elif resp.status_code == 401:
        print("error: unauthorized -- check DISPATCH_API_TOKEN", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"error: cancel failed (HTTP {resp.status_code})", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="CLI client for the claude-portable dispatcher API",
        epilog="Environment: DISPATCHER_URL (required), DISPATCH_API_TOKEN (optional)",
    )
    parser.add_argument("description", nargs="?",
                        help="Task description to submit")
    parser.add_argument("--status", metavar="TASK_ID",
                        help="Check status of a task")
    parser.add_argument("--wait", metavar="TASK_ID",
                        help="Poll until task reaches a terminal state")
    parser.add_argument("--timeout", type=int, default=300,
                        help="Timeout in seconds for --wait (default: 300)")
    parser.add_argument("--list", action="store_true",
                        help="List tasks")
    parser.add_argument("--state", metavar="STATE",
                        help="Filter --list by status (pending/running/completed/failed/cancelled)")
    parser.add_argument("--cancel", metavar="TASK_ID",
                        help="Cancel a pending or running task")

    args = parser.parse_args()

    # Exactly one action must be specified
    actions = sum([
        bool(args.description),
        bool(args.status),
        bool(args.wait),
        args.list,
        bool(args.cancel),
    ])
    if actions == 0:
        parser.print_help()
        sys.exit(1)
    if actions > 1 and not (args.list and args.state):
        if not (args.wait and args.timeout):
            parser.error("specify exactly one action: description, --status, --wait, --list, or --cancel")

    if args.description:
        submit_task(args.description)
    elif args.status:
        get_status(args.status)
    elif args.wait:
        wait_for_task(args.wait, args.timeout)
    elif args.list:
        list_tasks(args.state)
    elif args.cancel:
        cancel_task(args.cancel)


if __name__ == "__main__":
    try:
        main()
    except requests.ConnectionError:
        url = os.environ.get("DISPATCHER_URL", "(not set)")
        print(f"error: cannot connect to dispatcher at {url}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print()
        sys.exit(130)
