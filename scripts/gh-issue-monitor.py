#!/usr/bin/env python3
"""
gh-issue-monitor.py -- GitHub issue monitor daemon for CCC.

Polls GitHub issues across configured repos every 60 seconds.
When a new issue is opened or reopened, submits it as a task to the dispatcher.
Tracks task_id. Posts result/error as issue comment when task completes/fails.
Handles issue comments as follow-up tasks.

Usage:
    python3 scripts/gh-issue-monitor.py
    python3 scripts/gh-issue-monitor.py --repos grobomo/claude-portable altarr/boothapp
    python3 scripts/gh-issue-monitor.py --dispatcher-url https://16.58.49.156
    python3 scripts/gh-issue-monitor.py --poll-interval 30

Environment variables:
    GH_ISSUE_DISPATCHER_URL   Dispatcher base URL (default: https://16.58.49.156)
    GH_ISSUE_POLL_INTERVAL    Seconds between polls (default: 60)
    GH_ISSUE_REPOS            Comma-separated repos (default: altarr/boothapp,grobomo/claude-portable)
    DISPATCH_API_TOKEN        Bearer token for dispatcher API (optional)
    GH_ISSUE_STATE_FILE       Path to persist state (default: /data/gh-issue-monitor-state.json)
"""

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt="%H:%M:%S")
log = logging.getLogger("gh-issue-monitor")

# ── Config ─────────────────────────────────────────────────────────────────────

DEFAULT_REPOS = ["altarr/boothapp", "grobomo/claude-portable"]
DEFAULT_DISPATCHER_URL = "https://16.58.49.156"
DEFAULT_POLL_INTERVAL = 60
DEFAULT_STATE_FILE = "/data/gh-issue-monitor-state.json"
TASK_POLL_INTERVAL = 15  # seconds between task status checks
BOT_MARKER = "<!-- gh-issue-monitor -->"

# ── State ──────────────────────────────────────────────────────────────────────

# Tracks which issues/comments we've already processed
# Format: {
#   "issues": {"repo#number": {"task_id": ..., "state": ..., "last_updated": ...}},
#   "comments": {"repo#number#comment_id": {"task_id": ..., "state": ...}},
#   "last_poll": {"repo": "2026-01-01T00:00:00Z"}
# }
_state = {"issues": {}, "comments": {}, "last_poll": {}}
_running = True


def _signal_handler(sig, frame):
    global _running
    log.info("Received signal %d, shutting down...", sig)
    _running = False


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


# ── State persistence ──────────────────────────────────────────────────────────

def load_state(path):
    global _state
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                _state = json.load(f)
            log.info("Loaded state: %d issues, %d comments tracked",
                     len(_state.get("issues", {})), len(_state.get("comments", {})))
        except (json.JSONDecodeError, IOError) as e:
            log.warning("Could not load state from %s: %s", path, e)
    # Ensure keys exist
    _state.setdefault("issues", {})
    _state.setdefault("comments", {})
    _state.setdefault("last_poll", {})


def save_state(path):
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(_state, f, indent=2)
    except IOError as e:
        log.warning("Could not save state to %s: %s", path, e)


# ── gh CLI helpers ─────────────────────────────────────────────────────────────

def gh_json(args):
    """Run gh CLI command and return parsed JSON output."""
    cmd = ["gh"] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            log.warning("gh command failed: %s\n  stderr: %s", " ".join(cmd), result.stderr.strip())
            return None
        if not result.stdout.strip():
            return []
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        log.warning("gh command timed out: %s", " ".join(cmd))
        return None
    except json.JSONDecodeError as e:
        log.warning("gh returned invalid JSON: %s", e)
        return None


def gh_run(args):
    """Run gh CLI command, return (returncode, stdout, stderr)."""
    cmd = ["gh"] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        log.warning("gh command timed out: %s", " ".join(cmd))
        return 1, "", "timeout"


def list_issues(repo, since=None):
    """List open issues for a repo. Returns list of issue dicts."""
    args = [
        "issue", "list",
        "--repo", repo,
        "--state", "open",
        "--json", "number,title,body,state,createdAt,updatedAt,author,labels,comments",
        "--limit", "50",
    ]
    issues = gh_json(args)
    return issues if issues else []


