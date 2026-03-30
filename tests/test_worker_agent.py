#!/usr/bin/env python3
"""Tests for worker-agent.py — heartbeat client + HTTP monitoring server."""

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
from unittest.mock import MagicMock, patch

# ── Load worker-agent.py as module ───────────────────────────────────────────

_wa_path = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "scripts", "worker-agent.py"
))
_wa_loader = importlib.machinery.SourceFileLoader("worker_agent", _wa_path)
_wa_spec = importlib.util.spec_from_loader("worker_agent", _wa_loader)
wa = importlib.util.module_from_spec(_wa_spec)

# Patch env before loading to avoid side effects
with patch.dict(os.environ, {
    "DISPATCHER_IP": "",
    "DISPATCH_API_TOKEN": "",
    "WORKER_ID": "test-worker",
    "WORKER_WORKDIR": "/tmp",
    "WORKSPACE": "/tmp",
    "WORKER_AGENT_PORT": "0",
}):
    _wa_loader.exec_module(wa)


# ── Git helper tests ─────────────────────────────────────────────────────────

class TestGitHelpers(unittest.TestCase):

    @patch("subprocess.run")
    def test_git_returns_stdout(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123\n")
        result = wa._git("rev-parse", "HEAD", cwd="/tmp")
        self.assertEqual(result, "abc123")

    @patch("subprocess.run")
    def test_git_returns_empty_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = wa._git("log", cwd="/tmp")
        self.assertEqual(result, "")

    @patch("subprocess.run", side_effect=OSError("no git"))
    def test_git_returns_empty_on_exception(self, mock_run):
        result = wa._git("status", cwd="/tmp")
        self.assertEqual(result, "")

    def test_get_last_commit_time_none(self):
        with patch.object(wa, "_git", return_value=""):
            self.assertIsNone(wa._get_last_commit_time())

    def test_get_last_commit_time_value(self):
        with patch.object(wa, "_git", return_value="2026-03-28T10:00:00-04:00"):
            self.assertEqual(wa._get_last_commit_time(), "2026-03-28T10:00:00-04:00")

    def test_get_files_changed_zero(self):
        with patch.object(wa, "_git", return_value=""):
            self.assertEqual(wa._get_files_changed(), 0)

    def test_get_files_changed_count(self):
        with patch.object(wa, "_git", return_value="file1.py\nfile2.py\nfile3.py"):
            self.assertEqual(wa._get_files_changed(), 3)


class TestNewCommitDetection(unittest.TestCase):

    def setUp(self):
        wa._last_seen_commit = None

    def test_first_call_returns_false(self):
        with patch.object(wa, "_git", return_value="abc123"):
            self.assertFalse(wa._detect_new_commit())
            self.assertEqual(wa._last_seen_commit, "abc123")

    def test_same_commit_returns_false(self):
        wa._last_seen_commit = "abc123"
        with patch.object(wa, "_git", return_value="abc123"):
            self.assertFalse(wa._detect_new_commit())

    def test_new_commit_returns_true(self):
        wa._last_seen_commit = "abc123"
        with patch.object(wa, "_git", return_value="def456"):
            self.assertTrue(wa._detect_new_commit())
            self.assertEqual(wa._last_seen_commit, "def456")

    def test_no_head_returns_false(self):
        wa._last_seen_commit = "abc123"
        with patch.object(wa, "_git", return_value=""):
            self.assertFalse(wa._detect_new_commit())


# ── Process detection tests ──────────────────────────────────────────────────

class TestProcessDetection(unittest.TestCase):

    @patch("subprocess.run")
    def test_claude_alive_true(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="12345\n")
        self.assertTrue(wa._is_claude_alive())

    @patch("subprocess.run")
    def test_claude_alive_false(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        self.assertFalse(wa._is_claude_alive())

    @patch("subprocess.run", side_effect=OSError("no pgrep"))
    def test_claude_alive_exception(self, mock_run):
        self.assertFalse(wa._is_claude_alive())

    @patch("subprocess.run")
    def test_find_claude_pid(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="9876\n")
        self.assertEqual(wa._find_claude_pid(), 9876)

    @patch("subprocess.run")
    def test_find_claude_pid_none(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        self.assertIsNone(wa._find_claude_pid())


# ── Heartbeat payload tests ──────────────────────────────────────────────────

class TestHeartbeat(unittest.TestCase):

    @patch.object(wa, "_post", return_value=(200, "ok"))
    @patch.object(wa, "_is_claude_alive", return_value=True)
    @patch.object(wa, "_get_files_changed", return_value=5)
    @patch.object(wa, "_get_last_commit_time", return_value="2026-03-28T10:00:00Z")
    @patch.object(wa, "_read_task_id", return_value="task-42")
    def test_send_heartbeat_success(self, *mocks):
        result = wa.send_heartbeat()
        self.assertTrue(result)
        post_mock = mocks[4]  # _post is outermost
        call_args = post_mock.call_args
        self.assertEqual(call_args[0][0], "/worker/heartbeat")
        payload = call_args[0][1]
        self.assertEqual(payload["worker_id"], "test-worker")
        self.assertEqual(payload["status"], "working")
        self.assertEqual(payload["task_id"], "task-42")
        self.assertTrue(payload["claude_alive"])
        self.assertEqual(payload["files_changed"], 5)

    @patch.object(wa, "_post", return_value=(500, "error"))
    @patch.object(wa, "_is_claude_alive", return_value=False)
    @patch.object(wa, "_get_files_changed", return_value=0)
    @patch.object(wa, "_get_last_commit_time", return_value=None)
    @patch.object(wa, "_read_task_id", return_value="")
    def test_send_heartbeat_failure(self, *mocks):
        result = wa.send_heartbeat()
        self.assertFalse(result)

    @patch.object(wa, "_post", return_value=(200, "ok"))
    def test_report_complete(self, mock_post):
        result = wa.report_complete("task-42", "all done")
        self.assertTrue(result)
        call_args = mock_post.call_args
        self.assertEqual(call_args[0][0], "/task/task-42/complete")
        self.assertEqual(call_args[0][1]["summary"], "all done")

    @patch.object(wa, "_post", return_value=(200, "ok"))
    def test_report_failure(self, mock_post):
        result = wa.report_failure("task-42", "crashed")
        self.assertTrue(result)
        call_args = mock_post.call_args
        self.assertEqual(call_args[0][0], "/task/task-42/fail")
        self.assertEqual(call_args[0][1]["reason"], "crashed")


# ── Task ID discovery tests ─────────────────────────────────────────────────

class TestTaskIdDiscovery(unittest.TestCase):

    def test_read_task_id_from_env(self):
        with patch.object(wa, "TASK_ID", "env-task-99"):
            self.assertEqual(wa._read_task_id(), "env-task-99")

    def test_read_task_id_from_file(self):
        # Create /data/.task-id temporarily if possible, otherwise skip
        data_dir = "/data"
        task_file = os.path.join(data_dir, ".task-id")
        created_dir = False
        try:
            if not os.path.isdir(data_dir):
                os.makedirs(data_dir, exist_ok=True)
                created_dir = True
            with open(task_file, "w") as f:
                f.write("file-task-7\n")
            with patch.object(wa, "TASK_ID", ""):
                self.assertEqual(wa._read_task_id(), "file-task-7")
        except PermissionError:
            self.skipTest("Cannot write to /data (no permissions)")
        finally:
            if os.path.exists(task_file):
                os.unlink(task_file)
            if created_dir and os.path.isdir(data_dir):
                try:
                    os.rmdir(data_dir)
                except OSError:
                    pass

    def test_get_task_id_from_branch(self):
        with patch.object(wa, "_read_task_id", return_value=""):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="feature/task-123/substep\n"
                )
                self.assertEqual(wa._get_task_id(), "task-123")


# ── Completion marker tests ─────────────────────────────────────────────────

class TestCompletionMarker(unittest.TestCase):

    def test_complete_marker(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".task-complete",
                                         delete=False) as f:
            f.write("All PRs merged")
            fname = f.name
        try:
            with patch.object(wa, "WORKDIR", os.path.dirname(fname)):
                # Patch to match the exact paths checked
                orig_isfile = os.path.isfile
                def fake_isfile(p):
                    if p == os.path.join(os.path.dirname(fname), ".task-complete"):
                        return True
                    if p == "/data/.task-complete":
                        return False
                    return orig_isfile(p)

                orig_open = open
                def fake_open(p, *a, **kw):
                    if p == os.path.join(os.path.dirname(fname), ".task-complete"):
                        return orig_open(fname, *a, **kw)
                    return orig_open(p, *a, **kw)

                with patch("os.path.isfile", side_effect=fake_isfile):
                    with patch("builtins.open", side_effect=fake_open):
                        with patch("os.remove"):
                            result, detail = wa._check_completion_marker()
                            self.assertEqual(result, "complete")
                            self.assertEqual(detail, "All PRs merged")
        finally:
            if os.path.exists(fname):
                os.unlink(fname)

    def test_no_marker(self):
        with patch("os.path.isfile", return_value=False):
            result, detail = wa._check_completion_marker()
            self.assertIsNone(result)
            self.assertEqual(detail, "")


# ── HTTP monitoring server tests ─────────────────────────────────────────────

class TestHTTPMonitoring(unittest.TestCase):
    """Start the HTTP server on a random port and test endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), wa.AgentHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def _get(self, path):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = json.loads(resp.read().decode())
        return resp.status, body

    @patch.object(wa, "_find_claude_pid", return_value=None)
    @patch.object(wa, "_get_task_id", return_value="test-task")
    def test_status_idle(self, *mocks):
        status, body = self._get("/status")
        self.assertEqual(status, 200)
        self.assertIsNone(body["pid"])
        self.assertEqual(body["state"], "idle")
        self.assertEqual(body["task_id"], "test-task")

    @patch.object(wa, "_find_claude_pid", return_value=999)
    @patch.object(wa, "_get_cpu_percent", return_value=25.0)
    @patch.object(wa, "_get_memory_mb", return_value=512.0)
    @patch.object(wa, "_get_running_seconds", return_value=300.0)
    @patch.object(wa, "_get_task_id", return_value="task-7")
    def test_status_busy(self, *mocks):
        status, body = self._get("/status")
        self.assertEqual(status, 200)
        self.assertEqual(body["pid"], 999)
        self.assertEqual(body["state"], "busy")
        self.assertEqual(body["cpu_percent"], 25.0)
        self.assertEqual(body["memory_mb"], 512.0)

    def test_output_missing_log(self):
        with patch.object(wa, "OUTPUT_LOG", "/tmp/nonexistent-test-log.log"):
            status, body = self._get("/output")
            self.assertEqual(status, 200)
            self.assertEqual(body["count"], 0)
            self.assertIn("error", body)

    def test_output_with_log(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            for i in range(5):
                f.write(f"line {i}\n")
            fname = f.name
        try:
            with patch.object(wa, "OUTPUT_LOG", fname):
                status, body = self._get("/output")
                self.assertEqual(status, 200)
                self.assertEqual(body["count"], 5)
        finally:
            os.unlink(fname)

    def test_activity(self):
        status, body = self._get("/activity")
        self.assertEqual(status, 200)
        self.assertIn("last_git_commit", body)
        self.assertIn("zombie_count", body)

    def test_health(self):
        status, body = self._get("/health")
        self.assertEqual(status, 200)
        self.assertIn("disk_free_gb", body)
        self.assertIn("container_uptime_hours", body)

    def test_404(self):
        status, body = self._get("/nonexistent")
        self.assertEqual(status, 404)
        self.assertIn("endpoints", body)


# ── Auth header tests ────────────────────────────────────────────────────────

class TestAuthHeaders(unittest.TestCase):

    def test_headers_with_token(self):
        with patch.object(wa, "API_TOKEN", "secret-token"):
            h = wa._headers()
            self.assertEqual(h["Authorization"], "Bearer secret-token")

    def test_headers_without_token(self):
        with patch.object(wa, "API_TOKEN", ""):
            h = wa._headers()
            self.assertNotIn("Authorization", h)


# ── Worker ID resolution tests ───────────────────────────────────────────────

class TestWorkerIdResolution(unittest.TestCase):

    def test_env_worker_id(self):
        self.assertEqual(wa.RESOLVED_WORKER_ID, "test-worker")


if __name__ == "__main__":
    unittest.main()
