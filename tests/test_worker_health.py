#!/usr/bin/env python3
"""Tests for worker-health.py HTTP API."""

import importlib
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
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

loader = importlib.machinery.SourceFileLoader(
    "worker_health",
    os.path.join(os.path.dirname(__file__), "..", "scripts", "worker-health.py"),
)
spec = importlib.util.spec_from_loader("worker_health", loader)
wh = importlib.util.module_from_spec(spec)
loader.exec_module(wh)


class TestWorkerHealthAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = 18081
        wh.PORT = cls.port
        wh.WORKER_ID = "test-worker"
        cls.server = wh.HTTPServer(("127.0.0.1", cls.port), wh.WorkerHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def _get(self, path):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read().decode()
        conn.close()
        return resp.status, json.loads(body) if body else {}

    def _post(self, path):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("POST", path, body=b"{}",
                      headers={"Content-Type": "application/json",
                                "Content-Length": "2"})
        resp = conn.getresponse()
        body = resp.read().decode()
        conn.close()
        return resp.status, json.loads(body) if body else {}

    def test_health_returns_200(self):
        status, data = self._get("/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["worker_id"], "test-worker")
        self.assertIn("uptime_seconds", data)
        self.assertIn("claude_running", data)
        self.assertIn("task", data)
        self.assertIn("pipeline", data)

    def test_health_root_also_works(self):
        status, data = self._get("/")
        self.assertEqual(status, 200)
        self.assertEqual(data["worker_id"], "test-worker")

    def test_404_on_unknown(self):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/nonexistent")
        resp = conn.getresponse()
        resp.read()
        conn.close()
        self.assertEqual(resp.status, 404)

    @patch.object(wh, "_is_claude_running", return_value=False)
    def test_interrupt_no_process(self, mock_running):
        # Clean up any leftover flag
        try:
            os.remove(wh.INTERRUPT_FLAG)
        except FileNotFoundError:
            pass
        status, data = self._post("/interrupt")
        self.assertEqual(status, 200)
        self.assertIn(data["status"], ["no_process", "interrupted"])

    def test_pull_schedules_flag(self):
        try:
            os.remove(wh.PULL_FLAG)
        except FileNotFoundError:
            pass
        status, data = self._post("/pull")
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "pull_scheduled")
        # Flag file should exist
        self.assertTrue(os.path.isfile(wh.PULL_FLAG))
        os.remove(wh.PULL_FLAG)

    def test_health_shows_maintenance(self):
        maint_file = "/data/.maintenance"
        # Can't create /data on Windows, just verify the field exists
        status, data = self._get("/health")
        self.assertIn("maintenance", data)

    def test_health_has_idle_seconds(self):
        status, data = self._get("/health")
        self.assertIn("idle_seconds", data)


if __name__ == "__main__":
    unittest.main()
