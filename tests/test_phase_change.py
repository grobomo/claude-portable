#!/usr/bin/env python3
"""Tests for immediate phase transition events (worker -> dispatcher)."""

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

_wh_path = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "scripts", "worker-health.py"
))
_wh_loader = importlib.machinery.SourceFileLoader("worker_health", _wh_path)
_wh_spec = importlib.util.spec_from_loader("worker_health", _wh_loader)
wh = importlib.util.module_from_spec(_wh_spec)
_wh_loader.exec_module(wh)

_wp_path = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "scripts", "worker-pipeline.py"
))
_wp_loader = importlib.machinery.SourceFileLoader("worker_pipeline", _wp_path)
_wp_spec = importlib.util.spec_from_loader("worker_pipeline", _wp_loader)
wp = importlib.util.module_from_spec(_wp_spec)
_wp_loader.exec_module(wp)

_gd_path = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "scripts", "git-dispatch.py"
))
_gd_loader = importlib.machinery.SourceFileLoader("git_dispatch", _gd_path)
_gd_spec = importlib.util.spec_from_loader("git_dispatch", _gd_loader)
gd = importlib.util.module_from_spec(_gd_spec)
_gd_loader.exec_module(gd)


# ── Worker-side: send_phase_change ───────────────────────────────────────────

class TestSendPhaseChange(unittest.TestCase):
    """Test worker-health.py send_phase_change function."""

    def setUp(self):
        self.received = []
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length) if length else b"{}"
                parent.received.append(json.loads(body))
                resp = b'{"status": "ok"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self._orig_id = wh.WORKER_ID
        wh.WORKER_ID = "phase-test"

    def tearDown(self):
        self.server.shutdown()
        wh.WORKER_ID = self._orig_id

    def test_sends_phase_change_to_dispatcher(self):
        url = f"http://127.0.0.1:{self.port}"
        result = wh.send_phase_change(url, 3, "RESEARCH", "PLAN")
        self.assertTrue(result)
        self.assertEqual(len(self.received), 1)
        p = self.received[0]
        self.assertEqual(p["worker_id"], "phase-test")
        self.assertEqual(p["task_num"], 3)
        self.assertEqual(p["old_phase"], "RESEARCH")
        self.assertEqual(p["new_phase"], "PLAN")
        self.assertIn("timestamp", p)

    def test_returns_false_on_error(self):
        result = wh.send_phase_change("http://127.0.0.1:1", 1, "A", "B")
        self.assertFalse(result)

    def test_gate_result_included(self):
        url = f"http://127.0.0.1:{self.port}"
        wh.send_phase_change(url, 2, "TESTS", "IMPLEMENT", gate_result="passed")
        self.assertEqual(self.received[0]["gate_result"], "passed")


# ── Dispatcher-side: /worker/phase-change endpoint ───────────────────────────

class TestDispatcherPhaseChangeEndpoint(unittest.TestCase):
    """Test POST /worker/phase-change on the dispatcher."""

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

    def test_phase_change_returns_200(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster["w1"] = {"status": "idle", "pipeline": {}}
        status, data = self._post("/worker/phase-change", {
            "worker_id": "w1",
            "task_num": 5,
            "old_phase": "RESEARCH",
            "new_phase": "PLAN",
        })
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["phase"], "PLAN")

    def test_phase_change_updates_roster(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster["w2"] = {"status": "idle", "pipeline": {"stage": "idle"}}
        self._post("/worker/phase-change", {
            "worker_id": "w2",
            "task_num": 1,
            "old_phase": None,
            "new_phase": "RESEARCH",
        })
        with gd._fleet_roster_lock:
            entry = gd._fleet_roster.get("w2")
        self.assertEqual(entry["pipeline"]["stage"], "RESEARCH")
        self.assertEqual(entry["status"], "busy")

    def test_phase_change_to_idle(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster["w3"] = {"status": "busy", "pipeline": {"stage": "VERIFY"}}
        self._post("/worker/phase-change", {
            "worker_id": "w3",
            "new_phase": "idle",
        })
        with gd._fleet_roster_lock:
            entry = gd._fleet_roster.get("w3")
        self.assertEqual(entry["status"], "idle")

    def test_phase_change_unknown_worker_still_ok(self):
        """Phase change for unregistered worker doesn't crash."""
        status, data = self._post("/worker/phase-change", {
            "worker_id": "ghost",
            "new_phase": "TESTS",
        })
        self.assertEqual(status, 200)


# ── Worker-pipeline.py integration ───────────────────────────────────────────

class TestPipelinePhaseNotification(unittest.TestCase):
    """Test that worker-pipeline.py cmd_phase triggers phase-change notification."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.tmpdir, "pipeline-state.json")
        self._orig = wp.STATE_FILE
        wp.STATE_FILE = self.state_file
        wp.cmd_start(["1", "Test", "task"])

    def tearDown(self):
        wp.STATE_FILE = self._orig
        wp.DISPATCHER_URL = ""
        os.environ.pop("DISPATCHER_URL", None)
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_phase_stores_prev_phase(self):
        """cmd_phase tracks _prev_phase in state for transition events."""
        wp.cmd_phase(["RESEARCH", "running"])
        with open(self.state_file) as f:
            state = json.load(f)
        self.assertEqual(state.get("_prev_phase"), "RESEARCH")

        wp.cmd_phase(["PLAN", "running"])
        with open(self.state_file) as f:
            state = json.load(f)
        self.assertEqual(state.get("_prev_phase"), "PLAN")

    def test_phase_change_sent_on_running(self):
        """When DISPATCHER_URL is set and phase goes to running, notification is sent."""
        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length) if length else b"{}"
                received.append(json.loads(body))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')

            def log_message(self, *a):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()

        os.environ["DISPATCHER_URL"] = f"http://127.0.0.1:{port}"
        wp.DISPATCHER_URL = f"http://127.0.0.1:{port}"
        wp.cmd_phase(["RESEARCH", "running"])
        server.shutdown()

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["new_phase"], "RESEARCH")

    def test_no_notification_on_passed(self):
        """Phase 'passed' does not trigger notification (only 'running' does)."""
        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                self.rfile.read(length)
                received.append(True)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')

            def log_message(self, *a):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()

        os.environ["DISPATCHER_URL"] = f"http://127.0.0.1:{port}"
        wp.cmd_phase(["RESEARCH", "passed"])
        server.shutdown()

        self.assertEqual(len(received), 0)


if __name__ == "__main__":
    unittest.main()
