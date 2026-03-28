#!/usr/bin/env python3
"""Teams chat bridge for chatbot instances.

Polls a Teams chat for @claude mentions or quoted replies to bot messages,
processes them locally via Claude, and replies with results.

If the request is work (feature/fix/build), adds a TODO item to the tracked
git repo so the dispatcher/workers can pick it up.

Runs on a dedicated chatbot EC2 instance:
  - Graph token read from GRAPH_TOKEN_FILE (written by chatbot-daemon.sh)
  - Claude runs locally (no SSH dispatch to workers)
  - Work items committed to git repo at CHATBOT_TODO_REPO_DIR

Usage:
    python teams-chat-bridge.py --chat-id <TEAMS_CHAT_ID>
    python teams-chat-bridge.py --chat-id <ID> --trigger "@claude" --interval 30

Request lifecycle:
    received -> acked -> processing -> replied / failed
"""
import argparse
import json
import os
import re
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
STATE_PROCESSING = "processing"
STATE_REPLIED = "replied"
STATE_FAILED = "failed"

BOT_TAG = "[Claude Bot]"

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Keywords that indicate a work request (vs a question/status query)
WORK_KEYWORDS = [
    "implement", "add ", "create", "build", "fix", "refactor",
    "deploy", "update", "write", "develop", "make ", "set up",
    "integrate", "migrate", "configure", "install", "enable",
    "add feature", "new feature", "bug", "broken",
]

QUESTION_KEYWORDS = [
    "what", "how", "why", "when", "where", "who", "which",
    "show", "list", "explain", "describe", "status", "is ",
    "are ", "does ", "can ", "tell me", "help me understand",
]

# Phrases that indicate the user wants fleet/worker status
FLEET_STATUS_KEYWORDS = [
    "what are workers doing", "worker status", "fleet status",
    "what's happening", "whats happening", "what is happening",
    "status update", "what's running", "whats running",
    "show fleet", "fleet health", "workers busy",
    "any workers", "how many workers", "what are the workers",
    "current tasks", "active workers", "what workers",
    "are workers", "worker progress",
]

# ── State persistence ────────────────────────────────────────────────────────

