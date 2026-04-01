#!/usr/bin/env python3
"""
dispatcher-brain.py -- Persistent AI dispatcher brain for CCC fleet management.

Long-running process that uses AWS Bedrock (Claude) with tool_use to:
  - Check inbox sources (dispatcher API, GitHub issues)
  - Think about what needs doing
  - Act via tools (dispatch tasks, merge PRs, heal infrastructure)
  - Remember conversation history across iterations

Runs forever: check inbox -> think -> act -> remember -> sleep 30s

Environment:
  USE_BEDROCK=1           Use AWS Bedrock (default, creds from EC2 instance role)
  AWS_DEFAULT_REGION      Bedrock region (default: us-east-2)
  BRAIN_MODEL_ID          Bedrock model ID (default: us.anthropic.claude-sonnet-4-6-20250514-v1:0)
  BRAIN_HISTORY_FILE      Conversation history path (default: /tmp/brain-history.json)
  BRAIN_HEALTH_PORT       Health endpoint port (default: 8081)
  BRAIN_LOOP_INTERVAL     Seconds between loops (default: 30)
  BRAIN_MAX_TOKENS        Max history tokens before truncation (default: 100000)
  DISPATCHER_API_URL      Dispatcher API base URL (default: http://localhost:8080)
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

LOG_FORMAT = "%(asctime)s [brain] %(levelname)s %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt="%H:%M:%S")
log = logging.getLogger("brain")

# ── Config ─────────────────────────────────────────────────────────────────────

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
MODEL_ID = os.environ.get("BRAIN_MODEL_ID", "us.anthropic.claude-3-5-haiku-20241022-v1:0")
HISTORY_FILE = os.environ.get("BRAIN_HISTORY_FILE", "/tmp/brain-history.json")
HEALTH_PORT = int(os.environ.get("BRAIN_HEALTH_PORT", "8081"))
LOOP_INTERVAL = int(os.environ.get("BRAIN_LOOP_INTERVAL", "30"))
MAX_HISTORY_TOKENS = int(os.environ.get("BRAIN_MAX_TOKENS", "100000"))
DISPATCHER_API = os.environ.get("DISPATCHER_API_URL", "http://localhost:8080")

# ── Stats (thread-safe) ───────────────────────────────────────────────────────

_stats_lock = threading.Lock()
_stats = {
    "start_time": time.time(),
    "last_check_time": None,
    "loops_completed": 0,
    "tasks_dispatched": 0,
    "prs_merged": 0,
    "errors": 0,
    "last_error": None,
    "status": "starting",
}


def _update_stats(**kwargs):
    with _stats_lock:
        _stats.update(kwargs)


def _inc_stat(key, n=1):
    with _stats_lock:
        _stats[key] = _stats.get(key, 0) + n


# ── Token estimation ──────────────────────────────────────────────────────────

def estimate_tokens(text):
    """Rough: 1 token ~ 4 chars."""
    if isinstance(text, str):
        return len(text) // 4
    return len(json.dumps(text)) // 4


# ── Conversation history ──────────────────────────────────────────────────────

def load_history():
    """Load conversation history from disk."""
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_history(messages):
    """Save conversation history to disk."""
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(messages, f, indent=1)
    except OSError as e:
        log.error("Failed to save history: %s", e)


def truncate_history(messages):
    """Truncate history if it exceeds MAX_HISTORY_TOKENS."""
    total = sum(estimate_tokens(m) for m in messages)
    if total <= MAX_HISTORY_TOKENS:
        return messages
    # Keep system-like context (first message) and trim from the front
    # Keep last 2/3 of messages
    while total > MAX_HISTORY_TOKENS and len(messages) > 4:
        removed = messages.pop(0)
        total -= estimate_tokens(removed)
    log.info("Truncated history to %d messages (~%d tokens)", len(messages), total)
    return messages


# ── Tool implementations ──────────────────────────────────────────────────────

def _run_cmd(cmd, timeout=30):
    """Run a shell command and return (stdout, stderr, returncode)."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", 1
    except Exception as e:
        return "", str(e), 1


def _http_get(url, timeout=10):
    """Simple HTTP GET using urllib."""
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def _http_post(url, data, timeout=10):
    """Simple HTTP POST using urllib."""
    import urllib.request
    import urllib.error
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def tool_dispatch_task(text, target_repo):
    """Submit a task to the dispatcher API."""
    result = _http_post(f"{DISPATCHER_API}/submit", {
        "text": text,
        "target_repo": target_repo,
    })
    if "error" not in result:
        _inc_stat("tasks_dispatched")
    return result


