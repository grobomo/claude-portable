#!/usr/bin/env python3
"""Tests for immediate phase transition events from workers to dispatcher.

Validates:
- Worker send_phase_change() POSTs to dispatcher
- Dispatcher /worker/phase-change updates roster and board
- set_pipeline_phase() auto-sends phase change to dispatcher
- Phase change audit logging
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
from unittest.mock import patch, MagicMock

# ── Load modules ─────────────────────────────────────────────────────────────

_wh_path = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "scripts", "worker-health.py"
))
_wh_loader = importlib.machinery.SourceFileLoader("worker_health", _wh_path)
_wh_spec = importlib.util.spec_from_loader("worker_health", _wh_loader)
wh = importlib.util.module_from_spec(_wh_spec)
_wh_loader.exec_module(wh)

_gd_path = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "scripts", "git-dispatch.py"
))
_gd_loader = importlib.machinery.SourceFileLoader("git_dispatch", _gd_path)
_gd_spec = importlib.util.spec_from_loader("git_dispatch", _gd_loader)
gd = importlib.util.module_from_spec(_gd_spec)
_gd_loader.exec_module(gd)


# ── Worker-side tests ────────────────────────────────────────────────────────

class TestSendPhaseChange(unittest.TestCase):
    """Test that send_phase_change POSTs correct payload to dispatcher."""

    def setUp(self):
        self.received = []
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length) if length else b"{}"
                parent.received.append(json.loads(body))
                self.send_response(200)
                resp = b'{"status": "ok"}'
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)

            def log_message(self, fmt, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self._orig_id = wh.WORKER_ID
        wh.WORKER_ID = "phase-test-worker"

    def tearDown(self):
        self.server.shutdown()
        wh.WORKER_ID = self._orig_id

    def test_sends_phase_change_payload(self):
        url = f"http://127.0.0.1:{self.port}"
        result = wh.send_phase_change(url, 5, "RESEARCH", "PLAN")
        self.assertTrue(result)
        self.assertEqual(len(self.received), 1)
        p = self.received[0]
        self.assertEqual(p["worker_id"], "phase-test-worker")
        self.assertEqual(p["task_num"], 5)
        self.assertEqual(p["old_phase"], "RESEARCH")
        self.assertEqual(p["new_phase"], "PLAN")
        self.assertIn("timestamp", p)

    def test_sends_gate_result(self):
        url = f"http://127.0.0.1:{self.port}"
        wh.send_phase_change(url, 3, "TESTS", "IMPLEMENT", gate_result="passed")
        self.assertEqual(self.received[0]["gate_result"], "passed")

    def test_returns_false_on_connection_error(self):
        result = wh.send_phase_change("http://127.0.0.1:1", 1, "A", "B")
        self.assertFalse(result)

    def test_old_phase_none_for_new_task(self):
        url = f"http://127.0.0.1:{self.port}"
        wh.send_phase_change(url, 1, None, "RESEARCH")
        self.assertIsNone(self.received[0]["old_phase"])


class TestSetPipelinePhaseSendsEvent(unittest.TestCase):
    """Test that set_pipeline_phase auto-sends phase change to dispatcher."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_state = wh.PIPELINE_STATE_FILE
        wh.PIPELINE_STATE_FILE = os.path.join(self.tmpdir, "pipeline-state.json")
        self._orig_url = wh.DISPATCHER_URL
        self._orig_id = wh.WORKER_ID
        wh.WORKER_ID = "auto-phase-worker"

    def tearDown(self):
        wh.PIPELINE_STATE_FILE = self._orig_state
        wh.DISPATCHER_URL = self._orig_url
        wh.WORKER_ID = self._orig_id
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_phase_change_sent_when_dispatcher_url_set(self):
        wh.DISPATCHER_URL = "http://127.0.0.1:9999"
        with patch.object(wh, "send_phase_change", return_value=True) as mock:
            wh.set_pipeline_phase(1, "RESEARCH")
            mock.assert_called_once()
            args = mock.call_args
            self.assertEqual(args[0][1], 1)  # task_num
            self.assertEqual(args[0][3], "RESEARCH")  # new_phase

    def test_no_phase_change_when_no_dispatcher_url(self):
        wh.DISPATCHER_URL = ""
        with patch.object(wh, "send_phase_change") as mock:
            wh.set_pipeline_phase(1, "PLAN")
            mock.assert_not_called()

    def test_phase_change_includes_old_phase(self):
        wh.DISPATCHER_URL = "http://127.0.0.1:9999"
        # Set initial phase
        with patch.object(wh, "send_phase_change", return_value=True):
            wh.set_pipeline_phase(1, "RESEARCH")

        # Transition to next phase
        with patch.object(wh, "send_phase_change", return_value=True) as mock:
            wh.set_pipeline_phase(1, "PLAN")
            args = mock.call_args
            self.assertEqual(args[0][2], "RESEARCH")  # old_phase
            self.assertEqual(args[0][3], "PLAN")  # new_phase

    def test_new_task_resets_old_phase_to_none(self):
        wh.DISPATCHER_URL = "http://127.0.0.1:9999"
        # Set up task 1 at IMPLEMENT phase
        with patch.object(wh, "send_phase_change", return_value=True):
            wh.set_pipeline_phase(1, "IMPLEMENT")

        # Start task 2 — old_phase should be None
        with patch.object(wh, "send_phase_change", return_value=True) as mock:
            wh.set_pipeline_phase(2, "RESEARCH")
            args = mock.call_args
            self.assertIsNone(args[0][2])  # old_phase is None for new task

    def test_send_failure_does_not_crash(self):
        wh.DISPATCHER_URL = "http://127.0.0.1:1"  # unreachable
        # Should not raise
        wh.set_pipeline_phase(1, "VERIFY")
        # Verify state was still written
        with open(wh.PIPELINE_STATE_FILE) as f:
            state = json.load(f)
        self.assertEqual(state["current_phase"], "VERIFY")


