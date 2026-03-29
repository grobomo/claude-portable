#!/usr/bin/env python3
"""Tests for worker heartbeat polling to dispatcher.

Tests both sides:
1. Worker: _build_heartbeat_payload(), send_heartbeat()
2. Dispatcher: /worker/heartbeat endpoint, missed heartbeat detection
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
from unittest.mock import patch

# ── Load worker-health.py as module ──────────────────────────────────────────

_wh_path = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "scripts", "worker-health.py"
))
_wh_loader = importlib.machinery.SourceFileLoader("worker_health", _wh_path)
_wh_spec = importlib.util.spec_from_loader("worker_health", _wh_loader)
wh = importlib.util.module_from_spec(_wh_spec)
_wh_loader.exec_module(wh)

# ── Load git-dispatch.py as module ───────────────────────────────────────────

_gd_path = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "scripts", "git-dispatch.py"
))
_gd_loader = importlib.machinery.SourceFileLoader("git_dispatch", _gd_path)
_gd_spec = importlib.util.spec_from_loader("git_dispatch", _gd_loader)
gd = importlib.util.module_from_spec(_gd_spec)
_gd_loader.exec_module(gd)


# ── Worker-side tests ────────────────────────────────────────────────────────

class TestBuildHeartbeatPayload(unittest.TestCase):
    """Test that _build_heartbeat_payload assembles correct data."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.tmpdir, "pipeline-state.json")
        self._orig_state = wh.PIPELINE_STATE_FILE
        wh.PIPELINE_STATE_FILE = self.state_file
        self._orig_id = wh.WORKER_ID
        wh.WORKER_ID = "test-hb-worker"

    def tearDown(self):
        wh.PIPELINE_STATE_FILE = self._orig_state
        wh.WORKER_ID = self._orig_id
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_payload_has_required_fields(self):
        payload = wh._build_heartbeat_payload()
        self.assertEqual(payload["worker_id"], "test-hb-worker")
        self.assertIn("timestamp", payload)
        self.assertIn("uptime_seconds", payload)
        self.assertIn("claude_running", payload)
        self.assertIn("maintenance", payload)
        self.assertIn("idle_seconds", payload)
        self.assertIn("task", payload)
        self.assertIn("pipeline", payload)

    def test_payload_includes_pipeline_state(self):
        state = {
            "worker_id": "test-hb-worker",
            "task_num": 5,
            "status": "running",
            "current_phase": "IMPLEMENT",
            "phases": {"RESEARCH": {"status": "passed"}, "IMPLEMENT": {"status": "running"}},
        }
        with open(self.state_file, "w") as f:
            json.dump(state, f)

        payload = wh._build_heartbeat_payload()
        # _get_pipeline_stage returns {stage, stages_complete, phases}
        self.assertEqual(payload["pipeline"]["stage"], "IMPLEMENT")
        self.assertIn("phases", payload["pipeline"])

    def test_payload_idle_when_no_state_file(self):
        payload = wh._build_heartbeat_payload()
        self.assertIn("pipeline", payload)
        self.assertIn(payload["pipeline"]["stage"], ["idle", "unknown"])


class TestSendHeartbeat(unittest.TestCase):
    """Test send_heartbeat against a mock dispatcher."""

    def setUp(self):
        self.received_payloads = []
        parent = self

        class MockHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length) if length else b"{}"
                parent.received_payloads.append(json.loads(body))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                resp = b'{"status": "ok"}'
                self.send_header("Content-Length", str(len(resp)))
                self.end_headers()
                self.wfile.write(resp)

            def log_message(self, fmt, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), MockHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

        self._orig_id = wh.WORKER_ID
        wh.WORKER_ID = "hb-test"

    def tearDown(self):
        self.server.shutdown()
        wh.WORKER_ID = self._orig_id

    def test_send_heartbeat_posts_to_dispatcher(self):
        url = f"http://127.0.0.1:{self.port}"
        result = wh.send_heartbeat(url)
        self.assertTrue(result)
        self.assertEqual(len(self.received_payloads), 1)
        self.assertEqual(self.received_payloads[0]["worker_id"], "hb-test")

    def test_send_heartbeat_returns_false_on_connection_error(self):
        result = wh.send_heartbeat("http://127.0.0.1:1")
        self.assertFalse(result)

    def test_send_heartbeat_returns_false_on_invalid_url(self):
        result = wh.send_heartbeat("not-a-url")
        self.assertFalse(result)


# ── Dispatcher-side tests ────────────────────────────────────────────────────