STATE_FILE = os.environ.get(
    "CHATBOT_STATE_FILE",
    os.path.join(os.environ.get("TEMP", "/tmp"), "teams-chat-bridge-state.json")
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
            "Run via chatbot-daemon.sh or set the env var to a token JSON file."
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


# ── Teams helpers ────────────────────────────────────────────────────────────

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
    text = re.sub(r"<attachment[^>]*>.*?</attachment>", "", body_html,
                  flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text).strip()
    return text


# ── Local Claude execution ───────────────────────────────────────────────────

def run_claude_locally(prompt, workspace=None, timeout=300):
    """Run claude -p locally and return the output string."""
    workspace = workspace or os.environ.get("CHATBOT_TODO_REPO_DIR", "/workspace/claude-portable")
    escaped = prompt.replace("'", "'\\''")
    try:
        r = subprocess.run(
            ["claude", "-p", prompt, "--dangerously-skip-permissions"],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workspace,
        )
        output = r.stdout.strip()
        if r.returncode != 0 and not output:
            stderr = r.stderr.strip()
            return f"Claude returned exit code {r.returncode}. {stderr[:200]}" if stderr else \
                   f"Claude returned exit code {r.returncode}."
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Request timed out after {timeout}s."
    except FileNotFoundError:
        return "claude CLI not found. Is Claude Code installed?"
    except Exception as e:
        return f"Error running Claude: {e}"


# ── Work detection and TODO submission ───────────────────────────────────────

def is_work_request(prompt):
    """Heuristic: return True if the prompt sounds like a feature/fix/build request."""
    lower = prompt.lower().strip()
    # If it's clearly a question, not work
    question_count = sum(1 for kw in QUESTION_KEYWORDS if lower.startswith(kw) or f" {kw}" in lower)
    work_count = sum(1 for kw in WORK_KEYWORDS if kw in lower)
    # Phrases that explicitly request implementation
    explicit_work = any(p in lower for p in [
        "can you add", "can you fix", "can you create", "can you build",
        "please add", "please fix", "please create", "please build",
        "i need", "we need", "add a", "create a", "build a", "fix the",
    ])
    if explicit_work:
        return True
    return work_count > 0 and question_count == 0


def is_fleet_status_query(prompt):
    """Return True if the prompt is asking for fleet/worker status."""
    lower = prompt.lower().strip()
    return any(kw in lower for kw in FLEET_STATUS_KEYWORDS)


def get_fleet_status(repo_dir, dispatcher_url=None):
    """Collect fleet status from git + optional dispatcher health endpoint.

    Gathers:
    - TODO.md progress (done/pending)
    - Open PRs (gh pr list)
    - Active worker/chatbot branches (git branch -r)
    - Recent commits (git log)
    - Dispatcher health (if DISPATCHER_URL is set)

    Returns a formatted multi-line string.
    """
    lines = ["=== Fleet Status ===", ""]

    # Sync latest before reading
    try:
        subprocess.run(
            ["git", "pull", "--rebase", "--autostash"],
            cwd=repo_dir, capture_output=True, timeout=30,
        )
    except Exception:
        pass

    # TODO progress
    try:
        with open(os.path.join(repo_dir, "TODO.md")) as f:
            content = f.read()
        done = content.count("- [x]")
        pending = content.count("- [ ]")
        lines.append(f"Tasks: {done} done / {pending} pending")
    except Exception as e:
        lines.append(f"Tasks: (could not read TODO.md: {e})")

    lines.append("")

    # Open PRs
    try:
        r = subprocess.run(
            ["gh", "pr", "list", "--state", "open", "--limit", "20",
             "--json", "number,title,headRefName,author"],
            capture_output=True, text=True, timeout=30, cwd=repo_dir,
        )
        if r.returncode == 0 and r.stdout.strip():
            prs = json.loads(r.stdout)
            if prs:
                lines.append(f"Open PRs ({len(prs)} in progress):")
                for pr in prs:
                    author = (pr.get("author") or {}).get("login", "?")
                    title = pr.get("title", "?")[:60]
                    lines.append(f"  #{pr['number']} {title} [{author}]")
            else:
                lines.append("Open PRs: (none)")
        else:
            lines.append("Open PRs: (gh unavailable)")
    except Exception as e:
        lines.append(f"Open PRs: (error: {e})")

    lines.append("")

    # Active worker/chatbot branches
    try:
        r = subprocess.run(
            ["git", "branch", "-r"],
            capture_output=True, text=True, timeout=15, cwd=repo_dir,
        )
        if r.returncode == 0:
            branches = [
                b.strip().replace("origin/", "")
                for b in r.stdout.splitlines()
                if "continuous-claude/" in b or "chatbot/" in b
            ]
            if branches:
                lines.append(f"Active branches ({len(branches)}):")
                for b in branches[:10]:
                    lines.append(f"  {b}")
            else:
                lines.append("Active branches: (none)")
    except Exception as e:
        lines.append(f"Active branches: (error: {e})")

    lines.append("")

    # Recent commits
    try:
        r = subprocess.run(
            ["git", "log", "--oneline", "-8"],
            capture_output=True, text=True, timeout=15, cwd=repo_dir,
        )
        if r.returncode == 0 and r.stdout.strip():
            lines.append("Recent commits:")
            for line in r.stdout.strip().splitlines():
                lines.append(f"  {line}")
    except Exception as e:
        lines.append(f"Recent commits: (error: {e})")

    # Dispatcher health
    disp_url = dispatcher_url or os.environ.get("DISPATCHER_URL", "")
    if disp_url:
        lines.append("")
        lines.append("Dispatcher health:")
        try:
            health_url = disp_url.rstrip("/") + "/health"
            req = urllib.request.Request(
                health_url,
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                health = json.loads(resp.read().decode())
            lines.append(f"  Status: {health.get('status', '?')}")
            if "workers" in health:
                workers = health["workers"]
                lines.append(f"  Workers: {len(workers)} registered")
                for w in workers[:5]:
                    ip = w.get("ip", "?")
                    reachable = "up" if w.get("reachable") else "down"
                    lines.append(f"    {ip}: {reachable}")
            pending = health.get("pending_requests", [])
            if pending:
                lines.append(f"  Pending requests: {len(pending)}")
            if "error_count" in health:
                lines.append(f"  Error count: {health['error_count']}")
        except Exception as e:
            lines.append(f"  (could not reach dispatcher at {disp_url}: {e})")

    return "\n".join(lines)


def add_todo_item(prompt, sender, repo_dir=None):
    """Add a TODO item to TODO.md: create branch → commit → open PR → merge.

    Returns (success, pr_url_or_error_message).
    """
    repo_dir = repo_dir or os.environ.get("CHATBOT_TODO_REPO_DIR", "/workspace/claude-portable")
    todo_path = os.path.join(repo_dir, "TODO.md")

    if not os.path.isfile(todo_path):
        return False, f"TODO.md not found at {todo_path}"

    # Generate short task description from prompt (first 80 chars, cleaned up)
    task_desc = prompt.strip()
    # Remove common prefixes
    for prefix in ["can you ", "please ", "could you ", "i need you to ", "we need "]:
        if task_desc.lower().startswith(prefix):
            task_desc = task_desc[len(prefix):]
            break
    # Capitalize first letter
    task_desc = task_desc[:1].upper() + task_desc[1:] if task_desc else task_desc
    # Truncate at 80 chars at a word boundary
    if len(task_desc) > 80:
        task_desc = task_desc[:77].rsplit(" ", 1)[0] + "..."

    pr_title = f"feat: {task_desc[:60].lower()}"
    todo_item = f"- [ ] {task_desc} (requested by {sender})\n  - PR title: \"{pr_title}\"\n"

    branch = f"chatbot/request-{uuid.uuid4().hex[:6]}"

    try:
        # Configure git if needed
        subprocess.run(["git", "config", "user.name", "claude-chatbot"],
                       cwd=repo_dir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "noreply@claude-portable"],
                       cwd=repo_dir, capture_output=True)

        # Ensure we're on main and up to date
        subprocess.run(["git", "checkout", "main"],
                       cwd=repo_dir, capture_output=True, timeout=15)
        subprocess.run(["git", "pull", "--rebase", "--autostash"],
                       cwd=repo_dir, capture_output=True, timeout=30)

        # Create a feature branch
        branch_result = subprocess.run(
            ["git", "checkout", "-b", branch],
            cwd=repo_dir, capture_output=True, text=True, timeout=15
        )
        if branch_result.returncode != 0:
            return False, f"Git branch failed: {branch_result.stderr.strip()[:200]}"

        # Read current TODO.md, append item to a "Chatbot Requests" section
        with open(todo_path) as f:
            content = f.read()

        section_header = "\n## Chatbot Requests\n\n"
        if section_header.strip() in content:
            content = content.rstrip("\n") + "\n" + todo_item + "\n"
        else:
            content = content.rstrip("\n") + section_header + todo_item + "\n"

        with open(todo_path, "w") as f:
            f.write(content)

        # Commit
        subprocess.run(["git", "add", "TODO.md"], cwd=repo_dir, capture_output=True)
        commit_msg = f"feat: add chatbot request from {sender}\n\n{task_desc[:100]}"
        commit_result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=repo_dir, capture_output=True, text=True, timeout=15
        )
        if commit_result.returncode != 0:
            return False, f"Git commit failed: {commit_result.stderr.strip()[:200]}"

        # Push branch
        push_result = subprocess.run(
            ["git", "push", "-u", "origin", branch],
            cwd=repo_dir, capture_output=True, text=True, timeout=30
        )
        if push_result.returncode != 0:
            return False, f"Git push failed: {push_result.stderr.strip()[:200]}"

        # Open PR
        pr_body = f"Feature request from {sender}:\n\n> {prompt[:500]}\n\nAdded to TODO.md for worker pickup."
        pr_result = subprocess.run(
            ["gh", "pr", "create", "--title", pr_title, "--body", pr_body],
            cwd=repo_dir, capture_output=True, text=True, timeout=30
        )
        if pr_result.returncode != 0:
            return False, f"gh pr create failed: {pr_result.stderr.strip()[:200]}"

        pr_url = pr_result.stdout.strip()

        # Merge PR immediately (chatbot TODO PRs are always safe to merge)
        merge_result = subprocess.run(
            ["gh", "pr", "merge", "--squash", "--delete-branch"],
            cwd=repo_dir, capture_output=True, text=True, timeout=60
        )
        if merge_result.returncode != 0:
            # PR was created but not merged — still report it
            return True, pr_url

        # Return to main
        subprocess.run(["git", "checkout", "main"],
                       cwd=repo_dir, capture_output=True, timeout=15)
        subprocess.run(["git", "pull", "--rebase"],
                       cwd=repo_dir, capture_output=True, timeout=30)

        return True, pr_url
    except subprocess.TimeoutExpired:
        return False, "Git operation timed out"
    except Exception as e:
        return False, f"Git error: {e}"


