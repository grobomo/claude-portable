"""
storage.py -- JSONL/JSON persistence for conversation history and task outcomes.

Stores:
  - conversation_history.jsonl  -- full message log (role + content + timestamp)
  - task_outcomes.json          -- completed tasks with outcomes for learning
  - fleet_state.json            -- worker assignments and scores
"""

import json
import os
import time
from typing import Any


DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), ".data")


class Storage:
    """File-based persistence for brain state."""

    def __init__(self, data_dir: str | None = None):
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        os.makedirs(self.data_dir, exist_ok=True)

    def _path(self, filename: str) -> str:
        return os.path.join(self.data_dir, filename)

    # ── JSONL (append-only log) ────────────────────────────────────────────

    def append_jsonl(self, filename: str, record: dict) -> None:
        """Append a single JSON record to a JSONL file."""
        record.setdefault("_ts", time.time())
        with open(self._path(filename), "a") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def read_jsonl(self, filename: str, last_n: int | None = None) -> list[dict]:
        """Read records from a JSONL file. Optionally return only the last N."""
        path = self._path(filename)
        if not os.path.isfile(path):
            return []
        lines = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        lines.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        if last_n is not None:
            lines = lines[-last_n:]
        return lines

    def count_jsonl(self, filename: str) -> int:
        """Count records in a JSONL file without loading all into memory."""
        path = self._path(filename)
        if not os.path.isfile(path):
            return 0
        count = 0
        with open(path) as f:
            for line in f:
                if line.strip():
                    count += 1
        return count

    def truncate_jsonl(self, filename: str, keep_last_n: int) -> None:
        """Keep only the last N records in a JSONL file."""
        records = self.read_jsonl(filename)
        if len(records) <= keep_last_n:
            return
        records = records[-keep_last_n:]
        with open(self._path(filename), "w") as f:
            for rec in records:
                f.write(json.dumps(rec, default=str) + "\n")

    # ── JSON (full read/write) ─────────────────────────────────────────────

    def read_json(self, filename: str, default: Any = None) -> Any:
        """Read a JSON file. Returns default if file doesn't exist."""
        path = self._path(filename)
        if not os.path.isfile(path):
            return default if default is not None else {}
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return default if default is not None else {}

    def write_json(self, filename: str, data: Any) -> None:
        """Write data to a JSON file (overwrites)."""
        with open(self._path(filename), "w") as f:
            json.dump(data, f, indent=2, default=str)

    # ── Task outcomes ──────────────────────────────────────────────────────

    def record_task_outcome(self, task_id: str, task_text: str,
                            outcome: str, worker: str | None = None,
                            pr_url: str | None = None,
                            duration_s: float | None = None) -> None:
        """Record a completed task outcome for future learning."""
        self.append_jsonl("task_outcomes.jsonl", {
            "task_id": task_id,
            "task_text": task_text[:500],
            "outcome": outcome,
            "worker": worker,
            "pr_url": pr_url,
            "duration_s": duration_s,
        })

    def get_recent_outcomes(self, n: int = 20) -> list[dict]:
        """Get the N most recent task outcomes."""
        return self.read_jsonl("task_outcomes.jsonl", last_n=n)

    # ── Conversation messages ──────────────────────────────────────────────

    def append_message(self, role: str, content: str) -> None:
        """Append a conversation message."""
        self.append_jsonl("conversation_history.jsonl", {
            "role": role,
            "content": content,
        })

    def get_messages(self, last_n: int | None = None) -> list[dict]:
        """Get conversation messages (role + content only)."""
        records = self.read_jsonl("conversation_history.jsonl", last_n=last_n)
        return [{"role": r["role"], "content": r["content"]} for r in records]

    def clear_messages(self) -> None:
        """Clear conversation history (used after summarization)."""
        path = self._path("conversation_history.jsonl")
        if os.path.isfile(path):
            os.remove(path)