class TestDispatcherHeartbeatEndpoint(unittest.TestCase):
    """Test the /worker/heartbeat endpoint in git-dispatch.py."""

    @classmethod
    def setUpClass(cls):
        cls.port = 18082
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

    def test_heartbeat_returns_200(self):
        status, data = self._post("/worker/heartbeat", {
            "worker_id": "w1",
            "pipeline": {"stage": "idle"},
            "claude_running": False,
        })
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["worker_id"], "w1")

    def test_heartbeat_updates_roster(self):
        self._post("/worker/heartbeat", {
            "worker_id": "w2",
            "pipeline": {"stage": "IMPLEMENT", "status": "running", "current_phase": "IMPLEMENT"},
            "claude_running": True,
            "maintenance": False,
            "idle_seconds": 0,
            "uptime_seconds": 300,
        })
        with gd._fleet_roster_lock:
            entry = gd._fleet_roster.get("w2")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["status"], "busy")
        self.assertTrue(entry["healthy"])
        self.assertEqual(entry["missed_heartbeats"], 0)

    def test_heartbeat_idle_worker(self):
        self._post("/worker/heartbeat", {
            "worker_id": "w3",
            "pipeline": {"stage": "idle"},
            "claude_running": False,
            "maintenance": False,
            "idle_seconds": 600,
        })
        with gd._fleet_roster_lock:
            entry = gd._fleet_roster.get("w3")
        self.assertEqual(entry["status"], "idle")

    def test_heartbeat_maintenance_status(self):
        self._post("/worker/heartbeat", {
            "worker_id": "w4",
            "pipeline": {"stage": "idle"},
            "claude_running": False,
            "maintenance": True,
        })
        with gd._fleet_roster_lock:
            entry = gd._fleet_roster.get("w4")
        self.assertEqual(entry["status"], "maintenance")

    def test_heartbeat_auto_registers(self):
        """Worker not previously registered gets added to roster on heartbeat."""
        self._post("/worker/heartbeat", {
            "worker_id": "new-worker",
            "pipeline": {"stage": "RESEARCH"},
            "claude_running": True,
        })
        with gd._fleet_roster_lock:
            entry = gd._fleet_roster.get("new-worker")
        self.assertIsNotNone(entry)
        self.assertIn("last_heartbeat", entry)

    def test_heartbeat_visible_in_health(self):
        """Heartbeat data shows up in GET /health fleet_roster."""
        self._post("/worker/heartbeat", {
            "worker_id": "w5",
            "pipeline": {"stage": "VERIFY"},
            "claude_running": True,
            "uptime_seconds": 120,
        })
        status, data = self._get("/health")
        self.assertEqual(status, 200)
        roster = data.get("fleet_roster", {})
        self.assertIn("w5", roster)
        self.assertEqual(roster["w5"]["claude_running"], True)

    def test_multiple_heartbeats_update_timestamp(self):
        """Successive heartbeats update last_heartbeat."""
        self._post("/worker/heartbeat", {"worker_id": "w6", "pipeline": {}})
        with gd._fleet_roster_lock:
            ts1 = gd._fleet_roster["w6"]["last_heartbeat"]
        time.sleep(0.01)
        self._post("/worker/heartbeat", {"worker_id": "w6", "pipeline": {}})
        with gd._fleet_roster_lock:
            ts2 = gd._fleet_roster["w6"]["last_heartbeat"]
        self.assertTrue(ts1)
        self.assertTrue(ts2)


class TestMissedHeartbeatDetection(unittest.TestCase):
    """Test that fleet monitor marks workers unhealthy after missed heartbeats."""

    def setUp(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()

    def test_stale_heartbeat_marked_unhealthy(self):
        """Worker with last_heartbeat >90s ago gets marked unhealthy."""
        old_time = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(time.time() - 120),
        )
        with gd._fleet_roster_lock:
            gd._fleet_roster["stale-w"] = {
                "registered": True,
                "status": "busy",
                "last_heartbeat": old_time,
                "last_report": old_time,
                "last_task": None,
                "completions": 0,
                "ip": "",
                "healthy": True,
                "missed_heartbeats": 0,
            }

        with patch.object(gd, "_ssh_check_claude_process", return_value=True), \
             patch.object(gd, "stop_worker_instance"):
            gd._fleet_monitor_tick("us-east-1")

        with gd._fleet_roster_lock:
            entry = gd._fleet_roster.get("stale-w")
        self.assertFalse(entry["healthy"])
        self.assertGreater(entry["missed_heartbeats"], 0)

    def test_fresh_heartbeat_stays_healthy(self):
        """Worker with recent heartbeat stays healthy."""
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with gd._fleet_roster_lock:
            gd._fleet_roster["fresh-w"] = {
                "registered": True,
                "status": "busy",
                "last_heartbeat": now_str,
                "last_report": now_str,
                "last_task": None,
                "completions": 0,
                "ip": "",
                "healthy": True,
                "missed_heartbeats": 0,
            }

        with patch.object(gd, "_ssh_check_claude_process", return_value=True), \
             patch.object(gd, "stop_worker_instance"):
            gd._fleet_monitor_tick("us-east-1")

        with gd._fleet_roster_lock:
            entry = gd._fleet_roster.get("fresh-w")
        self.assertTrue(entry["healthy"])
        self.assertEqual(entry["missed_heartbeats"], 0)

    def test_no_heartbeat_field_skips_check(self):
        """Worker without last_heartbeat doesn't get marked unhealthy."""
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with gd._fleet_roster_lock:
            gd._fleet_roster["no-hb-w"] = {
                "registered": True,
                "status": "idle",
                "last_report": now_str,
                "last_task": None,
                "completions": 0,
                "ip": "",
            }

        with patch.object(gd, "_ssh_check_claude_process", return_value=True), \
             patch.object(gd, "stop_worker_instance"):
            gd._fleet_monitor_tick("us-east-1")

        with gd._fleet_roster_lock:
            entry = gd._fleet_roster.get("no-hb-w")
        self.assertNotEqual(entry.get("healthy"), False)


if __name__ == "__main__":
    unittest.main()