def tool_merge_pr(repo, pr_number):
    """Merge a PR with squash and auto-merge."""
    out, err, rc = _run_cmd(f"gh pr merge {pr_number} --repo {repo} --squash --auto")
    if rc == 0:
        _inc_stat("prs_merged")
    return {"stdout": out, "stderr": err, "returncode": rc}


def tool_check_fleet_health():
    """Check dispatcher health endpoint and parse worker states."""
    return _http_get(f"{DISPATCHER_API}/health")


def tool_register_worker(name, ip):
    """Register a worker with the dispatcher."""
    return _http_post(f"{DISPATCHER_API}/worker/register", {
        "name": name,
        "ip": ip,
    })


def tool_list_open_prs(repo):
    """List open PRs for a repo."""
    out, err, rc = _run_cmd(
        f"gh pr list --repo {repo} --state open --json number,title,author,createdAt,statusCheckRollup"
    )
    if rc == 0 and out:
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return {"raw": out}
    return {"error": err or "no output", "returncode": rc}


def tool_send_teams_message(text):
    """Send a message to Teams via team-chat.py."""
    out, err, rc = _run_cmd(
        f"python3 /workspace/hackathon26/scripts/team-chat.py '{text}'",
        timeout=15,
    )
    return {"stdout": out, "stderr": err, "returncode": rc}


def tool_run_shell(command):
    """Run a shell command for fleet ops."""
    out, err, rc = _run_cmd(command, timeout=60)
    return {"stdout": out, "stderr": err, "returncode": rc}


def tool_comment_on_issue(repo, number, body):
    """Comment on a GitHub issue."""
    # Escape body for shell
    safe_body = body.replace("'", "'\\''")
    out, err, rc = _run_cmd(f"gh issue comment {number} --repo {repo} --body '{safe_body}'")
    return {"stdout": out, "stderr": err, "returncode": rc}


def tool_close_issue(repo, number):
    """Close a GitHub issue."""
    out, err, rc = _run_cmd(f"gh issue close {number} --repo {repo}")
    return {"stdout": out, "stderr": err, "returncode": rc}


def tool_pull_latest(repo_path):
    """Pull latest code on a local repo."""
    out, err, rc = _run_cmd(f"cd {repo_path} && git fetch origin main && git reset --hard origin/main")
    return {"stdout": out, "stderr": err, "returncode": rc}


# ── Tool registry (Bedrock tool_use format) ───────────────────────────────────

TOOL_MAP = {
    "dispatch_task": tool_dispatch_task,
    "merge_pr": tool_merge_pr,
    "check_fleet_health": tool_check_fleet_health,
    "register_worker": tool_register_worker,
    "list_open_prs": tool_list_open_prs,
    "send_teams_message": tool_send_teams_message,
    "run_shell": tool_run_shell,
    "comment_on_issue": tool_comment_on_issue,
    "close_issue": tool_close_issue,
    "pull_latest": tool_pull_latest,
}

TOOL_DEFINITIONS = [
    {
        "name": "dispatch_task",
        "description": "Submit a task to the dispatcher API for a worker to execute.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Task description"},
                "target_repo": {"type": "string", "description": "Target repository (e.g. altarr/boothapp)"},
            },
            "required": ["text", "target_repo"],
        },
    },
    {
        "name": "merge_pr",
        "description": "Merge a pull request with squash and auto-merge.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository (e.g. grobomo/claude-portable)"},
                "pr_number": {"type": "integer", "description": "PR number"},
            },
            "required": ["repo", "pr_number"],
        },
    },
    {
        "name": "check_fleet_health",
        "description": "Check dispatcher health endpoint and parse worker states.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "register_worker",
        "description": "Register a worker instance with the dispatcher.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Worker name/ID"},
                "ip": {"type": "string", "description": "Worker IP address"},
            },
            "required": ["name", "ip"],
        },
    },
    {
        "name": "list_open_prs",
        "description": "List open pull requests for a repository.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository (e.g. grobomo/claude-portable)"},
            },
            "required": ["repo"],
        },
    },
    {
        "name": "send_teams_message",
        "description": "Send a message to Teams channel (as Coconut). Only for breakages or major milestones.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Message text"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "run_shell",
        "description": "Run a shell command for fleet operations (ssh to workers, docker exec, etc).",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "comment_on_issue",
        "description": "Add a comment to a GitHub issue.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository (e.g. altarr/boothapp)"},
                "number": {"type": "integer", "description": "Issue number"},
                "body": {"type": "string", "description": "Comment body"},
            },
            "required": ["repo", "number", "body"],
        },
    },
    {
        "name": "close_issue",
        "description": "Close a GitHub issue.",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo": {"type": "string", "description": "Repository (e.g. altarr/boothapp)"},
                "number": {"type": "integer", "description": "Issue number"},
            },
            "required": ["repo", "number"],
        },
    },
    {
        "name": "pull_latest",
        "description": "Pull latest code on dispatcher's local repo (git fetch + reset).",
        "input_schema": {
            "type": "object",
            "properties": {
                "repo_path": {"type": "string", "description": "Local path to repository"},
            },
            "required": ["repo_path"],
        },
    },
]