# ── Health endpoint ──────────────────────────────────────────────────────────

HEALTH_PORT = int(os.environ.get("CHATBOT_HEALTH_PORT", "8080"))

_health_lock = threading.Lock()
_health_state = {
    "status": "starting",
    "last_poll": None,
    "graph_token_valid": None,
    "pending_requests": [],
    "error_count": 0,
    "mode": "chatbot",
}


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
        }
        for rid, req in requests.items()
        if req["state"] in (STATE_ACKED, STATE_PROCESSING)
    ]

    token_ok = _graph_token_valid()
    overall = "ok" if token_ok else "degraded"

    with _health_lock:
        _health_state["status"] = overall
        _health_state["last_poll"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _health_state["graph_token_valid"] = token_ok
        _health_state["pending_requests"] = pending
        _health_state["error_count"] = error_count


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/health", "/"):
            with _health_lock:
                data = dict(_health_state)
            data["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            body = json.dumps(data, indent=2).encode()
            http_status = 200 if data["status"] == "ok" else 503
            self.send_response(http_status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass


def start_health_server(port=HEALTH_PORT):
    """Start HTTP health server in a background daemon thread."""
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True, name="health-server")
    t.start()
    print(f"  Health: http://0.0.0.0:{port}/health")
    return server


# ── Poll loop ────────────────────────────────────────────────────────────────

def poll_once(chat_id, trigger, state, workspace=None):
    """Single poll iteration: check for new messages, process via Claude, reply."""
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

        # If no trigger, check for a quoted reply to a bot message
        if not is_trigger and is_reply_to_bot(m):
            reply_text = extract_reply_text(body_html)
            if reply_text:
                prompt, is_trigger = reply_text, True

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
        }
        requests[request_id] = req
        new_requests.append(req)
        print(f"\n  [{time.strftime('%H:%M:%S')}] REQ {request_id} from {sender}: {prompt[:80]}")

    # --- Phase 2: ACK and process new requests ---
    for req in new_requests:
        rid = req["id"]
        prompt = req["prompt"]
        sender = req["sender"]

        # ACK in Teams
        ack_msg = f"Got it, {sender}! Processing your request..."
        if reply_in_teams(chat_id, ack_msg):
            req["state"] = STATE_ACKED
            print(f"  [{rid}] ACKed")

        req["state"] = STATE_PROCESSING

        # Fleet status queries are handled directly (no Claude round-trip needed)
        if is_fleet_status_query(prompt):
            print(f"  [{rid}] Fleet status query — collecting from git + dispatcher")
            result = get_fleet_status(workspace)
            print(f"  [{rid}] Fleet status collected ({len(result)} chars)")
        else:
            print(f"  [{rid}] Running Claude locally...")
            result = run_claude_locally(prompt, workspace=workspace)
            print(f"  [{rid}] Claude result: {result[:80]}")

        # Check if this is a work request that should be queued
        work_queued = False
        if is_work_request(prompt):
            print(f"  [{rid}] Detected work request — adding TODO item...")
            success, info = add_todo_item(prompt, sender, workspace)
            if success:
                work_queued = True
                queue_note = f"\n\nI've queued this as a TODO item. Workers will pick it up automatically. PR: {info}"
                print(f"  [{rid}] TODO item added, PR: {info}")
            else:
                queue_note = f"\n\n(Note: Failed to queue as TODO item: {info})"
                print(f"  [{rid}] WARNING: Failed to add TODO: {info}")
        else:
            queue_note = ""

        # Reply with result
        reply_text = result[:1800] + queue_note
        if reply_in_teams(chat_id, reply_text):
            req["state"] = STATE_REPLIED
            print(f"  [{rid}] Replied in Teams")
        else:
            req["state"] = STATE_FAILED
            print(f"  [{rid}] Failed to reply in Teams")

    # --- Cleanup old completed/failed requests (keep last 100) ---
    if len(requests) > 100:
        sorted_reqs = sorted(requests.items(), key=lambda x: x[1].get("timestamp", ""))
        for rid, req in sorted_reqs[:-100]:
            if req["state"] in (STATE_REPLIED, STATE_FAILED):
                del requests[rid]

    # Save state
    state["processed_msgs"] = list(processed)[-500:]
    state["requests"] = requests
    save_state(state)

    return len(new_requests)


def main():
    parser = argparse.ArgumentParser(
        description="Teams chat bridge (chatbot mode — processes locally via Claude)"
    )
    parser.add_argument("--chat-id", required=True, help="Teams chat ID to monitor")
    parser.add_argument("--trigger", default="@claude", help="Trigger keyword (default: @claude)")
    parser.add_argument("--interval", type=int, default=30,
                        help="Poll interval seconds (default: 30)")
    parser.add_argument("--workspace", default=None,
                        help="Working directory for Claude (default: CHATBOT_TODO_REPO_DIR or /workspace/claude-portable)")
    args = parser.parse_args()

    # Validate required env var early
    if not os.environ.get("GRAPH_TOKEN_FILE"):
        print("ERROR: GRAPH_TOKEN_FILE env var is not set.", file=sys.stderr)
        print("  Run via chatbot-daemon.sh, or set GRAPH_TOKEN_FILE to a token JSON file.",
              file=sys.stderr)
        sys.exit(1)

    workspace = args.workspace or os.environ.get(
        "CHATBOT_TODO_REPO_DIR", "/workspace/claude-portable"
    )

    print("=" * 55)
    print(f"  {BOT_TAG} Teams Chat Bridge (chatbot mode)")
    print("=" * 55)
    print(f"  Chat:       {args.chat_id[:35]}...")
    print(f"  Trigger:    {args.trigger}")
    print(f"  Poll:       every {args.interval}s")
    print(f"  Workspace:  {workspace}")
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
            new = poll_once(args.chat_id, args.trigger, state, workspace)
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
