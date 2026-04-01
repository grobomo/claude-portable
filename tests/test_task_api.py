#!/usr/bin/env python3
"""Tests for task management API endpoints in git-dispatch.py."""

import importlib.machinery
import importlib.util
import json
import os
import threading
import time
import unittest
from http.client import HTTPConnection
from http.server import HTTPServer

# ── Load git-dispatch.py ─────────────────────────────────────────────────────

_gd_path = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "scripts", "git-dispatch.py"
))
_gd_loader = importlib.machinery.SourceFileLoader("git_dispatch", _gd_path)
_gd_spec = importlib.util.spec_from_loader("git_dispatch", _gd_loader)
gd = importlib.util.module_from_spec(_gd_spec)
_gd_loader.exec_module(gd)

TEST_TOKEN = "test-secret-token-12345"
TEST_PORT = 18199


def _request(method, path, body=None, token=TEST_TOKEN):
    """Send an HTTP request and return (status, parsed_json)."""
    conn = HTTPConnection("127.0.0.1", TEST_PORT, timeout=5)
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    payload = json.dumps(body).encode() if body else None
    if payload:
        headers["Content-Length"] = str(len(payload))
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    data = resp.read().decode()
    conn.close()
    try:
        return resp.status, json.loads(data)
    except json.JSONDecodeError:
        return resp.status, data