def list_issue_comments(repo, issue_number):
    """List comments on an issue."""
    args = [
        "api",
        f"repos/{repo}/issues/{issue_number}/comments",
        "--jq", ".",
    ]
    comments = gh_json(args)
    return comments if comments else []


def post_comment(repo, issue_number, body):
    """Post a comment on an issue."""
    # Prepend bot marker so we can identify our own comments
    full_body = f"{BOT_MARKER}\n{body}"
    rc, stdout, stderr = gh_run([
        "issue", "comment", str(issue_number),
        "--repo", repo,
        "--body", full_body,
    ])
    if rc != 0:
        log.error("Failed to post comment on %s#%d: %s", repo, issue_number, stderr.strip())
        return False
    log.info("Posted comment on %s#%d", repo, issue_number)
    return True


# ── Dispatcher API ─────────────────────────────────────────────────────────────

def dispatcher_submit(dispatcher_url, text, sender="gh-issue-monitor", token=None):
    """Submit a task to the dispatcher. Returns task dict or None."""
    import urllib.request
    import urllib.error
    import ssl

    url = f"{dispatcher_url}/api/submit"
    payload = json.dumps({"text": text, "sender": sender}).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # Allow self-signed certs for internal dispatcher
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            data = json.loads(resp.read())
            return data
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:200]
        log.error("Dispatcher submit failed (HTTP %d): %s", e.code, body)
        return None
    except Exception as e:
        log.error("Dispatcher submit error: %s", e)
        return None


def dispatcher_status(dispatcher_url, task_id, token=None):
    """Check task status. Returns task dict or None."""
    import urllib.request
    import urllib.error
    import ssl

    url = f"{dispatcher_url}/task/{task_id}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            return json.loads(resp.read())
    except Exception as e:
        log.warning("Dispatcher status check failed for %s: %s", task_id, e)
        return None


# ── Core logic ─────────────────────────────────────────────────────────────────

def build_task_text(repo, issue):
    """Build task description from issue."""
    number = issue["number"]
    title = issue["title"]
    body = (issue.get("body") or "").strip()
    author = issue.get("author", {}).get("login", "unknown")
    labels = ", ".join(l.get("name", "") for l in issue.get("labels", []))

    parts = [
        f"GitHub Issue: {repo}#{number}",
        f"Title: {title}",
        f"Author: {author}",
    ]
    if labels:
        parts.append(f"Labels: {labels}")
    if body:
        # Truncate very long bodies
        if len(body) > 2000:
            body = body[:2000] + "\n... (truncated)"
        parts.append(f"\n{body}")

    return "\n".join(parts)


def build_followup_text(repo, issue_number, issue_title, comment):
    """Build task description from a follow-up comment."""
    author = comment.get("user", {}).get("login", "unknown")
    body = (comment.get("body") or "").strip()
    if len(body) > 2000:
        body = body[:2000] + "\n... (truncated)"

    return (
        f"Follow-up on GitHub Issue: {repo}#{issue_number}\n"
        f"Original issue: {issue_title}\n"
        f"Comment by: {author}\n\n"
        f"{body}"
    )


def format_result_comment(task):
    """Format a task result as a GitHub comment."""
    state = task.get("state", "UNKNOWN")
    task_id = task.get("id", "?")

    if state == "COMPLETED":
        result = task.get("result", "Task completed successfully.")
        pr_url = task.get("pr_url", "")
        lines = [
            f"**Task completed** (id: `{task_id}`)",
            "",
            result,
        ]
        if pr_url:
            lines.extend(["", f"PR: {pr_url}"])
        return "\n".join(lines)
    elif state == "FAILED":
        error = task.get("error", "Unknown error")
        return (
            f"**Task failed** (id: `{task_id}`)\n\n"
            f"Error: {error}"
        )
    elif state == "CANCELLED":
        return f"**Task cancelled** (id: `{task_id}`)"
    else:
        return f"**Task status: {state}** (id: `{task_id}`)"


