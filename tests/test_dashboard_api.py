"""Tests for dashboard API endpoints (v1: /api/*, v2: /dashboard/api/*)."""

import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import HTTPServer

loader = importlib.machinery.SourceFileLoader(
    "git_dispatch",
    os.path.join(os.path.dirname(__file__), "..", "scripts", "git-dispatch.py"),
)
spec = importlib.util.spec_from_loader("git_dispatch", loader)
gd = importlib.util.module_from_spec(spec)
loader.exec_module(gd)


def _json_get(server, path):
    """Make a GET request to the test server and return parsed JSON."""
    import urllib.request
    url = f"http://127.0.0.1:{server.server_address[1]}{path}"
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read().decode()), resp.status


class TestApiTasks(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_relay_dir = gd.RELAY_DIR
        gd.RELAY_DIR = self.tmpdir

    def tearDown(self):
        gd.RELAY_DIR = self._orig_relay_dir
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_request(self, state, request_id, data):
        dir_path = os.path.join(self.tmpdir, "requests", state)
        os.makedirs(dir_path, exist_ok=True)
        with open(os.path.join(dir_path, f"{request_id}.json"), "w") as f:
            json.dump(data, f)

    def test_empty_tasks(self):
        tasks = gd._api_get_tasks()
        self.assertEqual(tasks, [])

    def test_tasks_from_all_states(self):
        self._write_request("pending", "req-001", {
            "text": "Build feature X",
            "sender": "alice",
        })
        self._write_request("dispatched", "req-002", {
            "text": "Fix bug Y",
            "worker": "ccc-worker-1",
            "dispatched_at": "2026-03-29T10:00:00Z",
        })
        self._write_request("completed", "req-003", {
            "text": "Deploy service Z",
            "worker": "ccc-worker-2",
            "dispatched_at": "2026-03-29T09:00:00Z",
            "completed_at": "2026-03-29T09:15:00Z",
        })
        self._write_request("failed", "req-004", {
            "text": "Broken task",
            "worker": "ccc-worker-1",
            "error": "timeout",
        })

        tasks = gd._api_get_tasks()
        self.assertEqual(len(tasks), 4)

        by_id = {t["id"]: t for t in tasks}

        self.assertEqual(by_id["req-001"]["state"], "pending")
        self.assertIsNone(by_id["req-001"]["worker"])

        self.assertEqual(by_id["req-002"]["state"], "dispatched")
        self.assertEqual(by_id["req-002"]["worker"], "ccc-worker-1")

        self.assertEqual(by_id["req-003"]["state"], "completed")
        self.assertEqual(by_id["req-003"]["duration_seconds"], 900)

        self.assertEqual(by_id["req-004"]["state"], "failed")

    def test_text_truncated_to_100(self):
        long_text = "A" * 200
        self._write_request("pending", "req-long", {"text": long_text})
        tasks = gd._api_get_tasks()
        self.assertEqual(len(tasks[0]["text"]), 100)


class TestApiWorkers(unittest.TestCase):
    def setUp(self):
        self._orig_roster = gd._fleet_roster.copy()
        self._orig_stats = gd._worker_stats.copy()
        gd._fleet_roster.clear()
        gd._worker_stats.clear()

    def tearDown(self):
        gd._fleet_roster.clear()
        gd._fleet_roster.update(self._orig_roster)
        gd._worker_stats.clear()
        gd._worker_stats.update(self._orig_stats)

    def test_empty_workers(self):
        result = gd._api_get_workers()
        self.assertEqual(result, {})

    def test_workers_merged_with_stats(self):
        gd._fleet_roster["w1"] = {"status": "idle", "ip": "10.0.1.1"}
        gd._worker_stats["w1"] = {
            "current_task_id": "req-005",
            "tasks_completed": 3,
            "tasks_failed": 1,
            "registered_at": "2026-03-29T08:00:00Z",
            "last_dispatch_time": "2026-03-29T10:00:00Z",
            "durations": [120, 180],
        }

        result = gd._api_get_workers()
        self.assertIn("w1", result)
        w = result["w1"]
        self.assertEqual(w["current_task_id"], "req-005")
        self.assertEqual(w["tasks_completed"], 3)
        self.assertEqual(w["tasks_failed"], 1)
        self.assertEqual(w["ip"], "10.0.1.1")
        self.assertEqual(w["last_dispatch_time"], "2026-03-29T10:00:00Z")


class TestApiStats(unittest.TestCase):
    def setUp(self):
        self._orig_roster = gd._fleet_roster.copy()
        self._orig_stats = gd._worker_stats.copy()
        self._orig_state = dict(gd._state)
        self.tmpdir = tempfile.mkdtemp()
        self._orig_relay_dir = gd.RELAY_DIR
        gd.RELAY_DIR = self.tmpdir
        gd._fleet_roster.clear()
        gd._worker_stats.clear()

    def tearDown(self):
        gd.RELAY_DIR = self._orig_relay_dir
        gd._fleet_roster.clear()
        gd._fleet_roster.update(self._orig_roster)
        gd._worker_stats.clear()
        gd._worker_stats.update(self._orig_stats)
        gd._state.clear()
        gd._state.update(self._orig_state)
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_stats_with_workers(self):
        gd._fleet_roster["w1"] = {"status": "idle"}
        gd._fleet_roster["w2"] = {"status": "busy"}
        gd._fleet_roster["w3"] = {"status": "busy"}
        gd._state["uptime_start"] = time.time() - 3600

        stats = gd._api_get_stats()
        self.assertEqual(stats["total_workers"], 3)
        self.assertEqual(stats["idle_count"], 1)
        self.assertEqual(stats["busy_count"], 2)
        self.assertAlmostEqual(stats["uptime_seconds"], 3600, delta=5)

    def test_stats_empty(self):
        gd._state["uptime_start"] = time.time()
        stats = gd._api_get_stats()
        self.assertEqual(stats["total_workers"], 0)
        self.assertEqual(stats["tasks_completed_today"], 0)
        self.assertEqual(stats["success_rate_percent"], 0)
        self.assertEqual(stats["avg_duration_seconds"], 0)


class TestApiWorkerLive(unittest.TestCase):
    def setUp(self):
        self._orig_roster = gd._fleet_roster.copy()
        gd._fleet_roster.clear()

    def tearDown(self):
        gd._fleet_roster.clear()
        gd._fleet_roster.update(self._orig_roster)

    def test_worker_not_found(self):
        result = gd._api_get_worker_live("nonexistent")
        self.assertEqual(result["_status"], 404)

    def test_worker_no_ip(self):
        gd._fleet_roster["w1"] = {"status": "idle", "ip": ""}
        result = gd._api_get_worker_live("w1")
        self.assertEqual(result["_status"], 400)

    def test_worker_unreachable(self):
        gd._fleet_roster["w1"] = {"status": "idle", "ip": "192.0.2.1"}
        result = gd._api_get_worker_live("w1")
        self.assertEqual(result["worker_id"], "w1")
        # All endpoints should have error (unreachable IP)
        for endpoint in ("status", "output", "activity"):
            self.assertIn("error", result[endpoint])


class TestWorkerStatsTracking(unittest.TestCase):
    def setUp(self):
        self._orig_roster = gd._fleet_roster.copy()
        self._orig_stats = gd._worker_stats.copy()
        gd._fleet_roster.clear()
        gd._worker_stats.clear()
        gd._fleet_roster["w1"] = {
            "status": "idle", "ip": "10.0.1.1",
            "last_task": None, "last_report": None,
            "completions": 0, "last_area": None,
        }

    def tearDown(self):
        gd._fleet_roster.clear()
        gd._fleet_roster.update(self._orig_roster)
        gd._worker_stats.clear()
        gd._worker_stats.update(self._orig_stats)

    def test_pick_worker_updates_stats(self):
        name, ip = gd.pick_worker_for_area(None)
        self.assertEqual(name, "w1")
        self.assertIn("w1", gd._worker_stats)
        self.assertIsNotNone(gd._worker_stats["w1"]["last_dispatch_time"])


class TestHttpEndpoints(unittest.TestCase):
    """Integration test: actual HTTP requests to the HealthHandler."""

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), gd.HealthHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self._orig_roster = gd._fleet_roster.copy()
        self._orig_stats = gd._worker_stats.copy()
        self.tmpdir = tempfile.mkdtemp()
        self._orig_relay_dir = gd.RELAY_DIR
        gd.RELAY_DIR = self.tmpdir
        gd._fleet_roster.clear()
        gd._worker_stats.clear()

    def tearDown(self):
        gd.RELAY_DIR = self._orig_relay_dir
        gd._fleet_roster.clear()
        gd._fleet_roster.update(self._orig_roster)
        gd._worker_stats.clear()
        gd._worker_stats.update(self._orig_stats)
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_api_tasks_endpoint(self):
        data, status = _json_get(self.server, "/api/tasks")
        self.assertEqual(status, 200)
        self.assertIsInstance(data, list)

    def test_api_workers_endpoint(self):
        gd._fleet_roster["w1"] = {"status": "idle", "ip": "10.0.1.1"}
        data, status = _json_get(self.server, "/api/workers")
        self.assertEqual(status, 200)
        self.assertIn("w1", data)

    def test_api_stats_endpoint(self):
        data, status = _json_get(self.server, "/api/stats")
        self.assertEqual(status, 200)
        self.assertIn("total_workers", data)
        self.assertIn("uptime_seconds", data)

    def test_api_worker_live_404(self):
        import urllib.request
        import urllib.error
        url = f"http://127.0.0.1:{self.server.server_address[1]}/api/workers/nonexistent/live"
        try:
            urllib.request.urlopen(url, timeout=5)
            self.fail("Expected 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)


class TestDashboardV2Tasks(unittest.TestCase):
    """Tests for /dashboard/api/tasks spec-compliant endpoint."""

    def setUp(self):
        self._orig_roster = gd._fleet_roster.copy()
        self._orig_stats = gd._worker_stats.copy()
        self._orig_state = dict(gd._state)
        self.tmpdir = tempfile.mkdtemp()
        self._orig_repo_dir = gd.REPO_DIR
        gd.REPO_DIR = self.tmpdir
        gd._fleet_roster.clear()
        gd._worker_stats.clear()

    def tearDown(self):
        gd.REPO_DIR = self._orig_repo_dir
        gd._fleet_roster.clear()
        gd._fleet_roster.update(self._orig_roster)
        gd._worker_stats.clear()
        gd._worker_stats.update(self._orig_stats)
        gd._state.clear()
        gd._state.update(self._orig_state)
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_empty_fleet_returns_valid_schema(self):
        result = gd._dashboard_api_tasks()
        self.assertIn("features", result)
        self.assertIn("summary", result)
        self.assertIn("updated_at", result)
        self.assertIsInstance(result["features"], list)
        self.assertEqual(result["summary"]["total_tasks"], 0)

    def test_active_worker_creates_feature(self):
        gd._fleet_roster["w1"] = {
            "status": "busy",
            "task": {"branch": "continuous-claude/task-1-auth", "task_num": 1, "description": "Add auth"},
            "pipeline": {"stage": "BUILD", "stages_complete": 2, "phases": {"BUILD": {"start": "2026-03-29T10:00:00Z"}}},
            "last_heartbeat": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "healthy": True,
        }
        result = gd._dashboard_api_tasks()
        branches = [f["branch"] for f in result["features"]]
        self.assertIn("continuous-claude/task-1-auth", branches)

    def test_summary_counts(self):
        gd._fleet_roster["w1"] = {
            "status": "busy",
            "task": {"branch": "feat/x", "task_num": 1, "description": "Task A"},
            "pipeline": {"stage": "BUILD"},
            "last_heartbeat": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "healthy": True,
        }
        gd._fleet_roster["w2"] = {
            "status": "idle",
            "task": {},
            "pipeline": {"stage": "idle"},
            "last_heartbeat": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "healthy": True,
        }
        result = gd._dashboard_api_tasks()
        self.assertEqual(result["summary"]["idle_workers"], 1)
        self.assertEqual(result["summary"]["busy_workers"], 1)


class TestDashboardV2Infra(unittest.TestCase):
    """Tests for /dashboard/api/infra spec-compliant endpoint."""

    def setUp(self):
        self._orig_roster = gd._fleet_roster.copy()
        self._orig_stats = gd._worker_stats.copy()
        gd._fleet_roster.clear()
        gd._worker_stats.clear()

    def tearDown(self):
        gd._fleet_roster.clear()
        gd._fleet_roster.update(self._orig_roster)
        gd._worker_stats.clear()
        gd._worker_stats.update(self._orig_stats)

    def test_empty_fleet(self):
        result = gd._dashboard_api_infra()
        self.assertIn("workers", result)
        self.assertIn("updated_at", result)
        self.assertEqual(result["workers"], [])

    def test_worker_with_resource_metrics(self):
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        gd._fleet_roster["w1"] = {
            "status": "busy",
            "healthy": True,
            "last_heartbeat": now_str,
            "cpu_percent": 67.5,
            "memory_percent": 54.0,
            "memory_mb": {"used": 1100, "total": 2048},
            "disk_percent": 38.5,
            "disk_gb": {"used": 12.3, "total": 32.0},
            "uptime_seconds": 86400,
            "claude_running": True,
            "completions": 14,
            "task": {"description": "Auth refactor"},
            "pipeline": {"stage": "BUILD"},
            "error_count": 2,
            "recent_calls": [
                {"method": "POST", "path": "/heartbeat", "status": 200, "timestamp": now_str}
            ],
        }
        result = gd._dashboard_api_infra()
        self.assertEqual(len(result["workers"]), 1)
        w = result["workers"][0]
        self.assertEqual(w["worker_id"], "w1")
        self.assertTrue(w["healthy"])
        self.assertEqual(w["cpu_percent"], 67.5)
        self.assertEqual(w["memory_percent"], 54.0)
        self.assertEqual(w["memory_mb"]["used"], 1100)
        self.assertEqual(w["disk_percent"], 38.5)
        self.assertEqual(w["disk_gb"]["used"], 12.3)
        self.assertEqual(w["current_task"], "Auth refactor")
        self.assertEqual(w["phase"], "BUILD")
        self.assertTrue(w["claude_running"])
        self.assertGreater(w["tasks_per_hour"], 0)
        self.assertEqual(len(w["recent_calls"]), 1)

    def test_stale_worker_marked_unhealthy(self):
        # Heartbeat 2 minutes ago
        old_time = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(time.time() - 120),
        )
        gd._fleet_roster["w1"] = {
            "status": "idle",
            "healthy": True,
            "last_heartbeat": old_time,
            "uptime_seconds": 3600,
            "completions": 0,
            "task": {},
            "pipeline": {"stage": "idle"},
        }
        result = gd._dashboard_api_infra()
        w = result["workers"][0]
        self.assertFalse(w["healthy"])

    def test_worker_no_heartbeat_marked_unhealthy(self):
        gd._fleet_roster["w1"] = {
            "status": "idle",
            "healthy": True,
            "last_heartbeat": "",
            "uptime_seconds": 0,
            "completions": 0,
            "task": {},
            "pipeline": {"stage": "idle"},
        }
        result = gd._dashboard_api_infra()
        w = result["workers"][0]
        self.assertFalse(w["healthy"])


