"""
fleet.py -- Track worker state and select best worker for each task.

Maintains a scoring system based on:
  - Worker specialization (what areas they've worked on before)
  - Current load (how many active tasks)
  - Success rate (completed vs failed tasks)
  - Recency (prefer workers that haven't been used recently for fairness)
"""

import logging
import time
from typing import Any

from .storage import Storage

log = logging.getLogger(__name__)

FLEET_STATE_FILE = "fleet_state.json"


class Fleet:
    """Track worker state and select optimal worker assignment."""

    def __init__(self, storage: Storage):
        self.storage = storage
        self._state = self._load()

    def _load(self) -> dict:
        """Load fleet state from storage."""
        default = {"workers": {}, "last_updated": 0}
        state = self.storage.read_json(FLEET_STATE_FILE, default=default)
        if "workers" not in state:
            state["workers"] = {}
        return state

    def _save(self) -> None:
        """Persist fleet state."""
        self._state["last_updated"] = time.time()
        self.storage.write_json(FLEET_STATE_FILE, self._state)

    def register_worker(self, worker_id: str, ip: str | None = None,
                         tags: dict | None = None) -> None:
        """Register or update a worker."""
        workers = self._state["workers"]
        if worker_id not in workers:
            workers[worker_id] = {
                "id": worker_id,
                "ip": ip,
                "tags": tags or {},
                "tasks_completed": 0,
                "tasks_failed": 0,
                "areas": [],
                "last_task_at": 0,
                "current_task": None,
                "status": "idle",
            }
        else:
            if ip:
                workers[worker_id]["ip"] = ip
            if tags:
                workers[worker_id]["tags"].update(tags)
        self._save()

    def update_worker_status(self, worker_id: str, status: str,
                              current_task: str | None = None) -> None:
        """Update a worker's status."""
        workers = self._state["workers"]
        if worker_id not in workers:
            self.register_worker(worker_id)
        workers[worker_id]["status"] = status
        workers[worker_id]["current_task"] = current_task
        if status == "busy":
            workers[worker_id]["last_task_at"] = time.time()
        self._save()

    def record_task_completion(self, worker_id: str, task_area: str,
                                success: bool) -> None:
        """Record a task completion for a worker."""
        workers = self._state["workers"]
        if worker_id not in workers:
            self.register_worker(worker_id)
        w = workers[worker_id]
        if success:
            w["tasks_completed"] += 1
        else:
            w["tasks_failed"] += 1
        if task_area and task_area not in w["areas"]:
            w["areas"].append(task_area)
            # Keep area list manageable
            if len(w["areas"]) > 20:
                w["areas"] = w["areas"][-20:]
        w["status"] = "idle"
        w["current_task"] = None
        self._save()

    def get_idle_workers(self) -> list[dict]:
        """Get workers that are currently idle."""
        return [
            w for w in self._state["workers"].values()
            if w["status"] == "idle"
        ]

    def get_all_workers(self) -> list[dict]:
        """Get all known workers."""
        return list(self._state["workers"].values())

    def select_best_worker(self, task_text: str,
                            available_workers: list[str] | None = None) -> str | None:
        """Select the best worker for a task based on scoring.

        Scoring factors:
          - Area match: +10 if worker has worked on similar area before
          - Success rate: +5 * (completed / total) if total > 0
          - Idle time: +1 for every 5 minutes idle (fairness / round-robin)
          - Current load: -20 if worker is busy

        Returns worker_id or None if no suitable worker found.
        """
        workers = self._state["workers"]
        if not workers:
            return None

        # Extract area keywords from task text
        task_words = set(task_text.lower().split())

        candidates = available_workers or list(workers.keys())
        best_id = None
        best_score = float("-inf")

        for wid in candidates:
            if wid not in workers:
                continue
            w = workers[wid]
            score = 0.0

            # Busy penalty
            if w["status"] == "busy":
                score -= 20

            # Area match bonus
            for area in w.get("areas", []):
                if area.lower() in task_words:
                    score += 10
                    break

            # Success rate
            total = w["tasks_completed"] + w["tasks_failed"]
            if total > 0:
                score += 5 * (w["tasks_completed"] / total)

            # Idle time bonus (fairness)
            idle_minutes = (time.time() - w.get("last_task_at", 0)) / 60
            score += min(idle_minutes / 5, 10)  # Cap at +10

            if score > best_score:
                best_score = score
                best_id = wid

        return best_id

    def get_summary(self) -> str:
        """Get a human-readable summary of fleet state."""
        workers = self._state["workers"]
        if not workers:
            return "No workers registered."

        lines = []
        for wid, w in workers.items():
            total = w["tasks_completed"] + w["tasks_failed"]
            rate = f"{w['tasks_completed']}/{total}" if total else "0/0"
            status = w["status"]
            task = f" ({w['current_task']})" if w["current_task"] else ""
            areas = ", ".join(w.get("areas", [])[:5]) or "none"
            lines.append(f"  {wid}: {status}{task} | success: {rate} | areas: {areas}")

        return "Workers:\n" + "\n".join(lines)

    def remove_worker(self, worker_id: str) -> None:
        """Remove a worker from the fleet."""
        self._state["workers"].pop(worker_id, None)
        self._save()
