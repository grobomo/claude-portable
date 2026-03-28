#!/usr/bin/env python3
"""Teams -> CCC dispatch with request tracking.

Polls a Teams chat for @claude mentions, dispatches to ccc instances,
tracks each request through its lifecycle, and replies with results.

Runs locally on the laptop (needs Graph API token + ccc launcher).

Usage:
    python teams-dispatch.py --chat-id <TEAMS_CHAT_ID>
    python teams-dispatch.py --chat-id <ID> --trigger "@claude" --interval 30

Request lifecycle:
    received -> acked -> dispatched -> running -> completed / failed
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid

sys.path.insert(0, "C:/Users/joelg/Documents/ProjectsCL1/msgraph-lib")
from token_manager import graph_get, graph_post

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CCC_DIR = os.path.dirname(SCRIPT_DIR)
CCC_CMD = os.path.join(CCC_DIR, "ccc")

# Request states
STATE_RECEIVED = "received"
STATE_ACKED = "acked"
STATE_DISPATCHED = "dispatched"
STATE_RUNNING = "running"
STATE_COMPLETED = "completed"
STATE_FAILED = "failed"

BOT_TAG = "[Claude Bot]"

# ── State persistence ───────────────────────────────────────────────────────

STATE_FILE = os.path.join(os.environ.get("TEMP", "/tmp"), "teams-dispatch-state.json")

def load_state():
    if os.path.isfile(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"processed_msgs": [], "requests": {}}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

# ── Teams helpers ───────────────────────────────────────────────────────────

def reply_in_teams(chat_id, text):
    """Send a message to Teams chat with bot tag."""
    try:
        graph_post(f"/me/chats/{chat_id}/messages", body={
            "body": {"contentType": "text", "content": f"{BOT_TAG} {text}"}
        })
        return True
    except Exception as e:
        print(f"  WARNING: Teams reply failed: {e}")
        return False

def fetch_messages(chat_id, count=10):
    """Fetch recent messages from a Teams chat."""
    try:
        data = graph_get(f"/me/chats/{chat_id}/messages",
                         params={"$top": count, "$orderby": "createdDateTime desc"})
        return data.get("value", [])
    except Exception as e:
        print(f"  WARNING: Failed to fetch messages: {e}")
        return []


def extract_trigger(body_html, trigger):
    """Extract prompt text after trigger keyword, return (prompt, True) or (None, False)."""
    body_text = re.sub(r"<[^>]+>", "", body_html).strip()
    trigger_lower = trigger.lower()
    if trigger_lower not in body_text.lower():
        return None, False
    idx = body_text.lower().index(trigger_lower)
    prompt = body_text[idx + len(trigger):].strip()
    return (prompt, True) if prompt else (None, False)

# ── CCC helpers ─────────────────────────────────────────────────────────────

def get_running_instances():
    """Get list of running ccc instances."""
    try:
        r = subprocess.run(["python", CCC_CMD, "list"],
                           capture_output=True, text=True, timeout=15)
        instances = []
        for line in r.stdout.strip().split("\n")[2:]:  # skip header + separator
            parts = line.split()
            if len(parts) >= 3 and parts[2] == "running":
                instances.append({"name": parts[0], "id": parts[1], "ip": parts[3] if len(parts) > 3 else ""})
        return instances
    except Exception:
        return []

def find_ssh_key(instance_name):
    """Find SSH key for a named instance."""
    key_dir = os.path.expanduser("~/.ssh/ccc-keys")
    key_path = os.path.join(key_dir, f"{instance_name}.pem")
    if os.path.isfile(key_path):
        return key_path
    return None

def ssh_exec(ip, ssh_key, cmd, timeout=15):
    """Run command on ccc container, return stdout."""
    try:
        r = subprocess.run([
            "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
            "-o", "LogLevel=ERROR", "-i", ssh_key, f"ubuntu@{ip}",
            f"docker exec claude-portable bash -c '{cmd}'"
        ], capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""

_dispatch_counter = 0

# Instance naming convention (ccc prefixes names with "ccc-"):
#   worker-N / ccc-worker-N  = automated task runner
#   interactive / ccc-interactive = SSH/manual use (no automated tasks)
WORKER_PATTERNS = ("worker-", "ccc-worker-")
INTERACTIVE_PATTERNS = ("interactive", "ccc-interactive")


def get_workers():
    """Get running worker instances only."""
    return [i for i in get_running_instances()
            if any(i["name"].startswith(p) for p in WORKER_PATTERNS)]


def get_interactive():
    """Get the interactive instance, or None."""
    return next((i for i in get_running_instances()
                 if any(i["name"] == p or i["name"].startswith(p + "-") for p in INTERACTIVE_PATTERNS)), None)


def pick_worker():
    """Pick a worker instance, round-robin."""
    global _dispatch_counter
    workers = get_workers()
    if not workers:
        # Fall back to any running instance that isn't interactive
        all_inst = get_running_instances()
        workers = [i for i in all_inst if i["name"] != INTERACTIVE_NAME]
    if not workers:
        return None
    inst = workers[_dispatch_counter % len(workers)]
    _dispatch_counter += 1
    return inst


def dispatch_prompt(request_id, prompt, sender, instance_name=None, project="/workspace"):
    """Send a prompt to a ccc instance. Returns (success, instance_info_dict)."""
    full_prompt = f"Request {request_id} from {sender} via Teams.\n\n{prompt}"

    # Find a running instance to dispatch to
    instances = get_running_instances()
    inst = None
    if instance_name:
        inst = next((i for i in instances if i["name"] == instance_name), None)
    if not inst and instances:
        inst = instances[0]
    if not inst:
        return False, {"error": "no running instances"}

    ip = inst["ip"]
    name = inst["name"]
    info = {"name": name, "ip": ip}

    ssh_key = find_ssh_key(name)
    if not ssh_key:
        return False, {"error": f"no SSH key for {name}"}

    # Run claude -p on the instance, capture stdout to the result file directly via shell
    escaped = full_prompt.replace("'", "'\\''").replace('"', '\\"')
    result_file = f"/tmp/teams-result-{request_id}.txt"
    cmd = (
        f"docker exec -d -w {project} claude-portable bash -c '"
        f"claude -p \"{escaped}\" --dangerously-skip-permissions "
        f"> {result_file} 2>&1'"
    )

    try:
        r = subprocess.run([
            "ssh", "-o", "StrictHostKeyChecking=no", "-o", "LogLevel=ERROR",
            "-i", ssh_key, f"ubuntu@{ip}", cmd
        ], capture_output=True, text=True, timeout=30)
        return r.returncode == 0, info
    except subprocess.TimeoutExpired:
        return False, {**info, "error": "ssh timeout"}
    except Exception as e:
        return False, {**info, "error": str(e)}


def is_ssh_request(prompt):
    """Check if the prompt is asking for an SSH session rather than work."""
    keywords = ["ssh session", "ssh access", "give me ssh", "connect me", "terminal access",
                "shell access", "ssh plz", "ssh please", "give me a shell", "i need ssh",
                "need ssh", "want ssh", "ssh to", "shell session", "give me terminal"]
    prompt_lower = prompt.lower().strip()
    # Also match if the entire prompt is just "ssh" or "shell"
    if prompt_lower in ("ssh", "shell", "terminal", "ssh plz", "ssh please"):
        return True
    return any(k in prompt_lower for k in keywords)


def handle_ssh_request(chat_id, sender):
    """Handle SSH session request — use dedicated interactive instance, never a worker."""
    inst = get_interactive()

    if not inst:
        # No interactive instance running — launch one
        reply_in_teams(chat_id,
            f"Launching an interactive instance for you, {sender}. This takes ~3-5 min...")
        try:
            r = subprocess.run(
                ["python", CCC_CMD, "--name", "interactive", "--new"],
                capture_output=True, text=True, timeout=420)
            # Re-check
            inst = get_interactive()
        except Exception as e:
            reply_in_teams(chat_id, f"Failed to launch interactive instance: {e}")
            return

    if not inst:
        reply_in_teams(chat_id, f"Could not start interactive instance, {sender}. Try `ccc -n interactive` manually.")
        return

    name = inst["name"]
    ip = inst["ip"]
    ssh_key_path = find_ssh_key(name)
    key_info = f"~/.ssh/ccc-keys/{name}.pem" if ssh_key_path else "(key not found)"

    reply_in_teams(chat_id,
        f"Here you go, {sender}:\n\n"
        f"Instance: {name} ({ip})\n"
        f"SSH: `ssh -i {key_info} ubuntu@{ip} -t 'docker exec -it claude-portable bash -l'`\n"
        f"Web chat: http://{ip}:8888/\n"
        f"Or run: `ccc -n {name}`\n\n"
        f"This instance is yours — no automated tasks will run on it."
    )

def check_result(ip, ssh_key, request_id):
    """Check if a request has completed by looking for result file."""
    result = ssh_exec(ip, ssh_key, f"cat /tmp/teams-result-{request_id}.txt 2>/dev/null")
    return result if result else None

# ── Poll loop ───────────────────────────────────────────────────────────────

def poll_once(chat_id, trigger, state, instance_name=None, project="/workspace"):
    """Single poll iteration: check for new messages, dispatch, check results."""
    processed = set(state.get("processed_msgs", []))
    requests = state.get("requests", {})

    # --- Phase 1: Check for new @claude messages ---
    messages = fetch_messages(chat_id)
    new_requests = []

    for m in messages:
        mid = m.get("id", "")
        if mid in processed:
            continue

        body_html = m.get("body", {}).get("content", "")
        prompt, is_trigger = extract_trigger(body_html, trigger)

        # Mark as processed regardless
        processed.add(mid)

        if not is_trigger:
            continue

        # Ignore our own bot messages
        body_text = re.sub(r"<[^>]+>", "", body_html).strip()
        if body_text.startswith(BOT_TAG):
            continue

        sender = "(unknown)"
        fr = m.get("from", {})
        if fr and fr.get("user"):
            sender = fr["user"].get("displayName", "(unknown)")

        request_id = uuid.uuid4().hex[:8]
        req = {
            "id": request_id,
            "chat_id": chat_id,
            "sender": sender,
            "prompt": prompt,
            "state": STATE_RECEIVED,
            "message_id": mid,
            "timestamp": m.get("createdDateTime", "")[:19],
            "instance_ip": "",
            "instance_name": "",
        }
        requests[request_id] = req
        new_requests.append(req)
        print(f"\n  [{time.strftime('%H:%M:%S')}] REQ {request_id} from {sender}: {prompt[:80]}")

    # --- Phase 2: ACK and dispatch new requests ---
    for req in new_requests:
        rid = req["id"]
        prompt = req["prompt"]

        # Handle SSH/connection requests immediately (no dispatch needed)
        if is_ssh_request(prompt):
            handle_ssh_request(chat_id, req["sender"])
            req["state"] = STATE_COMPLETED
            req["result"] = "SSH connection info provided"
            print(f"  [{rid}] SSH request handled")
            continue

        # ACK in Teams
        ack_msg = f"Got it, {req['sender']}! Request `{rid}` received. Dispatching to a worker..."
        if reply_in_teams(chat_id, ack_msg):
            req["state"] = STATE_ACKED
            print(f"  [{rid}] ACKed in Teams")

        # Dispatch to a worker (never interactive)
        worker = pick_worker()
        worker_name = worker["name"] if worker else instance_name
        req["dispatched_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        success, info = dispatch_prompt(rid, prompt, req["sender"], worker_name, project)
        if success:
            req["state"] = STATE_DISPATCHED
            req["instance_ip"] = info.get("ip", "")
            req["instance_name"] = info.get("name", "")
            print(f"  [{rid}] Dispatched to {info.get('name', '?')} ({info.get('ip', '?')})")
            reply_in_teams(chat_id,
                f"Request `{rid}` dispatched to {info.get('name', 'worker')}. I'll post the result when it's done.")
        else:
            req["state"] = STATE_FAILED
            err = info.get("error", "unknown") if isinstance(info, dict) else str(info)
            print(f"  [{rid}] FAILED to dispatch: {err}")
            reply_in_teams(chat_id, f"Request `{rid}` failed to dispatch: {err}. No running instances?")

    # --- Phase 3: Check pending requests for results ---
    for rid, req in list(requests.items()):
        if req["state"] not in (STATE_DISPATCHED, STATE_RUNNING):
            continue

        # Find the instance this was dispatched to
        ip = req.get("instance_ip", "")
        name = req.get("instance_name", "")

        # If we don't have instance info, try to find from running instances
        if not ip:
            instances = get_running_instances()
            if instances:
                inst = instances[0]  # Use first running instance
                ip = inst.get("ip", "")
                name = inst.get("name", "")
                req["instance_ip"] = ip
                req["instance_name"] = name

        if not ip:
            continue

        ssh_key = find_ssh_key(name)
        if not ssh_key:
            continue

        # Check for result file first (per-request ID, no collision)
        result = check_result(ip, ssh_key, rid)
        if result:
            req["state"] = STATE_COMPLETED
            req["result"] = result[:500]
            print(f"  [{rid}] COMPLETED: {result[:80]}")
            reply_in_teams(chat_id,
                f"Request `{rid}` completed!\n\n{result[:400]}")
            continue

        # Check if Claude is still running
        procs = ssh_exec(ip, ssh_key, "pgrep -f 'claude.*--print' | wc -l")
        try:
            proc_count = int(procs) if procs else 0
        except ValueError:
            proc_count = 0

        if proc_count > 0:
            if req["state"] != STATE_RUNNING:
                req["state"] = STATE_RUNNING
                print(f"  [{rid}] Running on {name}")
        elif req["state"] == STATE_RUNNING:
            # Claude exited but no result file
            req["state"] = STATE_FAILED
            req["result"] = "Claude exited without writing result"
            print(f"  [{rid}] Claude exited with no result")
            reply_in_teams(chat_id,
                f"Request `{rid}` — Claude finished but didn't produce a result. Check instance logs.")

        # Timeout: 15min from dispatch time (not message time)
        timeout_ts = req.get("dispatched_at", req.get("timestamp", ""))
        if timeout_ts and req["state"] in (STATE_DISPATCHED, STATE_RUNNING):
            try:
                t = time.mktime(time.strptime(timeout_ts, "%Y-%m-%dT%H:%M:%SZ"))
                if time.time() - t > 900:
                    req["state"] = STATE_FAILED
                    req["result"] = "Timed out (15min)"
                    print(f"  [{rid}] TIMED OUT")
                    reply_in_teams(chat_id, f"Request `{rid}` timed out after 15 minutes.")
            except (ValueError, OverflowError):
                pass

    # --- Cleanup old completed/failed requests (keep last 50) ---
    if len(requests) > 50:
        sorted_reqs = sorted(requests.items(), key=lambda x: x[1].get("timestamp", ""))
        for rid, req in sorted_reqs[:-50]:
            if req["state"] in (STATE_COMPLETED, STATE_FAILED):
                del requests[rid]

    # Save state
    state["processed_msgs"] = list(processed)[-500:]
    state["requests"] = requests
    save_state(state)

    return len(new_requests)


def main():
    parser = argparse.ArgumentParser(description="Teams -> CCC dispatch with request tracking")
    parser.add_argument("--chat-id", required=True, help="Teams chat ID to monitor")
    parser.add_argument("--trigger", default="@claude", help="Trigger keyword (default: @claude)")
    parser.add_argument("--interval", type=int, default=30, help="Poll interval seconds (default: 30)")
    parser.add_argument("--instance", help="Preferred ccc instance name")
    parser.add_argument("--project", default="/workspace", help="Working directory on instance")
    args = parser.parse_args()

    print("=" * 55)
    print(f"  {BOT_TAG} Teams -> CCC Dispatch")
    print("=" * 55)
    print(f"  Chat:     {args.chat_id[:35]}...")
    print(f"  Trigger:  {args.trigger}")
    print(f"  Poll:     every {args.interval}s")
    print(f"  Instance: {args.instance or 'auto'}")
    print(f"  State:    {STATE_FILE}")
    print()

    state = load_state()
    print(f"  Loaded state: {len(state.get('processed_msgs', []))} processed, "
          f"{len(state.get('requests', {}))} tracked requests")
    print()
    print("[+] Polling...")

    while True:
        try:
            new = poll_once(args.chat_id, args.trigger, state, args.instance, args.project)
            if new:
                print(f"  Processed {new} new request(s)")
        except KeyboardInterrupt:
            print("\n  Stopped.")
            save_state(state)
            break
        except Exception as e:
            print(f"  ERROR in poll: {e}")

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
