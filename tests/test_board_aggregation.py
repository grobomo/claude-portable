#!/usr/bin/env python3
"""Tests for dispatcher board aggregation.

Validates:
- _build_board() aggregates worker pipeline state and task list
- Board includes per-worker phase, time_in_phase_s, task assignment
- Board includes per-task status (pending/in_progress/blocked) with worker mapping
- Board summary counts are accurate
- GET /board endpoint returns board JSON
- _update_board() writes board.json to disk
"""

import importlib.machinery
import importlib.util
import json
import os
import re
import sys
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import HTTPServer
from unittest.mock import patch

# ── Load git-dispatch.py as module ───────────────────────────────────────────

_gd_path = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "scripts", "git-dispatch.py"
))
_gd_loader = importlib.machinery.SourceFileLoader("git_dispatch", _gd_path)
_gd_spec = importlib.util.spec_from_loader("git_dispatch", _gd_loader)
gd = importlib.util.module_from_spec(_gd_spec)
_gd_loader.exec_module(gd)


class TestBuildBoardWorkers(unittest.TestCase):
    """Test that _build_board includes worker pipeline details."""

    def setUp(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()
        self._orig_repo = gd.REPO_DIR
        self.tmpdir = tempfile.mkdtemp()
        gd.REPO_DIR = self.tmpdir
        # Create minimal TODO.md
        with open(os.path.join(self.tmpdir, "TODO.md"), "w") as f:
            f.write("- [x] Done task\n- [ ] Pending task\n")

    def tearDown(self):
        gd.REPO_DIR = self._orig_repo
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_empty_roster_returns_empty_workers(self):
        board = gd._build_board()
        self.assertEqual(board["workers"], [])
        self.assertIn("updated_at", board)

    def test_worker_phase_in_board(self):
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with gd._fleet_roster_lock:
            gd._fleet_roster["w1"] = {
                "status": "busy",
                "healthy": True,
                "pipeline": {
                    "stage": "IMPLEMENT",
                    "stages_complete": 3,
                    "phases": {"IMPLEMENT": {"start": now_str, "status": "running"}},
                },
                "task": {"task_num": 2, "description": "Pending task", "branch": "continuous-claude/task-2"},
                "idle_seconds": 0,
                "maintenance": False,
                "last_heartbeat": now_str,
                "uptime_seconds": 600,
            }

        board = gd._build_board()
        self.assertEqual(len(board["workers"]), 1)
        w = board["workers"][0]
        self.assertEqual(w["worker_id"], "w1")
        self.assertEqual(w["phase"], "IMPLEMENT")
        self.assertEqual(w["task_num"], 2)
        self.assertEqual(w["task_description"], "Pending task")
        self.assertEqual(w["task_branch"], "continuous-claude/task-2")
        self.assertIsNotNone(w["time_in_phase_s"])
        self.assertGreaterEqual(w["time_in_phase_s"], 0)
        self.assertEqual(w["uptime_seconds"], 600)

    def test_idle_worker_has_no_time_in_phase(self):
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with gd._fleet_roster_lock:
            gd._fleet_roster["w-idle"] = {
                "status": "idle",
                "healthy": True,
                "pipeline": {"stage": "idle"},
                "task": {},
                "idle_seconds": 300,
                "maintenance": False,
                "last_heartbeat": now_str,
            }

        board = gd._build_board()
        w = board["workers"][0]
        self.assertEqual(w["phase"], "idle")
        self.assertIsNone(w["time_in_phase_s"])

    def test_multiple_workers_sorted_independently(self):
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with gd._fleet_roster_lock:
            gd._fleet_roster["w-alpha"] = {
                "status": "busy", "healthy": True,
                "pipeline": {"stage": "RESEARCH"}, "task": {},
                "last_heartbeat": now_str,
            }
            gd._fleet_roster["w-beta"] = {
                "status": "idle", "healthy": True,
                "pipeline": {"stage": "idle"}, "task": {},
                "last_heartbeat": now_str,
            }

        board = gd._build_board()
        self.assertEqual(len(board["workers"]), 2)
        wids = {w["worker_id"] for w in board["workers"]}
        self.assertEqual(wids, {"w-alpha", "w-beta"})


class TestBuildBoardTasks(unittest.TestCase):
    """Test that _build_board includes task list with worker assignments."""

    def setUp(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()
        self._orig_repo = gd.REPO_DIR
        self.tmpdir = tempfile.mkdtemp()
        gd.REPO_DIR = self.tmpdir

    def tearDown(self):
        gd.REPO_DIR = self._orig_repo
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_todo(self, content):
        with open(os.path.join(self.tmpdir, "TODO.md"), "w") as f:
            f.write(content)

    def test_pending_tasks_in_board(self):
        self._write_todo("- [x] Done\n- [ ] Task A\n- [ ] Task B\n")
        board = gd._build_board()
        self.assertEqual(len(board["tasks"]), 2)
        self.assertEqual(board["tasks"][0]["description"], "Task A")
        self.assertEqual(board["tasks"][0]["status"], "pending")
        self.assertIsNone(board["tasks"][0]["worker"])

    def test_task_assigned_to_worker(self):
        self._write_todo("- [ ] Build the widget\n")
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with gd._fleet_roster_lock:
            gd._fleet_roster["w1"] = {
                "status": "busy", "healthy": True,
                "pipeline": {"stage": "TESTS", "stages_complete": 2},
                "task": {"task_num": 1, "description": "Build the widget", "branch": "continuous-claude/task-1"},
                "last_heartbeat": now_str,
            }

        board = gd._build_board()
        self.assertEqual(len(board["tasks"]), 1)
        t = board["tasks"][0]
        self.assertEqual(t["status"], "in_progress")
        self.assertEqual(t["worker"], "w1")
        self.assertEqual(t["phase"], "TESTS")

    def test_blocked_task_status(self):
        self._write_todo(
            "- [ ] Task A\n"
            "- [ ] Task B\n"
            "  - depends-on: line-1\n"
        )
        board = gd._build_board()
        # Task B depends on Task A (line 1) which is unchecked
        blocked_tasks = [t for t in board["tasks"] if t["status"] == "blocked"]
        # At least Task B should be blocked
        self.assertTrue(len(blocked_tasks) >= 1)


class TestBuildBoardSummary(unittest.TestCase):
    """Test that board summary counts are accurate."""

    def setUp(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()
        self._orig_repo = gd.REPO_DIR
        self.tmpdir = tempfile.mkdtemp()
        gd.REPO_DIR = self.tmpdir

    def tearDown(self):
        gd.REPO_DIR = self._orig_repo
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_summary_counts(self):
        with open(os.path.join(self.tmpdir, "TODO.md"), "w") as f:
            f.write("- [x] Done 1\n- [x] Done 2\n- [ ] Pending 1\n- [ ] Pending 2\n- [ ] Pending 3\n")

        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with gd._fleet_roster_lock:
            gd._fleet_roster["w1"] = {
                "status": "busy", "healthy": True,
                "pipeline": {"stage": "IMPLEMENT"},
                "task": {"description": "Pending 1"},
                "last_heartbeat": now_str,
            }
            gd._fleet_roster["w2"] = {
                "status": "idle", "healthy": True,
                "pipeline": {"stage": "idle"},
                "task": {},
                "last_heartbeat": now_str,
            }

        board = gd._build_board()
        s = board["summary"]
        self.assertEqual(s["completed"], 2)
        self.assertEqual(s["in_progress"], 1)
        self.assertEqual(s["pending"], 2)  # Pending 2 + Pending 3
        self.assertEqual(s["total_tasks"], 5)
        self.assertEqual(s["busy_workers"], 1)
        self.assertEqual(s["idle_workers"], 1)
        self.assertEqual(s["total_workers"], 2)

    def test_summary_no_todo(self):
        """Board works even without TODO.md."""
        board = gd._build_board()
        self.assertEqual(board["summary"]["completed"], 0)
        self.assertEqual(board["summary"]["pending"], 0)


class TestUpdateBoard(unittest.TestCase):
    """Test that _update_board writes board.json to disk."""

    def setUp(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()
        self._orig_repo = gd.REPO_DIR
        self._orig_board = gd.BOARD_FILE
        self.tmpdir = tempfile.mkdtemp()
        gd.REPO_DIR = self.tmpdir
        gd.BOARD_FILE = os.path.join(self.tmpdir, "board.json")
        with open(os.path.join(self.tmpdir, "TODO.md"), "w") as f:
            f.write("- [ ] A task\n")

    def tearDown(self):
        gd.REPO_DIR = self._orig_repo
        gd.BOARD_FILE = self._orig_board
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_writes_valid_json(self):
        gd._update_board()
        self.assertTrue(os.path.isfile(gd.BOARD_FILE))
        with open(gd.BOARD_FILE) as f:
            board = json.load(f)
        self.assertIn("workers", board)
        self.assertIn("tasks", board)
        self.assertIn("summary", board)
        self.assertIn("updated_at", board)

    def test_board_updates_on_roster_change(self):
        gd._update_board()
        with open(gd.BOARD_FILE) as f:
            b1 = json.load(f)
        self.assertEqual(len(b1["workers"]), 0)

        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with gd._fleet_roster_lock:
            gd._fleet_roster["w-new"] = {
                "status": "busy", "healthy": True,
                "pipeline": {"stage": "PLAN"},
                "task": {"description": "A task"},
                "last_heartbeat": now_str,
            }
        gd._update_board()
        with open(gd.BOARD_FILE) as f:
            b2 = json.load(f)
        self.assertEqual(len(b2["workers"]), 1)
        self.assertEqual(b2["workers"][0]["phase"], "PLAN")


class TestBoardHTTPEndpoint(unittest.TestCase):
    """Test GET /board on the dispatcher health server."""

    @classmethod
    def setUpClass(cls):
        cls._orig_repo = gd.REPO_DIR
        cls.tmpdir = tempfile.mkdtemp()
        gd.REPO_DIR = cls.tmpdir
        with open(os.path.join(cls.tmpdir, "TODO.md"), "w") as f:
            f.write("- [x] Done task\n- [ ] Open task\n")
        cls.server = HTTPServer(("127.0.0.1", 0), gd.HealthHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        gd.REPO_DIR = cls._orig_repo
        import shutil
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def setUp(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()

    def _get(self, path):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read().decode()
        conn.close()
        return resp.status, json.loads(body) if body else {}

    def test_board_endpoint_returns_200(self):
        status, data = self._get("/board")
        self.assertEqual(status, 200)
        self.assertIn("workers", data)
        self.assertIn("tasks", data)
        self.assertIn("summary", data)
        self.assertIn("updated_at", data)

    def test_board_reflects_roster(self):
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with gd._fleet_roster_lock:
            gd._fleet_roster["w-http"] = {
                "status": "busy", "healthy": True,
                "pipeline": {"stage": "VERIFY", "stages_complete": 5},
                "task": {"task_num": 1, "description": "Open task", "branch": "cc/t1"},
                "last_heartbeat": now_str,
                "uptime_seconds": 120,
            }

        status, board = self._get("/board")
        self.assertEqual(status, 200)
        self.assertEqual(len(board["workers"]), 1)
        self.assertEqual(board["workers"][0]["phase"], "VERIFY")
        self.assertEqual(board["summary"]["busy_workers"], 1)

    def test_board_shows_task_in_progress(self):
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with gd._fleet_roster_lock:
            gd._fleet_roster["w-t"] = {
                "status": "busy", "healthy": True,
                "pipeline": {"stage": "RESEARCH"},
                "task": {"description": "Open task"},
                "last_heartbeat": now_str,
            }

        status, board = self._get("/board")
        in_progress = [t for t in board["tasks"] if t["status"] == "in_progress"]
        self.assertEqual(len(in_progress), 1)
        self.assertEqual(in_progress[0]["worker"], "w-t")

    def test_board_summary_counts_completed(self):
        status, board = self._get("/board")
        self.assertEqual(board["summary"]["completed"], 1)


if __name__ == "__main__":
    unittest.main()