class TestDashboardV2Http(unittest.TestCase):
    """Integration: HTTP requests to DashboardHandler."""

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), gd.DashboardHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self._orig_roster = gd._fleet_roster.copy()
        self._orig_stats = gd._worker_stats.copy()
        gd._fleet_roster.clear()
        gd._worker_stats.clear()

    def tearDown(self):
        gd._fleet_roster.clear()
        gd._fleet_roster.update(self._orig_roster)
        gd._worker_stats.clear()
        gd._worker_stats.update(self._orig_stats)

    def test_dashboard_serves_html(self):
        import urllib.request
        url = f"http://127.0.0.1:{self.server.server_address[1]}/dashboard"
        with urllib.request.urlopen(url, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            content_type = resp.headers.get("Content-Type", "")
            self.assertIn("text/html", content_type)
            body = resp.read().decode()
            self.assertIn("CCC Fleet Dashboard", body)

    def test_dashboard_api_tasks_json(self):
        data, status = _json_get(self.server, "/dashboard/api/tasks")
        self.assertEqual(status, 200)
        self.assertIn("features", data)
        self.assertIn("summary", data)

    def test_dashboard_api_infra_json(self):
        data, status = _json_get(self.server, "/dashboard/api/infra")
        self.assertEqual(status, 200)
        self.assertIn("workers", data)
        self.assertIn("updated_at", data)

    def test_dashboard_api_infra_with_workers(self):
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        gd._fleet_roster["w1"] = {
            "status": "busy", "healthy": True, "last_heartbeat": now_str,
            "cpu_percent": 50, "memory_percent": 40,
            "memory_mb": {"used": 800, "total": 2048},
            "disk_percent": 30, "disk_gb": {"used": 10, "total": 32},
            "uptime_seconds": 3600, "claude_running": True,
            "completions": 5, "task": {"description": "Test task"},
            "pipeline": {"stage": "BUILD"}, "error_count": 0, "recent_calls": [],
        }
        data, status = _json_get(self.server, "/dashboard/api/infra")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["workers"]), 1)
        self.assertEqual(data["workers"][0]["cpu_percent"], 50)

    def test_dashboard_404_for_unknown(self):
        import urllib.request
        import urllib.error
        url = f"http://127.0.0.1:{self.server.server_address[1]}/nonexistent"
        try:
            urllib.request.urlopen(url, timeout=5)
            self.fail("Expected 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)


class TestHealthHandlerDashboardRoutes(unittest.TestCase):
    """Verify dashboard routes also work on the HealthHandler (port 8080)."""

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), gd.HealthHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self._orig_roster = gd._fleet_roster.copy()
        gd._fleet_roster.clear()

    def tearDown(self):
        gd._fleet_roster.clear()
        gd._fleet_roster.update(self._orig_roster)

    def test_dashboard_html_on_health_port(self):
        import urllib.request
        url = f"http://127.0.0.1:{self.server.server_address[1]}/dashboard"
        with urllib.request.urlopen(url, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/html", resp.headers.get("Content-Type", ""))

    def test_dashboard_api_tasks_on_health_port(self):
        data, status = _json_get(self.server, "/dashboard/api/tasks")
        self.assertEqual(status, 200)
        self.assertIn("features", data)

    def test_dashboard_api_infra_on_health_port(self):
        data, status = _json_get(self.server, "/dashboard/api/infra")
        self.assertEqual(status, 200)
        self.assertIn("workers", data)


if __name__ == "__main__":
    unittest.main()
