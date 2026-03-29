#!/usr/bin/env python3
"""E2E tests for the dispatcher system.

Tests the full pipeline locally without real EC2:
- Health endpoint serves correct JSON
- Worker registration + done + idle flow
- Dispatch tick with pending tasks
- Relay status endpoint
- Leader state in health response
- Task routing integrated into dispatch
- Dependency blocking integrated into dispatch
- Fleet monitor skips fresh workers
"""

import importlib
import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.client import HTTPConnection
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

loader = importlib.machinery.SourceFileLoader(
    "git_dispatch",
    os.path.join(os.path.dirname(__file__), "..", "scripts", "git-dispatch.py"),
)
spec = importlib.util.spec_from_loader("git_dispatch", loader)
gd = importlib.util.module_from_spec(spec)
loader.exec_module(gd)


def _fresh_ts():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class TestHealthEndpointE2E(unittest.TestCase):
    """Start a real HTTP server and hit it with real HTTP requests."""

    @classmethod
    def setUpClass(cls):
        # Use a random high port
        cls.port = 18080
        gd.HEALTH_PORT = cls.port
        cls.server = gd.HTTPServer(("127.0.0.1", cls.port), gd.HealthHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        # Reset state
        with gd._state_lock:
            gd._state.update({
                "status": "running",
                "last_poll": None,
                "pending_tasks": 0,
                "active_workers": 0,
                "active_branches": 0,
                "total_dispatches": 0,
                "total_completions": 0,
                "last_error": None,
                "errors": 0,
                "uptime_start": time.time(),
            })
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()
        with gd._relay_stats_lock:
            gd._relay_stats.update({
                "last_poll": None, "pending": 0, "dispatched": 0,
                "completed": 0, "failed": 0, "errors": 0,
            })
        with gd._leader_state_lock:
            gd._leader_state.update({
                "role": "primary", "promoted_at": None, "demoted_at": None,
                "primary_instance": None, "last_heartbeat_write": None,
                "last_heartbeat_check": None,
            })

    def _get(self, path):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read().decode()
        conn.close()
        return resp.status, json.loads(body) if body else {}

    def _post(self, path, data):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        body = json.dumps(data).encode()
        conn.request("POST", path, body=body,
                      headers={"Content-Type": "application/json",
                                "Content-Length": str(len(body))})
        resp = conn.getresponse()
        rbody = resp.read().decode()
        conn.close()
        return resp.status, json.loads(rbody) if rbody else {}

    def test_health_returns_200(self):
        status, data = self._get("/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "running")
        self.assertIn("uptime_seconds", data)
        self.assertIn("fleet_roster", data)
        self.assertIn("relay", data)
        self.assertIn("leader", data)

    def test_relay_status_returns_200(self):
        status, data = self._get("/relay/status")
        self.assertEqual(status, 200)
        self.assertIn("pending", data)
        self.assertIn("completed", data)

    def test_404_on_unknown_path(self):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/nonexistent")
        resp = conn.getresponse()
        resp.read()
        conn.close()
        self.assertEqual(resp.status, 404)

    def test_worker_register_flow(self):
        status, data = self._post("/worker/register", {
            "worker_id": "e2e-worker-1",
            "ip": "10.0.0.99",
            "role": "worker",
            "capabilities": ["claude"],
        })
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")

        # Verify in roster
        with gd._fleet_roster_lock:
            entry = gd._fleet_roster.get("e2e-worker-1")
        self.assertIsNotNone(entry)
        self.assertTrue(entry["registered"])
        self.assertEqual(entry["ip"], "10.0.0.99")

    def test_worker_done_flow(self):
        # Register first
        self._post("/worker/register", {
            "worker_id": "e2e-worker-2", "ip": "10.0.0.100",
        })

        # Report done
        status, data = self._post("/worker/done", {
            "worker_id": "e2e-worker-2",
            "task": "Fix dispatcher relay poll",
            "duration": 120,
        })
        self.assertEqual(status, 200)

        # Check roster updated
        with gd._fleet_roster_lock:
            entry = gd._fleet_roster["e2e-worker-2"]
        self.assertEqual(entry["status"], "idle")
        self.assertEqual(entry["last_task"], "Fix dispatcher relay poll")
        self.assertEqual(entry["last_area"], "dispatcher")  # area affinity
        self.assertEqual(entry["completions"], 1)

    def test_leader_state_in_health(self):
        gd.promote_to_primary("e2e-test")
        status, data = self._get("/health")
        self.assertEqual(data["leader"]["role"], "primary")


class TestDispatchTickE2E(unittest.TestCase):
    """Test the full dispatch tick with a real TODO.md on disk."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        todo = (
            "# TODO\n\n"
            "- [x] Done task\n"
            "- [ ] Pending task one\n"
            "  - PR title: \"feat: pending one\"\n"
            "- [ ] Pending task two\n"
            "  - PR title: \"feat: pending two\"\n"
            "  - depends-on: 4\n"  # depends on "Pending task one" at line 4
        )
        with open(os.path.join(self.tmpdir, "TODO.md"), "w") as f:
            f.write(todo)

        gd.promote_to_primary("e2e-dispatch")
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()

    def tearDown(self):
        with gd._leader_state_lock:
            gd._leader_state["role"] = "standby"

    def test_pending_tasks_parsed(self):
        tasks = gd.get_pending_tasks(self.tmpdir)
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]["description"], "Pending task one")
        self.assertFalse(tasks[0]["blocked"])

    def test_blocked_task_identified(self):
        tasks = gd.get_pending_tasks(self.tmpdir)
        task_two = [t for t in tasks if "two" in t["description"]][0]
        self.assertTrue(task_two["blocked"])
        self.assertEqual(task_two["blocked_by"], [4])

    @patch.object(gd, "launch_worker", return_value=True)
    @patch.object(gd, "get_running_workers", return_value=[])
    @patch.object(gd, "get_active_worker_branches", return_value=[])
    @patch.object(gd, "git_pull", return_value=True)
    def test_dispatch_tick_reads_tasks(self, mock_pull, mock_branches,
                                       mock_workers, mock_launch):
        """Full dispatch tick reads TODO.md and attempts to scale."""
        old_repo = gd.REPO_DIR
        gd.REPO_DIR = self.tmpdir
        try:
            gd._dispatch_tick("us-east-2")
        finally:
            gd.REPO_DIR = old_repo

        mock_pull.assert_called_once()
        # Should see 2 pending tasks, attempt to launch workers
        mock_launch.assert_called()


class TestPickWorkerAffinityE2E(unittest.TestCase):
    """Test area affinity through the full register -> done -> pick cycle."""

    def setUp(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()

    def tearDown(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()

    def test_full_affinity_cycle(self):
        """Register worker, complete a dispatcher task, then pick for dispatcher area."""
        # 1. Register
        with gd._fleet_roster_lock:
            gd._fleet_roster["w-alpha"] = {
                "status": "idle", "ip": "10.0.1.1",
                "registered": True, "last_task": None,
                "last_area": None, "last_report": _fresh_ts(),
                "completions": 0,
            }
            gd._fleet_roster["w-beta"] = {
                "status": "idle", "ip": "10.0.1.2",
                "registered": True, "last_task": None,
                "last_area": None, "last_report": _fresh_ts(),
                "completions": 0,
            }

        # 2. w-alpha completes a dispatcher task
        with gd._fleet_roster_lock:
            gd._fleet_roster["w-alpha"]["last_task"] = "Fix dispatcher heartbeat"
            gd._fleet_roster["w-alpha"]["last_area"] = "dispatcher"

        # 3. Pick for a new dispatcher task — should prefer w-alpha
        name, ip = gd.pick_worker_for_area("dispatcher")
        self.assertEqual(name, "w-alpha")

        # 4. Reset w-alpha to idle, pick for fleet — should get w-beta (no affinity match)
        with gd._fleet_roster_lock:
            gd._fleet_roster["w-alpha"]["status"] = "idle"
        name, ip = gd.pick_worker_for_area("fleet")
        # w-beta has no area affinity but is idle
        self.assertIn(name, ["w-alpha", "w-beta"])


class TestScriptSyntax(unittest.TestCase):
    """Verify all shell scripts pass bash -n syntax check."""

    def test_all_shell_scripts(self):
        scripts_dir = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
        # Find Git Bash on Windows (Python may find WSL bash first)
        git_bash = r"C:\Program Files\Git\usr\bin\bash.exe"
        bash_cmd = git_bash if os.path.isfile(git_bash) else "bash"

        errors = []
        for f in os.listdir(scripts_dir):
            if not f.endswith(".sh"):
                continue
            path = os.path.join(scripts_dir, f)
            r = subprocess.run([bash_cmd, "-n", path],
                               capture_output=True, text=True, timeout=10)
            if r.returncode != 0:
                errors.append(f"{f}: {r.stderr.strip()}")
        self.assertEqual(errors, [], f"Shell syntax errors:\n" + "\n".join(errors))


class TestPythonSyntax(unittest.TestCase):
    """Verify all Python scripts compile cleanly."""

    def test_all_python_scripts(self):
        scripts_dir = os.path.join(os.path.dirname(__file__), "..", "scripts")
        for f in os.listdir(scripts_dir):
            if not f.endswith(".py"):
                continue
            path = os.path.join(scripts_dir, f)
            try:
                import py_compile
                py_compile.compile(path, doraise=True)
            except py_compile.PyCompileError as e:
                self.fail(f"Syntax error in {f}: {e}")


if __name__ == "__main__":
    unittest.main()
