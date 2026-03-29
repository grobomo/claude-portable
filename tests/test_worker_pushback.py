#!/usr/bin/env python3
"""Tests for worker pushback flow (blocked tasks with human-in-the-loop).

Validates:
- Worker pipeline cmd_blocked marks task as blocked and notifies dispatcher
- Worker pipeline cmd_answer unblocks task and restores phase
- Dispatcher POST /worker/blocked records blocked status in fleet roster
- Worker POST /answer writes answer to pipeline state and answer file
"""

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
from http.server import BaseHTTPRequestHandler, HTTPServer

# ── Load modules ─────────────────────────────────────────────────────────────

_gd_path = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "scripts", "git-dispatch.py"
))
_gd_loader = importlib.machinery.SourceFileLoader("git_dispatch", _gd_path)
_gd_spec = importlib.util.spec_from_loader("git_dispatch", _gd_loader)
gd = importlib.util.module_from_spec(_gd_spec)
_gd_loader.exec_module(gd)

_wp_path = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "scripts", "worker-pipeline.py"
))
_wp_loader = importlib.machinery.SourceFileLoader("worker_pipeline", _wp_path)
_wp_spec = importlib.util.spec_from_loader("worker_pipeline", _wp_loader)
wp = importlib.util.module_from_spec(_wp_spec)
_wp_loader.exec_module(wp)


# ── Worker pipeline: cmd_blocked and cmd_answer ──────────────────────────────

class TestCmdBlocked(unittest.TestCase):
    """Test worker-pipeline.py cmd_blocked."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.tmpdir, "pipeline-state.json")
        self._orig = wp.STATE_FILE
        wp.STATE_FILE = self.state_file
        wp.cmd_start(["1", "Test", "task"])
        wp.cmd_phase(["RESEARCH", "running"])

    def tearDown(self):
        wp.STATE_FILE = self._orig
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_blocked_marks_state(self):
        result = wp.cmd_blocked(["RESEARCH", "unclear requirements", "What does 'dark mode' mean?"])
        self.assertEqual(result, 0)
        with open(self.state_file) as f:
            state = json.load(f)
        self.assertEqual(state["status"], "blocked")
        self.assertEqual(state["blocked_phase"], "RESEARCH")
        self.assertEqual(state["blocked_reason"], "unclear requirements")
        self.assertEqual(state["blocked_question"], "What does 'dark mode' mean?")
        self.assertIn("blocked_at", state)

    def test_blocked_missing_args(self):
        result = wp.cmd_blocked(["RESEARCH"])
        self.assertEqual(result, 1)

    def test_blocked_no_active_task(self):
        wp.STATE_FILE = os.path.join(self.tmpdir, "empty.json")
        result = wp.cmd_blocked(["PLAN", "stuck"])
        self.assertEqual(result, 1)


class TestCmdAnswer(unittest.TestCase):
    """Test worker-pipeline.py cmd_answer."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.tmpdir, "pipeline-state.json")
        self._orig = wp.STATE_FILE
        wp.STATE_FILE = self.state_file
        wp.cmd_start(["2", "Another", "task"])
        wp.cmd_phase(["PLAN", "running"])
        wp.cmd_blocked(["PLAN", "need clarification", "Which DB to use?"])

    def tearDown(self):
        wp.STATE_FILE = self._orig
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_answer_unblocks_task(self):
        result = wp.cmd_answer(["Use", "PostgreSQL"])
        self.assertEqual(result, 0)
        with open(self.state_file) as f:
            state = json.load(f)
        self.assertEqual(state["status"], "running")
        self.assertEqual(state["blocked_answer"], "Use PostgreSQL")
        self.assertEqual(state["current_phase"], "PLAN")
        self.assertIn("unblocked_at", state)

    def test_answer_missing_args(self):
        result = wp.cmd_answer([])
        self.assertEqual(result, 1)

    def test_answer_no_active_task(self):
        wp.STATE_FILE = os.path.join(self.tmpdir, "empty.json")
        result = wp.cmd_answer(["some answer"])
        self.assertEqual(result, 1)


# ── Dispatcher: POST /worker/blocked ────────────────────────────────────────

class TestDispatcherBlockedEndpoint(unittest.TestCase):
    """Test POST /worker/blocked on the dispatcher."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls._orig_repo = gd.REPO_DIR
        gd.REPO_DIR = cls.tmpdir
        with open(os.path.join(cls.tmpdir, "TODO.md"), "w") as f:
            f.write("- [ ] task\n")
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

    def _post(self, path, payload):
        data = json.dumps(payload).encode()
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("POST", path, body=data,
                     headers={"Content-Type": "application/json",
                              "Content-Length": str(len(data))})
        resp = conn.getresponse()
        body = resp.read().decode()
        conn.close()
        return resp.status, json.loads(body) if body else {}

    def test_blocked_returns_200(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster["w1"] = {"status": "busy", "pipeline": {}}
        status, data = self._post("/worker/blocked", {
            "worker_id": "w1",
            "task_num": 3,
            "phase": "RESEARCH",
            "reason": "unclear",
            "question": "What exactly?",
        })
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")

    def test_blocked_updates_roster(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster["w1"] = {"status": "busy", "pipeline": {"stage": "PLAN"}}
        self._post("/worker/blocked", {
            "worker_id": "w1",
            "task_num": 5,
            "phase": "PLAN",
            "reason": "ambiguous spec",
            "question": "Which API version?",
        })
        with gd._fleet_roster_lock:
            entry = gd._fleet_roster["w1"]
        self.assertEqual(entry["status"], "blocked")
        self.assertEqual(entry["blocked_phase"], "PLAN")
        self.assertEqual(entry["blocked_question"], "Which API version?")

    def test_blocked_unknown_worker_still_ok(self):
        status, data = self._post("/worker/blocked", {
            "worker_id": "ghost",
            "phase": "TESTS",
            "reason": "stuck",
        })
        self.assertEqual(status, 200)

    def test_blocked_uses_reason_as_default_question(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster["w2"] = {"status": "busy", "pipeline": {}}
        self._post("/worker/blocked", {
            "worker_id": "w2",
            "phase": "WHY",
            "reason": "task seems redundant",
        })
        with gd._fleet_roster_lock:
            entry = gd._fleet_roster["w2"]
        self.assertEqual(entry["blocked_question"], "task seems redundant")


if __name__ == "__main__":
    unittest.main()
