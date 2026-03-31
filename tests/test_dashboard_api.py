"""Tests for the dashboard API endpoints (/api/tasks, /api/workers, /api/stats, /api/workers/{id}/live)."""

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


class TestDashboardHtml(unittest.TestCase):
    """Test that GET / serves the dashboard HTML."""

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), gd.HealthHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_root_returns_html(self):
        import urllib.request
        url = f"http://127.0.0.1:{self.server.server_address[1]}/"
        with urllib.request.urlopen(url, timeout=5) as resp:
            ct = resp.headers.get("Content-Type", "")
            body = resp.read().decode()
        self.assertIn("text/html", ct)
        self.assertIn("<title>CCC Fleet Dashboard</title>", body)

    def test_health_returns_json(self):
        data, status = _json_get(self.server, "/health")
        self.assertEqual(status, 200)
        self.assertIn("uptime_seconds", data)


class TestApiSubmit(unittest.TestCase):
    """Test POST /api/submit endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), gd.HealthHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self._orig_store = dict(gd._task_store)
        gd._task_store.clear()

    def tearDown(self):
        gd._task_store.clear()
        gd._task_store.update(self._orig_store)

    def _post(self, path, payload):
        import urllib.request
        import urllib.error
        url = f"http://127.0.0.1:{self.server.server_address[1]}{path}"
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode()), resp.status
        except urllib.error.HTTPError as e:
            return json.loads(e.read().decode()), e.code

    def test_submit_creates_task(self):
        data, status = self._post("/api/submit", {"text": "Build feature X"})
        self.assertEqual(status, 201)
        self.assertEqual(data["state"], "PENDING")
        self.assertEqual(data["text"], "Build feature X")
        self.assertEqual(data["sender"], "dashboard")
        self.assertIn("id", data)

    def test_submit_empty_text_returns_400(self):
        data, status = self._post("/api/submit", {"text": ""})
        self.assertEqual(status, 400)
        self.assertIn("error", data)

    def test_submit_missing_text_returns_400(self):
        data, status = self._post("/api/submit", {"priority": "high"})
        self.assertEqual(status, 400)
        self.assertIn("error", data)

    def test_submit_invalid_priority_defaults_normal(self):
        data, status = self._post("/api/submit", {"text": "Task Y", "priority": "bogus"})
        self.assertEqual(status, 201)
        self.assertEqual(data["priority"], "normal")

    def test_submit_custom_priority(self):
        data, status = self._post("/api/submit", {"text": "Urgent", "priority": "critical"})
        self.assertEqual(status, 201)
        self.assertEqual(data["priority"], "critical")

    def test_submit_cors_headers(self):
        import urllib.request
        url = f"http://127.0.0.1:{self.server.server_address[1]}/api/submit"
        data = json.dumps({"text": "CORS test"}).encode()
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            acao = resp.headers.get("Access-Control-Allow-Origin", "")
        self.assertEqual(acao, "*")


class TestDashboardApiTasks(unittest.TestCase):
    """Test /dashboard/api/tasks endpoint."""

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

    def test_empty_fleet_returns_valid_structure(self):
        data = gd._dashboard_api_tasks()
        self.assertIn("features", data)
        self.assertIn("summary", data)
        self.assertIn("updated_at", data)
        self.assertIsInstance(data["features"], list)

    def test_busy_worker_creates_feature(self):
        gd._fleet_roster["w1"] = {
            "status": "busy",
            "task": {"branch": "continuous-claude/task-1-add-logging", "task_num": 1, "description": "Add logging"},
            "pipeline": {"stage": "BUILD", "phases": {"BUILD": {"start": "2026-03-29T10:00:00Z"}}, "stages_complete": 2},
            "last_heartbeat": "2026-03-29T10:05:00Z",
        }
        data = gd._dashboard_api_tasks()
        features = data["features"]
        branches = [f["branch"] for f in features]
        self.assertIn("continuous-claude/task-1-add-logging", branches)

    def test_summary_counts(self):
        gd._fleet_roster["w1"] = {"status": "idle", "task": {}, "pipeline": {}}
        gd._fleet_roster["w2"] = {"status": "busy", "task": {}, "pipeline": {"stage": "BUILD"}}
        data = gd._dashboard_api_tasks()
        s = data["summary"]
        self.assertEqual(s["idle_workers"], 1)
        self.assertEqual(s["busy_workers"], 1)


class TestDashboardApiInfra(unittest.TestCase):
    """Test /dashboard/api/infra endpoint."""

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
        data = gd._dashboard_api_infra()
        self.assertIn("workers", data)
        self.assertEqual(len(data["workers"]), 0)
        self.assertIn("updated_at", data)

    def test_healthy_worker(self):
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        gd._fleet_roster["w1"] = {
            "status": "idle",
            "last_heartbeat": now,
            "last_report": now,
            "cpu_percent": 25.3,
            "memory_percent": 45.0,
            "memory_mb": {"used": 920, "total": 2048},
            "disk_percent": 30.0,
            "disk_gb": {"used": 10.0, "total": 32.0},
            "claude_running": True,
            "uptime_seconds": 7200,
            "pipeline": {"stage": "idle"},
            "task": {"description": ""},
            "error_count": 0,
            "completions": 5,
        }
        gd._worker_stats["w1"] = {"tasks_completed": 5}

        data = gd._dashboard_api_infra()
        self.assertEqual(len(data["workers"]), 1)
        w = data["workers"][0]
        self.assertTrue(w["healthy"])
        self.assertEqual(w["cpu_percent"], 25.3)
        self.assertEqual(w["memory_percent"], 45.0)
        self.assertEqual(w["memory_mb"]["used"], 920)
        self.assertEqual(w["disk_percent"], 30.0)
        self.assertEqual(w["tasks_completed"], 5)
        self.assertGreater(w["tasks_per_hour"], 0)

    def test_stale_worker_unhealthy(self):
        old_time = "2026-03-29T00:00:00Z"
        gd._fleet_roster["w1"] = {
            "status": "idle",
            "last_heartbeat": old_time,
            "pipeline": {},
            "task": {},
            "uptime_seconds": 100,
        }
        data = gd._dashboard_api_infra()
        w = data["workers"][0]
        self.assertFalse(w["healthy"])

    def test_no_heartbeat_unhealthy(self):
        gd._fleet_roster["w1"] = {
            "status": "idle",
            "pipeline": {},
            "task": {},
            "uptime_seconds": 100,
        }
        data = gd._dashboard_api_infra()
        w = data["workers"][0]
        self.assertFalse(w["healthy"])


class TestDashboardHttpEndpoints(unittest.TestCase):
    """Integration test: actual HTTP to /dashboard/* endpoints."""

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
            ct = resp.headers.get("Content-Type", "")
            body = resp.read().decode()
        self.assertIn("text/html", ct)
        self.assertIn("CCC Fleet Dashboard", body)
        self.assertIn("tab-tasks", body)
        self.assertIn("tab-infra", body)

    def test_dashboard_api_tasks_returns_json(self):
        data, status = _json_get(self.server, "/dashboard/api/tasks")
        self.assertEqual(status, 200)
        self.assertIn("features", data)
        self.assertIn("summary", data)

    def test_dashboard_api_infra_returns_json(self):
        data, status = _json_get(self.server, "/dashboard/api/infra")
        self.assertEqual(status, 200)
        self.assertIn("workers", data)
        self.assertIn("updated_at", data)

    def test_dashboard_api_infra_with_worker(self):
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        gd._fleet_roster["w1"] = {
            "status": "busy",
            "last_heartbeat": now,
            "cpu_percent": 50.0,
            "memory_percent": 60.0,
            "disk_percent": 40.0,
            "claude_running": True,
            "uptime_seconds": 3600,
            "pipeline": {"stage": "BUILD"},
            "task": {"description": "Test task"},
        }
        gd._worker_stats["w1"] = {"tasks_completed": 2}

        data, status = _json_get(self.server, "/dashboard/api/infra")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["workers"]), 1)
        w = data["workers"][0]
        self.assertEqual(w["worker_id"], "w1")
        self.assertEqual(w["cpu_percent"], 50.0)
        self.assertTrue(w["healthy"])

    def test_dashboard_api_cors(self):
        import urllib.request
        url = f"http://127.0.0.1:{self.server.server_address[1]}/dashboard/api/infra"
        with urllib.request.urlopen(url, timeout=5) as resp:
            acao = resp.headers.get("Access-Control-Allow-Origin", "")
        self.assertEqual(acao, "*")

    def test_dashboard_trailing_slash(self):
        import urllib.request
        url = f"http://127.0.0.1:{self.server.server_address[1]}/dashboard/"
        with urllib.request.urlopen(url, timeout=5) as resp:
            ct = resp.headers.get("Content-Type", "")
        self.assertIn("text/html", ct)


class TestHeartbeatResourceFields(unittest.TestCase):
    """Test that heartbeat handler stores new resource fields."""

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

    def _post_heartbeat(self, payload):
        import urllib.request
        url = f"http://127.0.0.1:{self.server.server_address[1]}/worker/heartbeat"
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode()), resp.status

    def test_heartbeat_stores_resource_metrics(self):
        payload = {
            "worker_id": "w-test",
            "task": {},
            "pipeline": {"stage": "idle"},
            "idle_seconds": 0,
            "claude_running": True,
            "maintenance": False,
            "uptime_seconds": 1000,
            "timestamp": "2026-03-29T10:00:00Z",
            "cpu_percent": 42.5,
            "memory_percent": 68.0,
            "memory_mb": {"used": 1400, "total": 2048},
            "disk_percent": 25.0,
            "disk_gb": {"used": 8.0, "total": 32.0},
            "error_count": 3,
        }
        data, status = self._post_heartbeat(payload)
        self.assertEqual(status, 200)

        # Verify stored in roster
        with gd._fleet_roster_lock:
            entry = gd._fleet_roster.get("w-test")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["cpu_percent"], 42.5)
        self.assertEqual(entry["memory_percent"], 68.0)
        self.assertEqual(entry["memory_mb"]["used"], 1400)
        self.assertEqual(entry["disk_percent"], 25.0)
        self.assertEqual(entry["disk_gb"]["total"], 32.0)
        self.assertEqual(entry["error_count"], 3)


if __name__ == "__main__":
    unittest.main()
