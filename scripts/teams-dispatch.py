#!/usr/bin/env python3
"""Teams -> CCC dispatch with request tracking.

Polls a Teams chat for @claude mentions or quoted replies to bot messages,
dispatches to ccc instances, tracks each request through its lifecycle,
and replies with results.

Runs on a dedicated dispatcher EC2 instance (cloud-native mode):
  - Graph token read from GRAPH_TOKEN_FILE (written by dispatcher-daemon.sh)
  - Workers discovered via EC2 API tags (Project=claude-portable, not dispatcher)
  - SSH keys synced from S3 fleet-keys/ by dispatcher-daemon.sh

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
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Request states
STATE_RECEIVED = "received"
STATE_ACKED = "acked"
STATE_DISPATCHED = "dispatched"
STATE_RUNNING = "running"
STATE_COMPLETED = "completed"
STATE_FAILED = "failed"

BOT_TAG = "[Claude Bot]"

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Instance naming convention (ccc prefixes names with "ccc-"):
#   worker-N / ccc-worker-N  = automated task runner
#   interactive / ccc-interactive = SSH/manual use (no automated tasks)
WORKER_PATTERNS = ("worker-", "ccc-worker-")
INTERACTIVE_PATTERNS = ("interactive", "ccc-interactive")

# ── State persistence ───────────────────────────────────────────────────────

STATE_FILE = os.environ.get(
    "TEAMS_DISPATCH_STATE_FILE",
    os.path.join(os.environ.get("TEMP", "/tmp"), "teams-dispatch-state.json")
)


def load_state():
    if os.path.isfile(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"processed_msgs": [], "requests": {}}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── Graph API helpers ────────────────────────────────────────────────────────

def _load_graph_token():
    """Read the Graph access token from GRAPH_TOKEN_FILE."""
    token_file = os.environ.get("GRAPH_TOKEN_FILE", "")
    if not token_file:
        raise RuntimeError(
            "GRAPH_TOKEN_FILE env var is not set. "
            "Run via dispatcher-daemon.sh or set the env var to a token JSON file."
        )
    if not os.path.isfile(token_file):
        raise RuntimeError(f"Graph token file not found: {token_file}")

    with open(token_file) as f:
        raw = f.read().strip()

    # Support both {"access_token": "..."} and a raw token string
    if raw.startswith("{"):
        data = json.loads(raw)
        token = data.get("access_token") or data.get("token", "")
    else:
        token = raw

    if not token:
        raise RuntimeError(f"No access_token found in {token_file}")
    return token


def graph_get(path, params=None):
    """GET from MS Graph API, return parsed JSON body."""
    token = _load_graph_token()
    url = f"{GRAPH_BASE}{path}"
    if params:
        query = "&".join(f"{k}={urllib.request.quote(str(v))}" for k, v in params.items())
        url = f"{url}?{query}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def graph_post(path, body):
    """POST to MS Graph API, return parsed JSON body (or empty dict on 204)."""
    token = _load_graph_token()
    url = f"{GRAPH_BASE}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw.decode()) if raw else {}
    except urllib.error.HTTPError as e:
        if e.code == 204:
            return {}
        raise


def graph_put_binary(path, data, content_type="application/octet-stream"):
    """PUT binary data to MS Graph API, return parsed JSON body."""
    token = _load_graph_token()
    url = f"{GRAPH_BASE}{path}"
    req = urllib.request.Request(url, data=data, method="PUT", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return json.loads(raw.decode()) if raw else {}
    except urllib.error.HTTPError as e:
        if e.code == 204:
            return {}
        raise


def upload_pem_to_onedrive(key_path, instance_name):
    """Upload a .pem key file to OneDrive and return a sharing URL, or None on failure."""
    try:
        filename = f"{instance_name}-ssh-key.pem"
        with open(key_path, "rb") as f:
            data = f.read()
        # Upload to OneDrive root (overwrites if exists)
        item = graph_put_binary(f"/me/drive/root:/{filename}:/content", data)
        item_id = item.get("id")
        if not item_id:
            print(f"  WARNING: OneDrive upload returned no item ID for {filename}")
            return None
        # Create an org-scoped view link so the user can download it
        link_resp = graph_post(f"/me/drive/items/{item_id}/createLink", {
            "type": "view",
            "scope": "organization",
        })
        url = link_resp.get("link", {}).get("webUrl")
        if url:
            print(f"  Uploaded {filename} to OneDrive: {url}")
        return url
    except Exception as e:
        print(f"  WARNING: Failed to upload PEM to OneDrive: {e}")
        return None


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


def is_reply_to_bot(m):
    """Return True if this message is a quoted reply to a [Claude Bot] message.

    Teams encodes quoted replies as attachments with contentType="messageReference".
    The attachment content JSON includes a messagePreview field with the quoted text.
    """
    for att in m.get("attachments", []):
        if att.get("contentType") != "messageReference":
            continue
        try:
            content = json.loads(att.get("content", "{}"))
            if BOT_TAG in content.get("messagePreview", ""):
                return True
        except (json.JSONDecodeError, TypeError):
            pass
    return False


def extract_reply_text(body_html):
    """Extract only the new reply text, stripping any <attachment> quote blocks."""
    # Remove <attachment ...>...</attachment> elements (the quoted original message)
    text = re.sub(r"<attachment[^>]*>.*?</attachment>", "", body_html,
                  flags=re.DOTALL | re.IGNORECASE)
    # Strip remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text).strip()
    return text


# ── EC2 worker discovery ─────────────────────────────────────────────────────

def _aws_region():
    """Get current AWS region from EC2 metadata or env."""
    try:
        token = subprocess.run([
            "curl", "-s", "-X", "PUT",
            "http://169.254.169.254/latest/api/token",
            "-H", "X-aws-ec2-metadata-token-ttl-seconds: 21600",
            "--connect-timeout", "2",
        ], capture_output=True, text=True, timeout=5).stdout.strip()
        if token:
            region = subprocess.run([
                "curl", "-s",
                "-H", f"X-aws-ec2-metadata-token: {token}",
                "http://169.254.169.254/latest/meta-data/placement/region",
                "--connect-timeout", "2",
            ], capture_output=True, text=True, timeout=5).stdout.strip()
            if region:
                return region
    except Exception:
        pass
    return os.environ.get("AWS_DEFAULT_REGION", "us-east-2")


def get_running_instances():
    """Discover running claude-portable worker instances via EC2 API tags."""
    region = _aws_region()
    try:
        r = subprocess.run([
            "aws", "ec2", "describe-instances",
            "--region", region,
            "--filters",
            "Name=tag:Project,Values=claude-portable",
            "Name=instance-state-name,Values=running",
            "--query",
            (
                "Reservations[].Instances[]"
                ".{name: Tags[?Key=='Name'].Value|[0],"
                " id: InstanceId,"
                " ip: PublicIpAddress,"
                " role: Tags[?Key=='Role'].Value|[0]}"
            ),
            "--output", "json",
        ], capture_output=True, text=True, timeout=20)

        if r.returncode != 0:
            print(f"  WARNING: EC2 describe-instances failed: {r.stderr.strip()}")
            return []

        items = json.loads(r.stdout)
        instances = []
        for item in items:
            name = (item.get("name") or "").strip()
            ip = (item.get("ip") or "").strip()
            role = (item.get("role") or "").strip().lower()
            iid = (item.get("id") or "").strip()
            if not ip:
                continue
            # Exclude dispatcher itself
            if role == "dispatcher":
                continue
            instances.append({"name": name, "id": iid, "ip": ip, "role": role})
        return instances
    except Exception as e:
        print(f"  WARNING: get_running_instances error: {e}")
        return []


def find_ssh_key(instance_name):
    """Find SSH key for a named instance (synced from S3 by dispatcher-daemon.sh)."""
    key_dir = os.path.expanduser("~/.ssh/ccc-keys")
    key_path = os.path.join(key_dir, f"{instance_name}.pem")
    if os.path.isfile(key_path):
        return key_path
    return None


def ssh_exec(ip, ssh_key, cmd, timeout=15):
    """Run command on ccc container via SSH, return stdout."""
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


def get_workers():
    """Get running worker instances only."""
    return [i for i in get_running_instances()
            if any(i["name"].startswith(p) for p in WORKER_PATTERNS)]


def get_interactive():
    """Get the interactive instance, or None."""
    return next((i for i in get_running_instances()
                 if any(i["name"] == p or i["name"].startswith(p + "-")
                        for p in INTERACTIVE_PATTERNS)), None)


def start_stopped_interactive():
    """Find a stopped interactive instance and start it. Returns instance dict or None."""
    region = _aws_region()
    try:
        r = subprocess.run([
            "aws", "ec2", "describe-instances",
            "--region", region,
            "--filters",
            "Name=tag:Project,Values=claude-portable",
            "Name=instance-state-name,Values=stopped",
            "--query",
            (
                "Reservations[].Instances[]"
                ".{name: Tags[?Key=='Name'].Value|[0],"
                " id: InstanceId,"
                " role: Tags[?Key=='Role'].Value|[0]}"
            ),
            "--output", "json",
        ], capture_output=True, text=True, timeout=20)

        if r.returncode != 0:
            return None

        items = json.loads(r.stdout)
        # Find the first stopped interactive instance
        target = next((
            item for item in items
            if any((item.get("name") or "").startswith(p) for p in INTERACTIVE_PATTERNS)
            and (item.get("role") or "").lower() != "dispatcher"
        ), None)
        if not target:
            return None

        instance_id = target["id"]
        name = target["name"]
        print(f"  Starting stopped instance {name} ({instance_id})")
        subprocess.run([
            "aws", "ec2", "start-instances",
            "--region", region,
            "--instance-ids", instance_id,
        ], capture_output=True, text=True, timeout=20)

        # Wait up to 90s for running + public IP
        for _ in range(18):
            time.sleep(5)
            r2 = subprocess.run([
                "aws", "ec2", "describe-instances",
                "--region", region,
                "--instance-ids", instance_id,
                "--query", "Reservations[0].Instances[0].{state: State.Name, ip: PublicIpAddress}",
                "--output", "json",
            ], capture_output=True, text=True, timeout=20)
            if r2.returncode == 0:
                info = json.loads(r2.stdout)
                if info.get("state") == "running" and info.get("ip"):
                    return {"name": name, "id": instance_id, "ip": info["ip"], "role": "interactive"}
        print(f"  WARNING: Instance {name} did not reach running state in time")
        return None
    except Exception as e:
        print(f"  WARNING: start_stopped_interactive error: {e}")
        return None


def pick_worker():
    """Pick a worker instance, round-robin."""
    global _dispatch_counter
    workers = get_workers()
    if not workers:
        # Fall back to any running non-worker instance
        all_inst = get_running_instances()
        workers = [i for i in all_inst
                   if not any(i["name"] == p or i["name"].startswith(p + "-")
                              for p in INTERACTIVE_PATTERNS)]
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

    # Run claude -p on the instance, capture stdout to the result file
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
    if prompt_lower in ("ssh", "shell", "terminal", "ssh plz", "ssh please"):
        return True
    return any(k in prompt_lower for k in keywords)


def handle_ssh_request(chat_id, sender):
    """Handle SSH session request — start interactive instance if needed and provide access."""
    inst = get_interactive()

    if not inst:
        # Try to start a stopped interactive instance
        reply_in_teams(chat_id,
            f"No interactive instance running, {sender}. Looking for a stopped one to start...")
        inst = start_stopped_interactive()
        if not inst:
            reply_in_teams(chat_id,
                f"No interactive instance found (running or stopped). "
                f"Launch one with: `ccc --name interactive` from your local machine.")
            return

    name = inst["name"]
    ip = inst["ip"]
    ssh_key_path = find_ssh_key(name)

    # Try to upload the .pem key to OneDrive for easy download
    key_url = None
    if ssh_key_path:
        key_url = upload_pem_to_onedrive(ssh_key_path, name)

    ssh_cmd = f"ssh -i {name}.pem ubuntu@{ip} -t 'docker exec -it claude-portable bash -l'"

    lines = [f"Here you go, {sender}:", "", f"Instance: {name} ({ip})"]

    if key_url:
        lines.append(f"SSH key: {key_url}  (download, then:)")
        lines.append(f"  `{ssh_cmd}`")
    elif ssh_key_path:
        lines.append(f"SSH: `ssh -i {ssh_key_path} ubuntu@{ip} -t 'docker exec -it claude-portable bash -l'`")
    else:
        lines.append(f"SSH: `{ssh_cmd}`  (get key via `ccc` on your local machine)")

    lines += [
        f"Web chat: http://{ip}:8888/  (alternative — no key needed)",
        "",
        "This instance is yours — no automated tasks will run on it.",
    ]

    reply_in_teams(chat_id, "\n".join(lines))


def check_result(ip, ssh_key, request_id):
    """Check if a request has completed by looking for result file."""
    result = ssh_exec(ip, ssh_key, f"cat /tmp/teams-result-{request_id}.txt 2>/dev/null")
    return result if result else None


# ── Health endpoint ─────────────────────────────────────────────────────────

HEALTH_PORT = int(os.environ.get("DISPATCHER_HEALTH_PORT", "8080"))

_health_lock = threading.Lock()
_health_state = {
    "status": "starting",
    "last_poll": None,
    "graph_token_valid": None,
    "workers": [],
    "pending_requests": [],
    "error_count": 0,
}


def _tcp_reachable(ip, port=22, timeout=3):
    """Return True if TCP port is open on the host."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        ok = s.connect_ex((ip, port)) == 0
        s.close()
        return ok
    except Exception:
        return False


