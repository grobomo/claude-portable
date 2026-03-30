#!/usr/bin/env python3
"""Tests for /api/verify/TASKID and /worker/verify endpoints."""

import json
import os
import sys
import threading
import time
import unittest
from http.server import HTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# Add scripts dir to path so we can import the dispatcher module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


def _import_dispatcher():
    """Import git-dispatch module (has hyphen in filename)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "git_dispatch",
        os.path.join(os.path.dirname(__file__), "..", "scripts", "git-dispatch.py"),
    )
    mod = importlib.util.load_module("git_dispatch", *importlib.util.module_from_spec(spec).__spec__.loader.load_module.__func__.__code__.co_consts[:0], spec)
    return mod


# Simpler approach: just start the server directly
def get_dispatcher():
    import importlib.util
    path = os.path.join(os.path.dirname(__file__), "..", "scripts", "git-dispatch.py")
    spec = importlib.util.spec_from_file_location("git_dispatch", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestVerifyEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dispatcher = get_dispatcher()
        # Find a free port
        cls.port = 18932
        cls.server = HTTPServer(("127.0.0.1", cls.port), cls.dispatcher.HealthHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"
        # Set a token for auth endpoints
        os.environ["DISPATCH_API_TOKEN"] = "test-token-123"
        cls.dispatcher.DISPATCH_API_TOKEN = "test-token-123"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def _post(self, path, data, auth=False):
        body = json.dumps(data).encode()
        req = Request(
            f"{self.base}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        if auth:
            req.add_header("Authorization", "Bearer test-token-123")
        return urlopen(req, timeout=5)

    def _get(self, path):
        req = Request(f"{self.base}{path}")
        return urlopen(req, timeout=5)

    def test_verify_not_found(self):
        """GET /api/verify/nonexistent returns 404."""
        try:
            self._get("/api/verify/nonexistent-task")
            self.fail("Expected 404")
        except HTTPError as e:
            self.assertEqual(e.code, 404)
            data = json.loads(e.read())
            self.assertIn("No verification results found", data["error"])

    def test_worker_verify_submit_and_retrieve(self):
        """POST /worker/verify then GET /api/verify/TASKID."""
        task_id = "test-task-42"
        verify_data = {
            "worker_id": "worker-1",
            "task_id": task_id,
            "task_num": 42,
            "results": {
                "overall": "pass",
                "pass": 5,
                "fail": 0,
                "warn": 1,
                "base_branch": "main",
                "checks": [
                    {"name": "shell_syntax", "result": "pass", "detail": "All good"},
                    {"name": "secret_scan", "result": "pass", "detail": "No secrets"},
                    {"name": "tests", "result": "pass", "detail": "5 passed"},
                    {"name": "python_syntax", "result": "pass", "detail": "OK"},
                    {"name": "line_endings", "result": "pass", "detail": "LF"},
                    {"name": "todo_markers", "result": "warn", "detail": "1 TODO"},
                ],
            },
        }

        # Submit verification results
        resp = self._post("/worker/verify", verify_data)
        self.assertEqual(resp.status, 200)
        body = json.loads(resp.read())
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["task_id"], task_id)
        self.assertEqual(body["overall"], "pass")

        # Retrieve verification results
        resp = self._get(f"/api/verify/{task_id}")
        self.assertEqual(resp.status, 200)
        body = json.loads(resp.read())
        self.assertEqual(body["task_id"], task_id)
        self.assertEqual(body["worker_id"], "worker-1")
        self.assertEqual(body["overall"], "pass")
        self.assertEqual(body["pass"], 5)
        self.assertEqual(body["fail"], 0)
        self.assertEqual(body["warn"], 1)
        self.assertEqual(len(body["checks"]), 6)

    def test_worker_verify_missing_task_id(self):
        """POST /worker/verify without task_id returns 400."""
        try:
            self._post("/worker/verify", {"worker_id": "w1", "results": {}})
            self.fail("Expected 400")
        except HTTPError as e:
            self.assertEqual(e.code, 400)

    def test_worker_verify_with_task_num_only(self):
        """POST /worker/verify with only task_num uses it as task_id."""
        verify_data = {
            "worker_id": "worker-2",
            "task_num": 99,
            "results": {
                "overall": "fail",
                "pass": 3,
                "fail": 2,
                "warn": 0,
                "checks": [
                    {"name": "tests", "result": "fail", "detail": "2 failed"},
                ],
            },
        }
        resp = self._post("/worker/verify", verify_data)
        self.assertEqual(resp.status, 200)
        body = json.loads(resp.read())
        self.assertEqual(body["task_id"], "99")

        # Retrieve by task_num as string
        resp = self._get("/api/verify/99")
        self.assertEqual(resp.status, 200)
        body = json.loads(resp.read())
        self.assertEqual(body["overall"], "fail")
        self.assertEqual(body["fail"], 2)

    def test_verify_updates_fleet_roster(self):
        """POST /worker/verify updates the fleet roster entry."""
        worker_id = "roster-test-worker"
        # Pre-populate roster
        with self.dispatcher._fleet_roster_lock:
            self.dispatcher._fleet_roster[worker_id] = {
                "status": "busy",
                "last_report": "",
            }

        self._post("/worker/verify", {
            "worker_id": worker_id,
            "task_id": "roster-test-task",
            "results": {"overall": "pass", "pass": 1, "fail": 0, "warn": 0, "checks": []},
        })

        with self.dispatcher._fleet_roster_lock:
            entry = self.dispatcher._fleet_roster.get(worker_id, {})
        self.assertEqual(entry.get("verify_result"), "pass")
        self.assertIn("last_verify", entry)


if __name__ == "__main__":
    unittest.main()