class TestTaskAPI(unittest.TestCase):
    """Test task management API endpoints."""

    @classmethod
    def setUpClass(cls):
        # Set the API token
        gd.DISPATCH_API_TOKEN = TEST_TOKEN
        # Clear task store
        with gd._task_store_lock:
            gd._task_store.clear()
        # Start the server
        cls.server = HTTPServer(("127.0.0.1", TEST_PORT), gd.HealthHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.2)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        # Clear task store before each test
        with gd._task_store_lock:
            gd._task_store.clear()

    # ── Auth tests ─────────────────────────────────────────────────────

    def test_no_auth_header_returns_401(self):
        status, data = _request("POST", "/task", {"text": "hello", "sender": "test"}, token=None)
        self.assertEqual(status, 401)
        self.assertIn("Missing", data["error"])

    def test_wrong_token_returns_403(self):
        status, data = _request("POST", "/task", {"text": "hello", "sender": "test"}, token="wrong")
        self.assertEqual(status, 403)
        self.assertIn("Invalid", data["error"])

    def test_no_token_configured_returns_503(self):
        original = gd.DISPATCH_API_TOKEN
        gd.DISPATCH_API_TOKEN = ""
        try:
            status, data = _request("POST", "/task", {"text": "hello", "sender": "test"})
            self.assertEqual(status, 503)
            self.assertIn("not configured", data["error"])
        finally:
            gd.DISPATCH_API_TOKEN = original

    # ── POST /task ─────────────────────────────────────────────────────

    def test_create_task(self):
        status, data = _request("POST", "/task", {
            "text": "Deploy new version",
            "sender": "joel",
            "priority": "high",
        })
        self.assertEqual(status, 201)
        self.assertEqual(data["text"], "Deploy new version")
        self.assertEqual(data["sender"], "joel")
        self.assertEqual(data["priority"], "high")
        self.assertEqual(data["state"], "PENDING")
        self.assertIsNotNone(data["id"])
        self.assertIsNotNone(data["created_at"])
        self.assertEqual(data["retries"], 0)

    def test_create_task_defaults(self):
        status, data = _request("POST", "/task", {"text": "simple task", "sender": "test"})
        self.assertEqual(status, 201)
        self.assertEqual(data["sender"], "test")
        self.assertEqual(data["priority"], "normal")

    def test_create_task_empty_text_returns_400(self):
        status, data = _request("POST", "/task", {"text": "", "sender": "test"})
        self.assertEqual(status, 400)
        self.assertIn("text", data.get("fields", {}))

    def test_create_task_missing_text_returns_400(self):
        status, data = _request("POST", "/task", {"sender": "joel"})
        self.assertEqual(status, 400)

    def test_create_task_invalid_priority_returns_400(self):
        status, data = _request("POST", "/task", {"text": "x", "sender": "test", "priority": "urgent"})
        self.assertEqual(status, 400)
        self.assertIn("priority", data.get("fields", {}))

    # ── GET /task/{id} ─────────────────────────────────────────────────

    def test_get_task_by_id(self):
        _, created = _request("POST", "/task", {"text": "fetch me", "sender": "test"})
        task_id = created["id"]
        status, data = _request("GET", f"/task/{task_id}")
        self.assertEqual(status, 200)
        self.assertEqual(data["id"], task_id)
        self.assertEqual(data["text"], "fetch me")

    def test_get_task_not_found(self):
        status, data = _request("GET", "/task/nonexistent-id")
        self.assertEqual(status, 404)

    # ── GET /tasks ─────────────────────────────────────────────────────

    def test_list_all_tasks(self):
        _request("POST", "/task", {"text": "task 1", "sender": "test"})
        _request("POST", "/task", {"text": "task 2", "sender": "test"})
        status, data = _request("GET", "/tasks")
        self.assertEqual(status, 200)
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["tasks"]), 2)

    def test_list_tasks_filter_by_status(self):
        _, t1 = _request("POST", "/task", {"text": "task 1", "sender": "test"})
        _, t2 = _request("POST", "/task", {"text": "task 2", "sender": "test"})
        # Move t2 to RUNNING
        _request("POST", f"/task/{t2['id']}", {"state": "RUNNING"})
        status, data = _request("GET", "/tasks?status=pending")
        self.assertEqual(status, 200)
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["tasks"][0]["id"], t1["id"])

    def test_list_tasks_empty(self):
        status, data = _request("GET", "/tasks")
        self.assertEqual(status, 200)
        self.assertEqual(data["count"], 0)

    # ── DELETE /task/{id} ──────────────────────────────────────────────

    def test_cancel_pending_task(self):
        _, created = _request("POST", "/task", {"text": "cancel me", "sender": "test"})
        task_id = created["id"]
        status, data = _request("DELETE", f"/task/{task_id}")
        self.assertEqual(status, 200)
        self.assertEqual(data["state"], "CANCELLED")

    def test_cancel_running_task(self):
        _, created = _request("POST", "/task", {"text": "running", "sender": "test"})
        task_id = created["id"]
        _request("POST", f"/task/{task_id}", {"state": "RUNNING"})
        status, data = _request("DELETE", f"/task/{task_id}")
        self.assertEqual(status, 200)
        self.assertEqual(data["state"], "CANCELLED")

    def test_cancel_completed_task_returns_409(self):
        _, created = _request("POST", "/task", {"text": "done", "sender": "test"})
        task_id = created["id"]
        _request("POST", f"/task/{task_id}", {"state": "COMPLETED"})
        status, data = _request("DELETE", f"/task/{task_id}")
        self.assertEqual(status, 409)
        self.assertIn("Cannot cancel", data["error"])

    def test_cancel_already_cancelled_returns_409(self):
        _, created = _request("POST", "/task", {"text": "x", "sender": "test"})
        task_id = created["id"]
        _request("DELETE", f"/task/{task_id}")
        status, data = _request("DELETE", f"/task/{task_id}")
        self.assertEqual(status, 409)

    def test_cancel_nonexistent_returns_404(self):
        status, data = _request("DELETE", "/task/no-such-id")
        self.assertEqual(status, 404)

    # ── POST /task/{id}/retry ──────────────────────────────────────────

    def test_retry_failed_task(self):
        _, created = _request("POST", "/task", {"text": "fail and retry", "sender": "test"})
        task_id = created["id"]
        # Move to FAILED
        _request("POST", f"/task/{task_id}", {"state": "FAILED", "error": "boom"})
        status, data = _request("POST", f"/task/{task_id}/retry")
        self.assertEqual(status, 200)
        self.assertEqual(data["state"], "PENDING")
        self.assertEqual(data["retries"], 1)
        self.assertIsNone(data["error"])

    def test_retry_non_failed_returns_409(self):
        _, created = _request("POST", "/task", {"text": "not failed", "sender": "test"})
        task_id = created["id"]
        status, data = _request("POST", f"/task/{task_id}/retry")
        self.assertEqual(status, 409)
        self.assertIn("FAILED", data["error"])

    def test_retry_nonexistent_returns_404(self):
        status, data = _request("POST", "/task/no-such-id/retry")
        self.assertEqual(status, 404)

    def test_retry_increments_counter(self):
        _, created = _request("POST", "/task", {"text": "multi retry", "sender": "test"})
        task_id = created["id"]
        for i in range(3):
            _request("POST", f"/task/{task_id}", {"state": "FAILED", "error": f"fail {i}"})
            _request("POST", f"/task/{task_id}/retry")
        status, data = _request("GET", f"/task/{task_id}")
        self.assertEqual(data["retries"], 3)

    # ── POST /task/{id} (state update) ─────────────────────────────────

    def test_update_task_state(self):
        _, created = _request("POST", "/task", {"text": "update me", "sender": "test"})
        task_id = created["id"]
        status, data = _request("POST", f"/task/{task_id}", {"state": "DISPATCHED"})
        self.assertEqual(status, 200)
        self.assertEqual(data["state"], "DISPATCHED")
        self.assertIsNotNone(data["dispatched_at"])

    def test_update_task_progress(self):
        _, created = _request("POST", "/task", {"text": "progress", "sender": "test"})
        task_id = created["id"]
        _request("POST", f"/task/{task_id}", {"state": "RUNNING", "progress": "50%"})
        status, data = _request("GET", f"/task/{task_id}")
        self.assertEqual(data["progress"], "50%")

    def test_update_task_result(self):
        _, created = _request("POST", "/task", {"text": "result", "sender": "test"})
        task_id = created["id"]
        _request("POST", f"/task/{task_id}", {"state": "COMPLETED", "result": "PR #42 merged"})
        status, data = _request("GET", f"/task/{task_id}")
        self.assertEqual(data["state"], "COMPLETED")
        self.assertEqual(data["result"], "PR #42 merged")
        self.assertIsNotNone(data["completed_at"])

    # ── State transitions ──────────────────────────────────────────────

    def test_full_lifecycle(self):
        """PENDING -> DISPATCHED -> RUNNING -> COMPLETED."""
        _, task = _request("POST", "/task", {
            "text": "full lifecycle", "sender": "test", "priority": "high",
        })
        tid = task["id"]
        self.assertEqual(task["state"], "PENDING")

        _, task = _request("POST", f"/task/{tid}", {"state": "DISPATCHED"})
        self.assertEqual(task["state"], "DISPATCHED")

        _, task = _request("POST", f"/task/{tid}", {"state": "RUNNING", "progress": "starting"})
        self.assertEqual(task["state"], "RUNNING")

        _, task = _request("POST", f"/task/{tid}", {
            "state": "COMPLETED", "result": "done", "progress": "100%",
        })
        self.assertEqual(task["state"], "COMPLETED")
        self.assertIsNotNone(task["completed_at"])

    def test_failed_lifecycle(self):
        """PENDING -> DISPATCHED -> RUNNING -> FAILED -> retry -> PENDING."""
        _, task = _request("POST", "/task", {"text": "fail lifecycle", "sender": "test"})
        tid = task["id"]
        _request("POST", f"/task/{tid}", {"state": "RUNNING"})
        _request("POST", f"/task/{tid}", {"state": "FAILED", "error": "OOM"})

        _, task = _request("GET", f"/task/{tid}")
        self.assertEqual(task["state"], "FAILED")
        self.assertEqual(task["error"], "OOM")

        _, task = _request("POST", f"/task/{tid}/retry")
        self.assertEqual(task["state"], "PENDING")
        self.assertEqual(task["retries"], 1)
        self.assertIsNone(task["error"])


if __name__ == "__main__":
    unittest.main()
