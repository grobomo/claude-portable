"""
blockers.py -- Receive worker escalations, search past resolutions, suggest fixes.

When a worker reports a blocker, the brain:
  1. Searches past task outcomes for similar issues
  2. Checks known resolution patterns
  3. Asks Claude for a suggested fix using conversation context
"""

import logging
import re
import time

from .storage import Storage

log = logging.getLogger(__name__)

# Common blocker patterns and their known resolutions
KNOWN_PATTERNS = [
    {
        "pattern": r"(permission|denied|403|unauthorized)",
        "category": "auth",
        "suggestion": "Check IAM roles, API tokens, and gh auth status. "
                      "Verify the worker has correct AWS profile and GitHub auth.",
    },
    {
        "pattern": r"(merge conflict|conflict|cannot merge)",
        "category": "git",
        "suggestion": "Pull latest main, rebase the feature branch. "
                      "If conflicts persist, the worker should resolve manually.",
    },
    {
        "pattern": r"(timeout|timed out|deadline exceeded)",
        "category": "timeout",
        "suggestion": "Increase timeout values. Check if the operation is hanging "
                      "on network or waiting for a resource.",
    },
    {
        "pattern": r"(not found|404|no such file|module not found)",
        "category": "missing",
        "suggestion": "Check file paths, ensure dependencies are installed. "
                      "Run npm install or pip install as needed.",
    },
    {
        "pattern": r"(disk full|no space|quota exceeded)",
        "category": "resources",
        "suggestion": "Clean up Docker images/volumes, expand EBS volume, "
                      "or terminate idle workers to free resources.",
    },
    {
        "pattern": r"(rate limit|throttl|too many requests|429)",
        "category": "rate_limit",
        "suggestion": "Add backoff/retry logic. If Claude API rate limited, "
                      "reduce concurrent workers or add delays between calls.",
    },
]


class BlockerResolver:
    """Search past resolutions and suggest fixes for worker blockers."""

    def __init__(self, storage: Storage):
        self.storage = storage

    def search_past_resolutions(self, blocker_text: str, n: int = 5) -> list[dict]:
        """Search past blocker records for similar issues.

        Returns matching past blockers with their resolutions, sorted by relevance.
        """
        past = self.storage.read_jsonl("blockers.jsonl")
        if not past:
            return []

        # Simple keyword matching -- extract significant words from blocker
        words = set(re.findall(r'\b\w{4,}\b', blocker_text.lower()))
        if not words:
            return []

        scored = []
        for record in past:
            past_text = record.get("blocker_text", "").lower()
            past_words = set(re.findall(r'\b\w{4,}\b', past_text))
            overlap = len(words & past_words)
            if overlap > 0:
                scored.append((overlap, record))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [rec for _, rec in scored[:n]]

    def match_known_patterns(self, blocker_text: str) -> list[dict]:
        """Match blocker text against known resolution patterns."""
        text_lower = blocker_text.lower()
        matches = []
        for pattern in KNOWN_PATTERNS:
            if re.search(pattern["pattern"], text_lower):
                matches.append({
                    "category": pattern["category"],
                    "suggestion": pattern["suggestion"],
                })
        return matches

    def suggest_resolution(self, blocker_text: str, worker_id: str | None = None,
                            task_id: str | None = None) -> dict:
        """Analyze a blocker and suggest a resolution.

        Returns a dict with:
          - known_fixes: matches from known patterns
          - past_resolutions: similar past blockers and how they were resolved
          - recommended_action: best guess at what to do
        """
        known = self.match_known_patterns(blocker_text)
        past = self.search_past_resolutions(blocker_text)

        # Build recommendation
        if known:
            recommended = known[0]["suggestion"]
        elif past and past[0].get("resolution"):
            recommended = f"Similar past blocker was resolved by: {past[0]['resolution']}"
        else:
            recommended = (
                "No known resolution found. Consider: "
                "1) Check logs on the worker, "
                "2) Try restarting the task, "
                "3) Escalate to human operator."
            )

        return {
            "known_fixes": known,
            "past_resolutions": past[:3],
            "recommended_action": recommended,
        }

    def record_blocker(self, blocker_text: str, worker_id: str | None = None,
                        task_id: str | None = None,
                        resolution: str | None = None) -> None:
        """Record a blocker (and optionally its resolution) for future reference."""
        self.storage.append_jsonl("blockers.jsonl", {
            "blocker_text": blocker_text[:500],
            "worker_id": worker_id,
            "task_id": task_id,
            "resolution": resolution,
            "resolved_at": time.time() if resolution else None,
        })

    def resolve_blocker(self, task_id: str, resolution: str) -> None:
        """Update the most recent blocker for a task with its resolution."""
        records = self.storage.read_jsonl("blockers.jsonl")
        updated = False
        for record in reversed(records):
            if record.get("task_id") == task_id and not record.get("resolution"):
                record["resolution"] = resolution
                record["resolved_at"] = time.time()
                updated = True
                break

        if updated:
            # Rewrite the file with updated records
            path = self.storage._path("blockers.jsonl")
            import json
            with open(path, "w") as f:
                for rec in records:
                    f.write(json.dumps(rec, default=str) + "\n")