def process_issues(repos, dispatcher_url, token, state_file):
    """Poll repos for new/reopened issues and new comments."""
    for repo in repos:
        issues = list_issues(repo)
        if issues is None:
            continue

        for issue in issues:
            number = issue["number"]
            key = f"{repo}#{number}"
            updated_at = issue.get("updatedAt", "")

            # Check if this is a new issue we haven't seen
            if key not in _state["issues"]:
                log.info("New issue: %s -- %s", key, issue["title"])
                task_text = build_task_text(repo, issue)
                result = dispatcher_submit(dispatcher_url, task_text, sender=key, token=token)
                if result:
                    task_id = result.get("id", "")
                    _state["issues"][key] = {
                        "task_id": task_id,
                        "state": result.get("state", "PENDING"),
                        "title": issue["title"],
                        "last_updated": updated_at,
                        "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }
                    post_comment(repo, number,
                                 f"Task submitted to CCC dispatcher (id: `{task_id}`). Tracking...")
                    log.info("Submitted task %s for %s", task_id, key)
                else:
                    log.error("Failed to submit task for %s", key)
                    _state["issues"][key] = {
                        "task_id": None,
                        "state": "SUBMIT_FAILED",
                        "title": issue["title"],
                        "last_updated": updated_at,
                    }
                save_state(state_file)
                continue

            # Issue exists in state -- check if reopened (was terminal, now open again)
            tracked = _state["issues"][key]
            if tracked.get("state") in ("COMPLETED", "FAILED", "CANCELLED", "SUBMIT_FAILED") \
                    and tracked.get("result_posted"):
                log.info("Reopened issue: %s -- %s", key, issue["title"])
                task_text = build_task_text(repo, issue)
                result = dispatcher_submit(dispatcher_url, task_text, sender=key, token=token)
                if result:
                    task_id = result.get("id", "")
                    tracked.update({
                        "task_id": task_id,
                        "state": result.get("state", "PENDING"),
                        "result_posted": False,
                        "last_updated": updated_at,
                        "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    })
                    post_comment(repo, number,
                                 f"Reopened -- new task submitted (id: `{task_id}`). Tracking...")
                    log.info("Re-submitted task %s for reopened %s", task_id, key)
                save_state(state_file)

            # Check for new comments
            _process_issue_comments(repo, issue, dispatcher_url, token, state_file)

        _state["last_poll"][repo] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    save_state(state_file)


def _process_issue_comments(repo, issue, dispatcher_url, token, state_file):
    """Check for new comments on a tracked issue and submit as follow-up tasks."""
    number = issue["number"]
    key = f"{repo}#{number}"
    comments = list_issue_comments(repo, number)
    if not comments:
        return

    for comment in comments:
        comment_id = comment.get("id")
        if not comment_id:
            continue
        comment_key = f"{key}#{comment_id}"

        # Skip our own comments
        body = comment.get("body", "")
        if BOT_MARKER in body:
            continue

        # Skip already-processed comments
        if comment_key in _state["comments"]:
            continue

        author = comment.get("user", {}).get("login", "unknown")
        log.info("New comment on %s by %s (id: %s)", key, author, comment_id)

        task_text = build_followup_text(repo, number, issue["title"], comment)
        result = dispatcher_submit(dispatcher_url, task_text, sender=comment_key, token=token)
        if result:
            task_id = result.get("id", "")
            _state["comments"][comment_key] = {
                "task_id": task_id,
                "state": result.get("state", "PENDING"),
                "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            post_comment(repo, number,
                         f"Follow-up task submitted (id: `{task_id}`). Tracking...")
            log.info("Submitted follow-up task %s for comment %s", task_id, comment_key)
        else:
            _state["comments"][comment_key] = {
                "task_id": None,
                "state": "SUBMIT_FAILED",
            }
            log.error("Failed to submit follow-up task for %s", comment_key)

        save_state(state_file)


def check_pending_tasks(repos, dispatcher_url, token, state_file):
    """Poll dispatcher for status of in-flight tasks. Post results when done."""
    terminal_states = {"COMPLETED", "FAILED", "CANCELLED"}

    # Check issue tasks
    for key, tracked in list(_state["issues"].items()):
        task_id = tracked.get("task_id")
        if not task_id:
            continue
        if tracked.get("state") in terminal_states:
            continue
        if tracked.get("result_posted"):
            continue

        task = dispatcher_status(dispatcher_url, task_id, token)
        if not task:
            continue

        new_state = task.get("state", "")
        tracked["state"] = new_state

        if new_state in terminal_states:
            # Parse repo and issue number from key
            repo, number_str = key.rsplit("#", 1)
            number = int(number_str)
            comment_body = format_result_comment(task)
            if post_comment(repo, number, comment_body):
                tracked["result_posted"] = True
                log.info("Posted result for %s (state: %s)", key, new_state)

    # Check comment follow-up tasks
    for comment_key, tracked in list(_state["comments"].items()):
        task_id = tracked.get("task_id")
        if not task_id:
            continue
        if tracked.get("state") in terminal_states:
            continue
        if tracked.get("result_posted"):
            continue

        task = dispatcher_status(dispatcher_url, task_id, token)
        if not task:
            continue

        new_state = task.get("state", "")
        tracked["state"] = new_state

        if new_state in terminal_states:
            # Parse repo#number#comment_id
            parts = comment_key.split("#")
            if len(parts) >= 3:
                repo = parts[0]
                number = int(parts[1])
                comment_body = format_result_comment(task)
                if post_comment(repo, number, comment_body):
                    tracked["result_posted"] = True
                    log.info("Posted follow-up result for %s (state: %s)", comment_key, new_state)

    save_state(state_file)


# ── Main loop ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="GitHub issue monitor daemon for CCC")
    parser.add_argument("--repos", nargs="+",
                        default=os.environ.get("GH_ISSUE_REPOS", "").split(",") if os.environ.get("GH_ISSUE_REPOS") else DEFAULT_REPOS,
                        help="Repos to monitor (default: altarr/boothapp grobomo/claude-portable)")
    parser.add_argument("--dispatcher-url",
                        default=os.environ.get("GH_ISSUE_DISPATCHER_URL", DEFAULT_DISPATCHER_URL),
                        help="Dispatcher base URL")
    parser.add_argument("--poll-interval", type=int,
                        default=int(os.environ.get("GH_ISSUE_POLL_INTERVAL", DEFAULT_POLL_INTERVAL)),
                        help="Seconds between polls (default: 60)")
    parser.add_argument("--state-file",
                        default=os.environ.get("GH_ISSUE_STATE_FILE", DEFAULT_STATE_FILE),
                        help="Path to state file")
    parser.add_argument("--once", action="store_true",
                        help="Run one poll cycle and exit (for testing)")
    args = parser.parse_args()

    # Filter empty repo strings
    repos = [r.strip() for r in args.repos if r.strip()]
    if not repos:
        log.error("No repos configured. Use --repos or GH_ISSUE_REPOS env var.")
        sys.exit(1)

    dispatcher_url = args.dispatcher_url.rstrip("/")
    token = os.environ.get("DISPATCH_API_TOKEN", "")

    log.info("GitHub Issue Monitor starting")
    log.info("  Repos: %s", ", ".join(repos))
    log.info("  Dispatcher: %s", dispatcher_url)
    log.info("  Poll interval: %ds", args.poll_interval)
    log.info("  State file: %s", args.state_file)

    # Verify gh CLI is available
    rc, stdout, stderr = gh_run(["auth", "status"])
    if rc != 0:
        log.error("gh CLI auth check failed: %s", stderr.strip())
        log.error("Ensure gh is installed and authenticated")
        sys.exit(1)

    load_state(args.state_file)

    poll_count = 0
    task_check_counter = 0

    while _running:
        poll_count += 1
        log.info("Poll #%d -- checking %d repos", poll_count, len(repos))

        try:
            process_issues(repos, dispatcher_url, token, args.state_file)
        except Exception as e:
            log.error("Error during issue poll: %s", e, exc_info=True)

        # Check pending tasks every cycle
        task_check_counter += 1
        try:
            check_pending_tasks(repos, dispatcher_url, token, args.state_file)
        except Exception as e:
            log.error("Error during task check: %s", e, exc_info=True)

        # Log stats
        active_issues = sum(1 for t in _state["issues"].values()
                           if t.get("state") not in ("COMPLETED", "FAILED", "CANCELLED", "SUBMIT_FAILED"))
        active_comments = sum(1 for t in _state["comments"].values()
                             if t.get("state") not in ("COMPLETED", "FAILED", "CANCELLED", "SUBMIT_FAILED"))
        log.info("  Tracked: %d issues (%d active), %d comments (%d active)",
                 len(_state["issues"]), active_issues,
                 len(_state["comments"]), active_comments)

        if args.once:
            break

        # Sleep in small increments so we can respond to signals
        for _ in range(args.poll_interval):
            if not _running:
                break
            time.sleep(1)

    save_state(args.state_file)
    log.info("GitHub Issue Monitor stopped")


if __name__ == "__main__":
    main()
