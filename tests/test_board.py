#!/usr/bin/env python3
"""Tests for dispatcher board aggregation (board.json)."""

import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest

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

    def tearDown(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()

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


if __name__ == "__main__":
    unittest.main()
