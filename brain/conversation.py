"""
conversation.py -- Persistent conversation manager using Anthropic API.

Maintains a single long-running conversation with Claude that accumulates
context across tasks. When context approaches the limit, summarizes old
tasks and restarts with the summary.

Key behaviors:
  - Loads CLAUDE.md + fleet state + recent PRs as system context
  - When a task arrives, Claude writes the spec inline (not via subprocess)
  - After each task completes, appends the outcome so next task benefits
  - When context approaches limit, summarizes and restarts
"""

import json
import logging
import os
import re
import time

from .context import build_system_prompt, estimate_tokens
from .storage import Storage

log = logging.getLogger(__name__)

# Context window management
MAX_CONTEXT_TOKENS = 180_000  # claude-sonnet-4-20250514 has 200k, leave headroom
SUMMARIZE_THRESHOLD = 150_000  # trigger summarization at this point
MODEL = "claude-sonnet-4-20250514"

# AWS Secrets Manager key for API key
SECRETS_MANAGER_KEY = "hackathon26/claude-api-key"


def _get_api_key() -> str:
    """Retrieve Claude API key from AWS Secrets Manager or environment.

    Priority:
      1. ANTHROPIC_API_KEY env var (for local dev/testing)
      2. AWS Secrets Manager (hackathon26/claude-api-key)
    """
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    if env_key:
        return env_key

    try:
        import boto3
        client = boto3.client("secretsmanager", region_name="us-east-1")
        resp = client.get_secret_value(SecretId=SECRETS_MANAGER_KEY)
        secret = resp["SecretString"]
        # Handle both raw key and JSON-wrapped key
        try:
            data = json.loads(secret)
            return data.get("api_key", data.get("key", secret))
        except json.JSONDecodeError:
            return secret
    except Exception as e:
        log.error("Failed to get API key from Secrets Manager: %s", e)
        raise RuntimeError(
            "No ANTHROPIC_API_KEY env var and Secrets Manager lookup failed. "
            f"Set ANTHROPIC_API_KEY or ensure AWS access to {SECRETS_MANAGER_KEY}."
        ) from e


def _create_client():
    """Create an Anthropic client. Lazy import to avoid hard dependency."""
    import anthropic
    return anthropic.Anthropic(api_key=_get_api_key())


