#!/usr/bin/env python3
"""Tests for worker-health.py pipeline HTTP endpoints.

Validates:
- GET /status returns pipeline state
- POST /phase sets current phase
- POST /gate records gate results
- Pipeline state functions (get/set/record/idle)
"""

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
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

loader = importlib.machinery.SourceFileLoader(
    "worker_health",
    os.path.join(os.path.dirname(__file__), "..", "scripts", "worker-health.py"),
)
spec = importlib.util.spec_from_loader("worker_health", loader)
wh = importlib.util.module_from_spec(spec)
loader.exec_module(wh)


class TestPipelineStateFunctions(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig = wh.PIPELINE_STATE_FILE
        wh.PIPELINE_STATE_FILE = os.path.join(self.tmpdir, "pipeline-state.json")

    def tearDown(self):
        wh.PIPELINE_STATE_FILE = self._orig

    def test_initial_state_is_idle(self):
        state = wh.get_pipeline_state()
        self.assertEqual(state["phase"], "idle")
        self.assertIsNone(state["task_num"])

    def test_set_phase_writes_and_reads(self):
        wh.set_pipeline_phase(1, "RESEARCH")
        state = wh.get_pipeline_state()
        self.assertEqual(state["phase"], "RESEARCH")
        self.assertEqual(state["task_num"], 1)

    def test_phase_history_tracked(self):
        wh.set_pipeline_phase(1, "RESEARCH")
        wh.set_pipeline_phase(1, "REVIEW")
        state = wh.get_pipeline_state()
        self.assertEqual(len(state["phase_history"]), 2)

    def test_gate_result(self):
        wh.set_pipeline_phase(1, "RESEARCH")
        wh.record_gate_result(1, "RESEARCH", True, "ok")
        state = wh.get_pipeline_state()
        self.assertTrue(state["gates"]["RESEARCH"]["passed"])

    def test_new_task_resets(self):
        wh.set_pipeline_phase(1, "RESEARCH")
        wh.set_pipeline_phase(2, "RESEARCH")
        state = wh.get_pipeline_state()
        self.assertEqual(state["task_num"], 2)
        self.assertEqual(len(state["phase_history"]), 1)

    def test_set_idle(self):
        wh.set_pipeline_phase(1, "PLAN")
        wh.set_pipeline_idle()
        state = wh.get_pipeline_state()
        self.assertEqual(state["phase"], "idle")
        self.assertIsNone(state["task_num"])


class TestPipelineHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp()
        wh.PIPELINE_STATE_FILE = os.path.join(cls.tmpdir, "pipeline-state.json")
        import socket
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        cls.port = s.getsockname()[1]
        s.close()
        from http.server import HTTPServer
        cls.server = HTTPServer(("127.0.0.1", cls.port), wh.WorkerHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def _get(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        resp = urllib.request.urlopen(url, timeout=5)
        return json.loads(resp.read())

    def _post(self, path, data):
        url = f"http://127.0.0.1:{self.port}{path}"
        body = json.dumps(data).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=5)
        return json.loads(resp.read())

    def test_get_status(self):
        resp = self._get("/status")
        self.assertIn("phase", resp)
        self.assertIn("task_num", resp)

    def test_post_phase(self):
        resp = self._post("/phase", {"task_num": 5, "phase": "PLAN"})
        self.assertEqual(resp["status"], "ok")
        state = self._get("/status")
        self.assertEqual(state["phase"], "PLAN")
        self.assertEqual(state["task_num"], 5)

    def test_post_gate(self):
        self._post("/phase", {"task_num": 5, "phase": "RESEARCH"})
        resp = self._post("/gate", {
            "task_num": 5, "phase": "RESEARCH",
            "passed": True, "detail": "1500 chars"
        })
        self.assertEqual(resp["status"], "ok")
        state = self._get("/status")
        self.assertIn("RESEARCH", state["gates"])
        self.assertTrue(state["gates"]["RESEARCH"]["passed"])


if __name__ == "__main__":
    unittest.main()