def _graph_token_valid():
    """Return True if the Graph token can make a successful /me call."""
    try:
        graph_get("/me")
        return True
    except Exception:
        return False


def _update_health(state, error_count):
    """Refresh global health snapshot. Called after each poll iteration."""
    requests = state.get("requests", {})
    pending = [
        {
            "id": rid,
            "state": req["state"],
            "sender": req.get("sender", "?"),
            "dispatched_at": req.get("dispatched_at", ""),
            "instance": req.get("instance_name", ""),
        }
        for rid, req in requests.items()
        if req["state"] in (STATE_ACKED, STATE_DISPATCHED, STATE_RUNNING)
    ]

    workers = get_workers()
    worker_status = [
        {"name": w["name"], "ip": w["ip"], "reachable": _tcp_reachable(w["ip"])}
        for w in workers
    ]

    token_ok = _graph_token_valid()

    if not token_ok:
        overall = "degraded"
    elif not worker_status:
        overall = "no_workers"
    else:
        overall = "ok"

    with _health_lock:
        _health_state["status"] = overall
        _health_state["last_poll"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _health_state["graph_token_valid"] = token_ok
        _health_state["workers"] = worker_status
        _health_state["pending_requests"] = pending
        _health_state["error_count"] = error_count


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/health", "/"):
            with _health_lock:
                data = dict(_health_state)
            data["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            body = json.dumps(data, indent=2).encode()
            http_status = 200 if data["status"] in ("ok", "no_workers") else 503
            self.send_response(http_status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):  # suppress default access log noise
        pass


def start_health_server(port=HEALTH_PORT):
    """Start HTTP health server in a background daemon thread."""
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True, name="health-server")
    t.start()
    print(f"  Health: http://0.0.0.0:{port}/health")
    return server


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

        # If no @claude trigger, check for a quoted reply to a bot message
        if not is_trigger and is_reply_to_bot(m):
            reply_text = extract_reply_text(body_html)
            if reply_text:
                prompt, is_trigger = reply_text, True

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
                f"Request `{rid}` dispatched to {info.get('name', 'worker')}. "
                f"I'll post the result when it's done.")
        else:
            req["state"] = STATE_FAILED
            err = info.get("error", "unknown") if isinstance(info, dict) else str(info)
            print(f"  [{rid}] FAILED to dispatch: {err}")
            reply_in_teams(chat_id,
                f"Request `{rid}` failed to dispatch: {err}. No running instances?")

    # --- Phase 3: Check pending requests for results ---
    for rid, req in list(requests.items()):
        if req["state"] not in (STATE_DISPATCHED, STATE_RUNNING):
            continue

        ip = req.get("instance_ip", "")
        name = req.get("instance_name", "")

        # If we lost instance info, try to recover from running instances
        if not ip:
            instances = get_running_instances()
            if instances:
                inst = instances[0]
                ip = inst.get("ip", "")
                name = inst.get("name", "")
                req["instance_ip"] = ip
                req["instance_name"] = name

        if not ip:
            continue

        ssh_key = find_ssh_key(name)
        if not ssh_key:
            continue

        # Check for result file (per-request ID, no collision)
        result = check_result(ip, ssh_key, rid)
        if result:
            req["state"] = STATE_COMPLETED
            req["result"] = result[:500]
            print(f"  [{rid}] COMPLETED: {result[:80]}")
            reply_in_teams(chat_id, f"Request `{rid}` completed!\n\n{result[:400]}")
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
                f"Request `{rid}` — Claude finished but didn't produce a result. "
                f"Check instance logs.")

        # Timeout: 15min from dispatch time
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
    parser = argparse.ArgumentParser(
        description="Teams -> CCC dispatch (cloud-native, runs on dispatcher EC2 instance)"
    )
    parser.add_argument("--chat-id", required=True, help="Teams chat ID to monitor")
    parser.add_argument("--trigger", default="@claude", help="Trigger keyword (default: @claude)")
    parser.add_argument("--interval", type=int, default=30,
                        help="Poll interval seconds (default: 30)")
    parser.add_argument("--instance", help="Preferred worker instance name")
    parser.add_argument("--project", default="/workspace",
                        help="Working directory on instance (default: /workspace)")
    args = parser.parse_args()

    # Validate required env var early
    if not os.environ.get("GRAPH_TOKEN_FILE"):
        print("ERROR: GRAPH_TOKEN_FILE env var is not set.", file=sys.stderr)
        print("  Run via dispatcher-daemon.sh, or set GRAPH_TOKEN_FILE to a token JSON file.",
              file=sys.stderr)
        sys.exit(1)

    print("=" * 55)
    print(f"  {BOT_TAG} Teams -> CCC Dispatch (cloud-native)")
    print("=" * 55)
    print(f"  Chat:       {args.chat_id[:35]}...")
    print(f"  Trigger:    {args.trigger}")
    print(f"  Poll:       every {args.interval}s")
    print(f"  Instance:   {args.instance or 'auto (EC2 tag discovery)'}")
    print(f"  Token file: {os.environ.get('GRAPH_TOKEN_FILE', '(not set)')}")
    print(f"  State:      {STATE_FILE}")
    print()

    state = load_state()
    print(f"  Loaded state: {len(state.get('processed_msgs', []))} processed, "
          f"{len(state.get('requests', {}))} tracked requests")
    print()

    start_health_server()
    print("[+] Polling...")

    error_count = 0
    while True:
        try:
            new = poll_once(args.chat_id, args.trigger, state, args.instance, args.project)
            if new:
                print(f"  Processed {new} new request(s)")
            _update_health(state, error_count)
        except KeyboardInterrupt:
            print("\n  Stopped.")
            save_state(state)
            break
        except Exception as e:
            error_count += 1
            print(f"  ERROR in poll: {e}")
            with _health_lock:
                _health_state["error_count"] = error_count
                _health_state["status"] = "degraded"

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