class ConversationManager:
    """Persistent conversation with Claude for spec generation and learning."""

    def __init__(self, storage: Storage, repo_dir: str,
                 fleet_summary: str = "", model: str | None = None):
        self.storage = storage
        self.repo_dir = repo_dir
        self.fleet_summary = fleet_summary
        self.model = model or MODEL
        self._client = None
        self._system_prompt = None
        self._messages: list[dict] = []
        self._total_tokens = 0

    @property
    def client(self):
        if self._client is None:
            self._client = _create_client()
        return self._client

    def _get_system_prompt(self) -> str:
        """Build or return cached system prompt."""
        if self._system_prompt is None:
            # Get recent outcomes for learning context
            outcomes = self.storage.get_recent_outcomes(n=10)
            summaries = ""
            if outcomes:
                lines = []
                for o in outcomes:
                    lines.append(
                        f"- Task: {o.get('task_text', 'unknown')[:100]} | "
                        f"Outcome: {o.get('outcome', 'unknown')} | "
                        f"Worker: {o.get('worker', 'unknown')}"
                    )
                summaries = "\n".join(lines)

            self._system_prompt = build_system_prompt(
                repo_dir=self.repo_dir,
                fleet_summary=self.fleet_summary,
                task_summaries=summaries,
            )
        return self._system_prompt

    def _load_persisted_messages(self) -> None:
        """Load messages from storage if we have none in memory."""
        if not self._messages:
            self._messages = self.storage.get_messages()
            self._total_tokens = sum(
                estimate_tokens(m["content"]) for m in self._messages
            )

    def _check_context_limit(self) -> None:
        """If approaching context limit, summarize old messages and restart."""
        system_tokens = estimate_tokens(self._get_system_prompt())
        total = system_tokens + self._total_tokens

        if total < SUMMARIZE_THRESHOLD:
            return

        log.info("Context at ~%d tokens (threshold: %d), summarizing...",
                 total, SUMMARIZE_THRESHOLD)

        # Ask Claude to summarize the conversation so far
        summary_messages = self._messages + [{
            "role": "user",
            "content": (
                "Summarize all the tasks we've discussed so far, their outcomes, "
                "and any key architectural decisions or patterns. Be concise but "
                "preserve actionable knowledge. This summary will replace the "
                "full conversation history."
            ),
        }]

        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self._get_system_prompt(),
                messages=summary_messages,
            )
            summary_text = resp.content[0].text

            # Reset conversation with summary as first message
            self._messages = [
                {"role": "user", "content": "Here is a summary of our previous work:"},
                {"role": "assistant", "content": summary_text},
            ]
            self._total_tokens = estimate_tokens(summary_text) + 50
            self.storage.clear_messages()
            self.storage.append_message("user", "Here is a summary of our previous work:")
            self.storage.append_message("assistant", summary_text)

            log.info("Context summarized. New token estimate: ~%d", self._total_tokens)

        except Exception as e:
            log.error("Summarization failed: %s. Truncating instead.", e)
            # Fallback: just keep the last 10 messages
            self._messages = self._messages[-10:]
            self._total_tokens = sum(
                estimate_tokens(m["content"]) for m in self._messages
            )
            self.storage.clear_messages()
            for m in self._messages:
                self.storage.append_message(m["role"], m["content"])

    def generate_spec(self, task_text: str, request_id: str | None = None) -> dict:
        """Generate spec-kit artifacts for a task using the persistent conversation.

        Returns dict with keys: spec, plan, tasks (each a string of markdown content).
        Falls back to minimal spec on API failure.
        """
        self._load_persisted_messages()
        self._check_context_limit()

        user_msg = (
            f"New task request (ID: {request_id or 'unknown'}):\n\n"
            f"{task_text}\n\n"
            "Generate the full spec-kit artifacts (spec.md, plan.md, tasks.md) "
            "for this task. Use the ===SPEC===, ===PLAN===, ===TASKS=== delimiters."
        )

        self._messages.append({"role": "user", "content": user_msg})
        self.storage.append_message("user", user_msg)

        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=8192,
                system=self._get_system_prompt(),
                messages=self._messages,
            )

            assistant_text = resp.content[0].text
            self._messages.append({"role": "assistant", "content": assistant_text})
            self.storage.append_message("assistant", assistant_text)
            self._total_tokens += estimate_tokens(user_msg) + estimate_tokens(assistant_text)

            return self._parse_spec_response(assistant_text, task_text)

        except Exception as e:
            log.error("API call failed for task %s: %s", request_id, e)
            # Remove the failed user message from conversation
            self._messages.pop()
            return self._fallback_spec(task_text)

    def append_outcome(self, task_id: str, task_text: str, outcome: str,
                        worker: str | None = None) -> None:
        """Append a task outcome to the conversation for learning."""
        self._load_persisted_messages()

        outcome_msg = (
            f"Task completed - ID: {task_id}\n"
            f"Original: {task_text[:200]}\n"
            f"Worker: {worker or 'unknown'}\n"
            f"Outcome: {outcome}\n\n"
            "Note this for future reference when planning similar tasks."
        )

        self._messages.append({"role": "user", "content": outcome_msg})
        self.storage.append_message("user", outcome_msg)

        # Record in task outcomes too
        self.storage.record_task_outcome(task_id, task_text, outcome, worker)

        # Don't call the API just for recording -- save tokens.
        # The next generate_spec call will have this context.
        self._total_tokens += estimate_tokens(outcome_msg)

    def ask_about_blocker(self, blocker_text: str, task_id: str | None = None,
                           context: str = "") -> str:
        """Ask the brain about a blocker, leveraging conversation history."""
        self._load_persisted_messages()

        user_msg = (
            f"A worker hit a blocker:\n\n"
            f"Task: {task_id or 'unknown'}\n"
            f"Blocker: {blocker_text}\n"
        )
        if context:
            user_msg += f"Additional context: {context}\n"
        user_msg += "\nWhat's the most likely cause and fix?"

        self._messages.append({"role": "user", "content": user_msg})
        self.storage.append_message("user", user_msg)

        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=self._get_system_prompt(),
                messages=self._messages,
            )

            assistant_text = resp.content[0].text
            self._messages.append({"role": "assistant", "content": assistant_text})
            self.storage.append_message("assistant", assistant_text)
            self._total_tokens += estimate_tokens(user_msg) + estimate_tokens(assistant_text)

            return assistant_text

        except Exception as e:
            log.error("Blocker analysis API call failed: %s", e)
            self._messages.pop()
            return f"API call failed: {e}. Check worker logs manually."

    def invalidate_system_prompt(self) -> None:
        """Force rebuild of system prompt (e.g., after fleet state changes)."""
        self._system_prompt = None

    @staticmethod
    def _parse_spec_response(text: str, task_text: str) -> dict:
        """Parse the ===SPEC=== / ===PLAN=== / ===TASKS=== delimited response."""
        result = {"spec": "", "plan": "", "tasks": ""}

        # Try delimiter-based parsing first
        spec_match = re.search(r'===SPEC===\s*(.*?)(?:===PLAN===|$)', text, re.DOTALL)
        plan_match = re.search(r'===PLAN===\s*(.*?)(?:===TASKS===|$)', text, re.DOTALL)
        tasks_match = re.search(r'===TASKS===\s*(.*?)$', text, re.DOTALL)

        if spec_match:
            result["spec"] = spec_match.group(1).strip()
        if plan_match:
            result["plan"] = plan_match.group(1).strip()
        if tasks_match:
            result["tasks"] = tasks_match.group(1).strip()

        # If delimiter parsing failed, treat whole response as spec
        if not result["spec"]:
            result["spec"] = text.strip()
            result["plan"] = f"# Plan\n\nImplement the specification above."
            result["tasks"] = f"# Tasks\n\n- [ ] Implement spec as described"

        return result

    @staticmethod
    def _fallback_spec(task_text: str) -> dict:
        """Generate a minimal fallback spec when API fails."""
        return {
            "spec": (
                f"# Spec: {task_text[:80]}\n\n"
                f"## Problem Statement\n{task_text}\n\n"
                "## Success Criteria\n"
                "- [ ] Task completed as described\n"
                "- [ ] Tests pass\n"
                "- [ ] PR created with clear description\n"
            ),
            "plan": "# Plan\n\nImplement the specification above. See spec.md for details.",
            "tasks": "# Tasks\n\n- [ ] Implement spec as described in spec.md",
        }