# ── System prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are the dispatcher brain for a CCC (Claude Code Container) fleet. You manage workers, merge PRs, heal infrastructure, and keep the system running smoothly.

Your responsibilities:
- Check inbox every 30s. If tasks are pending, decompose and dispatch them to workers.
- If PRs are open and CI passes, merge them.
- If workers are stopping/dead, re-register them. If IAM creds expired, refresh.
- After merging PRs, pull latest code on dispatcher so watcher has fresh analysis code.
- When idle with no tasks: review recent PRs for quality, check if any workers need maintenance, think about what the system should build next to improve itself.
- Post to Teams (as Coconut) ONLY when something breaks or a major milestone completes. No status spam.
- Never implement code yourself. Always dispatch to workers.

Monitored repositories:
- altarr/boothapp (filter GitHub issues with 'task' label)
- grobomo/hackathon26 (filter GitHub issues with 'task' label)
- grobomo/claude-portable (fleet infrastructure)

When you receive inbox data, analyze it and decide:
1. Are there pending tasks? -> dispatch_task
2. Are there open PRs with passing CI? -> merge_pr
3. Are workers unhealthy? -> register_worker or run_shell to fix
4. Is everything idle? -> briefly note "idle, all clear" and move on

Be concise in your reasoning. Focus on actions, not explanations."""


# ── Inbox collection ──────────────────────────────────────────────────────────

def collect_inbox():
    """Gather pending work from all inbox sources."""
    inbox = {}

    # 1. Dispatcher API queue
    try:
        api_tasks = _http_get(f"{DISPATCHER_API}/api/tasks")
        if isinstance(api_tasks, list):
            pending = [t for t in api_tasks if t.get("state") == "pending"]
        elif isinstance(api_tasks, dict) and "tasks" in api_tasks:
            pending = [t for t in api_tasks["tasks"] if t.get("state") == "pending"]
        else:
            pending = []
        inbox["dispatcher_tasks"] = pending
    except Exception as e:
        inbox["dispatcher_tasks_error"] = str(e)

    # 2. GitHub issues: altarr/boothapp
    for repo in ("altarr/boothapp", "grobomo/hackathon26"):
        key = repo.replace("/", "_") + "_issues"
        out, err, rc = _run_cmd(
            f"gh issue list --repo {repo} --state open --label task "
            f"--json number,title,body,labels 2>/dev/null"
        )
        if rc == 0 and out:
            try:
                issues = json.loads(out)
                inbox[key] = issues
            except json.JSONDecodeError:
                inbox[key] = []
        else:
            inbox[key] = []

    # 3. Fleet health snapshot
    try:
        health = _http_get(f"{DISPATCHER_API}/health")
        if "error" not in health:
            inbox["fleet_health"] = {
                "workers": health.get("fleet_roster", {}),
                "uptime": health.get("uptime_seconds"),
            }
    except Exception:
        pass

    # 4. Open PRs across repos
    for repo in ("grobomo/claude-portable", "altarr/boothapp", "grobomo/hackathon26"):
        key = repo.replace("/", "_") + "_prs"
        out, err, rc = _run_cmd(
            f"gh pr list --repo {repo} --state open "
            f"--json number,title,author,statusCheckRollup 2>/dev/null"
        )
        if rc == 0 and out:
            try:
                inbox[key] = json.loads(out)
            except json.JSONDecodeError:
                inbox[key] = []
        else:
            inbox[key] = []

    return inbox


# ── Bedrock API (Converse API) ────────────────────────────────────────────────

_bedrock_client = None


def _get_bedrock_client():
    """Lazy-init Bedrock runtime client."""
    global _bedrock_client
    if _bedrock_client is None:
        import boto3
        _bedrock_client = boto3.client("bedrock-runtime", region_name=REGION)
    return _bedrock_client


def _to_converse_messages(messages):
    """Convert internal message format to Bedrock Converse API format.

    Internal format uses Anthropic-style messages (text strings or content blocks).
    Converse API requires: content = [{"text": "..."} | {"toolUse": ...} | {"toolResult": ...}]
    """
    result = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if isinstance(content, str):
            result.append({"role": role, "content": [{"text": content}]})
        elif isinstance(content, list):
            blocks = []
            for block in content:
                if isinstance(block, str):
                    blocks.append({"text": block})
                elif block.get("type") == "text":
                    blocks.append({"text": block.get("text", "")})
                elif block.get("type") == "tool_use":
                    blocks.append({
                        "toolUse": {
                            "toolUseId": block["id"],
                            "name": block["name"],
                            "input": block.get("input", {}),
                        }
                    })
                elif block.get("type") == "tool_result":
                    blocks.append({
                        "toolResult": {
                            "toolUseId": block["tool_use_id"],
                            "content": [{"text": block.get("content", "")}],
                        }
                    })
                else:
                    blocks.append({"text": json.dumps(block)})
            if blocks:
                result.append({"role": role, "content": blocks})
        else:
            result.append({"role": role, "content": [{"text": str(content)}]})

    return result


def _to_converse_tools(tools):
    """Convert Anthropic-style tool defs to Converse API toolSpec format."""
    specs = []
    for t in tools:
        specs.append({
            "toolSpec": {
                "name": t["name"],
                "description": t["description"],
                "inputSchema": {"json": t["input_schema"]},
            }
        })
    return specs


def call_bedrock(messages, system=None, tools=None):
    """Call AWS Bedrock Converse API with Claude model."""
    client = _get_bedrock_client()

    kwargs = {
        "modelId": MODEL_ID,
        "messages": _to_converse_messages(messages),
        "inferenceConfig": {"maxTokens": 4096},
    }

    if system:
        kwargs["system"] = [{"text": system}]

    if tools:
        kwargs["toolConfig"] = {"tools": _to_converse_tools(tools)}

    resp = client.converse(**kwargs)

    # Convert Converse response back to Anthropic-style format
    output = resp.get("output", {}).get("message", {})
    stop_reason_map = {"end_turn": "end_turn", "tool_use": "tool_use", "max_tokens": "max_tokens"}
    raw_stop = resp.get("stopReason", "end_turn")
    stop_reason = stop_reason_map.get(raw_stop, raw_stop)

    content_blocks = []
    for block in output.get("content", []):
        if "text" in block:
            content_blocks.append({"type": "text", "text": block["text"]})
        elif "toolUse" in block:
            tu = block["toolUse"]
            content_blocks.append({
                "type": "tool_use",
                "id": tu["toolUseId"],
                "name": tu["name"],
                "input": tu.get("input", {}),
            })

    return {"stop_reason": stop_reason, "content": content_blocks}


# ── Tool execution loop ───────────────────────────────────────────────────────

def execute_tool(name, input_data):
    """Execute a tool by name with given input."""
    func = TOOL_MAP.get(name)
    if not func:
        return {"error": f"Unknown tool: {name}"}

    try:
        # Map input keys to function parameters
        if name == "dispatch_task":
            return func(input_data["text"], input_data["target_repo"])
        elif name == "merge_pr":
            return func(input_data["repo"], input_data["pr_number"])
        elif name == "check_fleet_health":
            return func()
        elif name == "register_worker":
            return func(input_data["name"], input_data["ip"])
        elif name == "list_open_prs":
            return func(input_data["repo"])
        elif name == "send_teams_message":
            return func(input_data["text"])
        elif name == "run_shell":
            return func(input_data["command"])
        elif name == "comment_on_issue":
            return func(input_data["repo"], input_data["number"], input_data["body"])
        elif name == "close_issue":
            return func(input_data["repo"], input_data["number"])
        elif name == "pull_latest":
            return func(input_data["repo_path"])
        else:
            return {"error": f"No handler for tool: {name}"}
    except Exception as e:
        return {"error": str(e)}


def run_conversation_turn(messages, inbox_summary):
    """Run one turn of the brain conversation with tool use loop."""
    # Add inbox as user message
    user_msg = {
        "role": "user",
        "content": f"[INBOX CHECK @ {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}]\n\n"
                   f"{json.dumps(inbox_summary, indent=1, default=str)}"
    }
    messages.append(user_msg)

    # Conversation loop (handle tool_use responses)
    max_tool_rounds = 10
    for _ in range(max_tool_rounds):
        try:
            response = call_bedrock(
                messages=messages,
                system=SYSTEM_PROMPT,
                tools=TOOL_DEFINITIONS,
            )
        except Exception as e:
            log.error("Bedrock API error: %s", e)
            _inc_stat("errors")
            _update_stats(last_error=str(e))
            # Add error as assistant message so history stays valid
            messages.append({
                "role": "assistant",
                "content": [{"type": "text", "text": f"[API error: {e}]"}],
            })
            break

        stop_reason = response.get("stop_reason", "end_turn")
        content_blocks = response.get("content", [])

        # Add assistant response to history
        messages.append({"role": "assistant", "content": content_blocks})

        # Log any text output
        for block in content_blocks:
            if block.get("type") == "text" and block.get("text"):
                log.info("Brain: %s", block["text"][:200])

        # If no tool use, we're done
        if stop_reason != "tool_use":
            break

        # Execute tools and add results
        tool_results = []
        for block in content_blocks:
            if block.get("type") == "tool_use":
                tool_name = block["name"]
                tool_input = block.get("input", {})
                tool_id = block["id"]

                log.info("Tool call: %s(%s)", tool_name, json.dumps(tool_input)[:100])
                result = execute_tool(tool_name, tool_input)
                log.info("Tool result: %s", json.dumps(result)[:200])

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps(result, default=str),
                })

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    return messages


# ── Health endpoint ───────────────────────────────────────────────────────────

class BrainHealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/api/brain-status", "/health", "/"):
            with _stats_lock:
                data = dict(_stats)
            data["uptime_seconds"] = int(time.time() - data.pop("start_time", time.time()))
            body = json.dumps(data, indent=2, default=str).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress request logs


def start_health_server():
    """Start health endpoint in a background thread."""
    server = HTTPServer(("0.0.0.0", HEALTH_PORT), BrainHealthHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    log.info("Health endpoint listening on port %d", HEALTH_PORT)
    return server


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    log.info("=== Dispatcher Brain Starting ===")
    log.info("  Model:    %s", MODEL_ID)
    log.info("  Region:   %s", REGION)
    log.info("  History:  %s", HISTORY_FILE)
    log.info("  Health:   :%d", HEALTH_PORT)
    log.info("  Interval: %ds", LOOP_INTERVAL)
    log.info("")

    # Start health endpoint
    start_health_server()

    # Load conversation history
    messages = load_history()
    log.info("Loaded %d history messages", len(messages))

    _update_stats(status="running")

    loop_count = 0
    while True:
        try:
            loop_count += 1
            log.info("--- Loop %d ---", loop_count)

            # Collect inbox
            inbox = collect_inbox()
            _update_stats(last_check_time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

            # Summarize for logging
            n_tasks = len(inbox.get("dispatcher_tasks", []))
            n_issues = sum(
                len(inbox.get(k, []))
                for k in inbox
                if k.endswith("_issues")
            )
            n_prs = sum(
                len(inbox.get(k, []))
                for k in inbox
                if k.endswith("_prs")
            )
            log.info("Inbox: %d pending tasks, %d issues, %d open PRs", n_tasks, n_issues, n_prs)

            if n_tasks == 0 and n_issues == 0 and n_prs == 0:
                log.info("Idle -- no pending work")
                _update_stats(status="idle")
            else:
                _update_stats(status="working")

            # Run brain conversation turn
            messages = run_conversation_turn(messages, inbox)

            # Truncate and save history
            messages = truncate_history(messages)
            save_history(messages)

            _inc_stat("loops_completed")
            _update_stats(status="idle")

        except KeyboardInterrupt:
            log.info("Shutting down (keyboard interrupt)")
            break
        except Exception as e:
            log.error("Loop error: %s", e, exc_info=True)
            _inc_stat("errors")
            _update_stats(last_error=str(e), status="error")

        # Sleep between iterations
        time.sleep(LOOP_INTERVAL)


if __name__ == "__main__":
    main()
