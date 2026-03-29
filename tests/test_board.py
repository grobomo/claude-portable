#!/usr/bin/env python3
"""Tests for dispatcher board aggregation (board.json + /board endpoint)."""

import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

loader = importlib.machinery.SourceFileLoader(
    "git_dispatch",
    os.path.join(os.path.dirname(__file__), "..", "scripts", "git-dispatch.py"),
)
spec = importlib.util.spec_from_loader("git_dispatch", loader)
gd = importlib.util.module_from_spec(spec)
loader.exec_module(gd)


class TestBuildBoard(unittest.TestCase):
    def setUp(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()
        self.tmpdir = tempfile.mkdtemp()
        self._orig_repo = gd.REPO_DIR
        gd.REPO_DIR = self.tmpdir
        # Write empty TODO.md by default
        with open(os.path.join(self.tmpdir, "TODO.md"), "w") as f:
            f.write("")

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

    def test_single_worker_in_board(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster["w1"] = {
                "status": "busy",
                "healthy": True,
                "pipeline": {"stage": "TESTS", "stages_complete": 3},
                "task": {"task_num": 5, "description": "Add tests", "branch": "continuous-claude/task-5"},
                "idle_seconds": 0,
                "maintenance": False,
                "last_heartbeat": "2026-03-29T10:00:00Z",
            }

        board = gd._build_board()
        self.assertEqual(len(board["workers"]), 1)
        w = board["workers"][0]
        self.assertEqual(w["worker_id"], "w1")
        self.assertEqual(w["status"], "busy")
        self.assertEqual(w["phase"], "TESTS")
        self.assertEqual(w["phases_complete"], 3)
        self.assertEqual(w["task_num"], 5)
        self.assertTrue(w["healthy"])

    def test_multiple_workers(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster["w1"] = {
                "status": "busy",
                "pipeline": {"stage": "IMPLEMENT"},
                "task": {},
                "idle_seconds": 0,
            }
            gd._fleet_roster["w2"] = {
                "status": "idle",
                "pipeline": {"stage": "idle"},
                "task": {},
                "idle_seconds": 300,
            }

        board = gd._build_board()
        self.assertEqual(len(board["workers"]), 2)
        ids = {w["worker_id"] for w in board["workers"]}
        self.assertEqual(ids, {"w1", "w2"})

    def test_idle_worker_shows_idle_phase(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster["w1"] = {
                "status": "idle",
                "pipeline": {},
                "task": {},
                "idle_seconds": 600,
            }

        board = gd._build_board()
        self.assertEqual(board["workers"][0]["phase"], "idle")

    def test_missing_fields_use_defaults(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster["w1"] = {"status": "idle"}

        board = gd._build_board()
        w = board["workers"][0]
        self.assertEqual(w["phase"], "idle")
        self.assertIsNone(w["task_num"])
        self.assertEqual(w["task_description"], "")
        self.assertTrue(w["healthy"])  # default True

    def test_time_in_phase_computed(self):
        """time_in_phase_s calculated from pipeline.phases.<phase>.start."""
        past = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 120)
        )
        with gd._fleet_roster_lock:
            gd._fleet_roster["w1"] = {
                "status": "busy",
                "pipeline": {
                    "stage": "IMPLEMENT",
                    "phases": {"IMPLEMENT": {"start": past, "status": "running"}},
                },
                "task": {"task_num": 3},
            }

        board = gd._build_board()
        w = board["workers"][0]
        self.assertEqual(w["phase"], "IMPLEMENT")
        self.assertEqual(w["phase_start"], past)
        self.assertIsNotNone(w["time_in_phase_s"])
        self.assertGreaterEqual(w["time_in_phase_s"], 115)
        self.assertLessEqual(w["time_in_phase_s"], 130)

    def test_idle_worker_has_null_time_in_phase(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster["w1"] = {
                "status": "idle",
                "pipeline": {"stage": "idle"},
                "task": {},
            }

        board = gd._build_board()
        w = board["workers"][0]
        self.assertIsNone(w["phase_start"])
        self.assertIsNone(w["time_in_phase_s"])

    def test_summary_worker_counts(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster["w1"] = {
                "status": "busy",
                "pipeline": {"stage": "TESTS"},
                "task": {},
            }
            gd._fleet_roster["w2"] = {
                "status": "idle",
                "pipeline": {"stage": "idle"},
                "task": {},
            }
            gd._fleet_roster["w3"] = {
                "status": "busy",
                "pipeline": {"stage": "PR"},
                "task": {},
            }

        board = gd._build_board()
        self.assertEqual(board["summary"]["busy_workers"], 2)
        self.assertEqual(board["summary"]["idle_workers"], 1)
        self.assertEqual(board["summary"]["total_workers"], 3)


class TestUpdateBoard(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.board_file = os.path.join(self.tmpdir, "board.json")
        self._orig = gd.BOARD_FILE
        gd.BOARD_FILE = self.board_file
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()

    def tearDown(self):
        gd.BOARD_FILE = self._orig
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_writes_board_file(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster["w1"] = {
                "status": "busy",
                "pipeline": {"stage": "PLAN"},
                "task": {"task_num": 2},
            }
        gd._update_board()
        self.assertTrue(os.path.isfile(self.board_file))
        with open(self.board_file) as f:
            board = json.load(f)
        self.assertEqual(len(board["workers"]), 1)
        self.assertEqual(board["workers"][0]["phase"], "PLAN")

    def test_overwrites_on_update(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster["w1"] = {
                "status": "idle",
                "pipeline": {"stage": "idle"},
                "task": {},
            }
        gd._update_board()
        with gd._fleet_roster_lock:
            gd._fleet_roster["w1"]["status"] = "busy"
            gd._fleet_roster["w1"]["pipeline"] = {"stage": "VERIFY"}
        gd._update_board()
        with open(self.board_file) as f:
            board = json.load(f)
        self.assertEqual(board["workers"][0]["phase"], "VERIFY")

    def test_empty_roster_writes_valid_json(self):
        gd._update_board()
        with open(self.board_file) as f:
            board = json.load(f)
        self.assertEqual(board["workers"], [])


class TestBoardTaskSummary(unittest.TestCase):
    """Test that board includes task list and summary from TODO.md."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_repo = gd.REPO_DIR
        gd.REPO_DIR = self.tmpdir
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()

    def tearDown(self):
        gd.REPO_DIR = self._orig_repo
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_todo(self, content):
        with open(os.path.join(self.tmpdir, "TODO.md"), "w") as f:
            f.write(content)

    def test_task_counts_in_summary(self):
        self._write_todo(
            "# Tasks\n"
            "- [x] Done 1\n"
            "- [x] Done 2\n"
            "- [ ] Pending 3\n"
            "- [ ] Pending 4\n"
        )
        board = gd._build_board()
        s = board["summary"]
        self.assertEqual(s["total_tasks"], 4)
        self.assertEqual(s["completed"], 2)
        self.assertEqual(s["pending"], 2)

    def test_tasks_is_list_of_pending(self):
        self._write_todo(
            "# Tasks\n"
            "- [x] Done 1\n"
            "- [ ] Pending 2\n"
            "- [ ] Pending 3\n"
        )
        board = gd._build_board()
        # tasks list only contains pending (unchecked) items
        self.assertIsInstance(board["tasks"], list)
        self.assertEqual(len(board["tasks"]), 2)

    def test_no_todo_file_gives_empty(self):
        # No TODO.md written — REPO_DIR points to empty tmpdir
        board = gd._build_board()
        self.assertEqual(board["summary"]["total_tasks"], 0)
        self.assertEqual(board["tasks"], [])

    def test_summary_always_present(self):
        self._write_todo("")
        board = gd._build_board()
        self.assertIn("summary", board)
        self.assertIn("tasks", board)
        for key in ("total_tasks", "completed", "pending", "blocked",
                     "idle_workers", "busy_workers", "total_workers"):
            self.assertIn(key, board["summary"])

    def test_task_worker_assignment(self):
        self._write_todo(
            "# Tasks\n"
            "- [ ] Build feature X\n"
        )
        with gd._fleet_roster_lock:
            gd._fleet_roster["w1"] = {
                "status": "busy",
                "pipeline": {"stage": "IMPLEMENT"},
                "task": {"description": "Build feature X"},
            }
        board = gd._build_board()
        self.assertEqual(len(board["tasks"]), 1)
        t = board["tasks"][0]
        self.assertEqual(t["worker"], "w1")
        self.assertEqual(t["phase"], "IMPLEMENT")
        self.assertEqual(t["status"], "in_progress")

    def test_unassigned_task_is_pending(self):
        self._write_todo(
            "# Tasks\n"
            "- [ ] Unassigned task\n"
        )
        board = gd._build_board()
        t = board["tasks"][0]
        self.assertEqual(t["status"], "pending")
        self.assertIsNone(t["worker"])

    def test_blocked_task_status(self):
        self._write_todo(
            "# Tasks\n"
            "- [ ] Blocked task\n"
            "  - depends-on: 99\n"
        )
        board = gd._build_board()
        t = board["tasks"][0]
        self.assertEqual(t["status"], "blocked")
        self.assertTrue(t["blocked"])
        self.assertEqual(board["summary"]["blocked"], 1)

    def test_in_progress_count(self):
        self._write_todo(
            "# Tasks\n"
            "- [ ] Task A\n"
            "- [ ] Task B\n"
        )
        with gd._fleet_roster_lock:
            gd._fleet_roster["w1"] = {
                "status": "busy",
                "pipeline": {"stage": "TESTS"},
                "task": {"description": "Task A"},
            }
        board = gd._build_board()
        self.assertEqual(board["summary"]["in_progress"], 1)
        self.assertEqual(board["summary"]["pending"], 1)


class TestBoardEndpoint(unittest.TestCase):
    """Test GET /board HTTP endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.port = 18083
        gd.HEALTH_PORT = cls.port
        cls.server = HTTPServer(("127.0.0.1", cls.port), gd.HealthHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

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

    def test_board_returns_200(self):
        status, data = self._get("/board")
        self.assertEqual(status, 200)
        self.assertIn("workers", data)
        self.assertIn("updated_at", data)

    def test_board_reflects_roster(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster["board-w"] = {
                "status": "idle",
                "healthy": True,
                "pipeline": {"stage": "idle"},
                "task": {},
                "idle_seconds": 100,
                "maintenance": False,
                "last_heartbeat": "2026-03-29T12:00:00Z",
            }
        status, data = self._get("/board")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["workers"]), 1)
        self.assertEqual(data["workers"][0]["worker_id"], "board-w")

    def test_board_has_tasks_field(self):
        status, data = self._get("/board")
        self.assertIn("tasks", data)


if __name__ == "__main__":
    unittest.main()