# ── Dispatcher-side tests ────────────────────────────────────────────────────

class TestDispatcherPhaseChangeEndpoint(unittest.TestCase):
    """Test POST /worker/phase-change on dispatcher."""

    @classmethod
    def setUpClass(cls):
        cls._orig_repo = gd.REPO_DIR
        cls.tmpdir = tempfile.mkdtemp()
        gd.REPO_DIR = cls.tmpdir
        with open(os.path.join(cls.tmpdir, "TODO.md"), "w") as f:
            f.write("- [ ] test task\n")
        cls._orig_board = gd.BOARD_FILE
        gd.BOARD_FILE = os.path.join(cls.tmpdir, "board.json")
        cls.server = HTTPServer(("127.0.0.1", 0), gd.HealthHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        gd.REPO_DIR = cls._orig_repo
        gd.BOARD_FILE = cls._orig_board
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

    def _get(self, path):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read().decode()
        conn.close()
        return resp.status, json.loads(body) if body else {}

    def test_phase_change_returns_200(self):
        # Pre-register worker
        with gd._fleet_roster_lock:
            gd._fleet_roster["w1"] = {
                "status": "busy", "healthy": True,
                "pipeline": {"stage": "RESEARCH"},
                "last_report": "",
            }
        status, data = self._post("/worker/phase-change", {
            "worker_id": "w1",
            "task_num": 3,
            "old_phase": "RESEARCH",
            "new_phase": "PLAN",
        })
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["phase"], "PLAN")

    def test_phase_change_updates_roster(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster["w2"] = {
                "status": "busy", "healthy": True,
                "pipeline": {"stage": "TESTS"},
                "last_report": "",
            }
        self._post("/worker/phase-change", {
            "worker_id": "w2",
            "task_num": 1,
            "old_phase": "TESTS",
            "new_phase": "IMPLEMENT",
        })
        with gd._fleet_roster_lock:
            entry = gd._fleet_roster.get("w2")
        self.assertEqual(entry["pipeline"]["stage"], "IMPLEMENT")
        self.assertEqual(entry["status"], "busy")

    def test_idle_phase_sets_idle_status(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster["w3"] = {
                "status": "busy", "healthy": True,
                "pipeline": {"stage": "PR"},
                "last_report": "",
            }
        self._post("/worker/phase-change", {
            "worker_id": "w3",
            "task_num": 1,
            "old_phase": "PR",
            "new_phase": "idle",
        })
        with gd._fleet_roster_lock:
            entry = gd._fleet_roster.get("w3")
        self.assertEqual(entry["status"], "idle")

    def test_phase_change_updates_board(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster["w4"] = {
                "status": "busy", "healthy": True,
                "pipeline": {"stage": "PLAN"},
                "last_report": "",
                "task": {"description": "test task"},
            }
        self._post("/worker/phase-change", {
            "worker_id": "w4",
            "task_num": 1,
            "old_phase": "PLAN",
            "new_phase": "TESTS",
        })
        # Board should be updated (check via endpoint)
        status, board = self._get("/board")
        self.assertEqual(status, 200)
        # Worker phase should reflect the change
        w4_entries = [w for w in board["workers"] if w["worker_id"] == "w4"]
        self.assertEqual(len(w4_entries), 1)
        self.assertEqual(w4_entries[0]["phase"], "TESTS")

    def test_unknown_worker_still_returns_200(self):
        """Phase change for unregistered worker doesn't crash."""
        status, data = self._post("/worker/phase-change", {
            "worker_id": "unknown-w",
            "task_num": 1,
            "old_phase": "A",
            "new_phase": "B",
        })
        self.assertEqual(status, 200)

    def test_gate_result_logged(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster["w5"] = {
                "status": "busy", "healthy": True,
                "pipeline": {"stage": "VERIFY"},
                "last_report": "",
            }
        status, data = self._post("/worker/phase-change", {
            "worker_id": "w5",
            "task_num": 2,
            "old_phase": "VERIFY",
            "new_phase": "PR",
            "gate_result": "all_tests_passed",
        })
        self.assertEqual(status, 200)
        self.assertEqual(data["phase"], "PR")


if __name__ == "__main__":
    unittest.main()
