#!/usr/bin/env python3
"""Tests for task routing by app area in git-dispatch.py."""

import importlib
import importlib.machinery
import importlib.util
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

loader = importlib.machinery.SourceFileLoader(
    "git_dispatch",
    os.path.join(os.path.dirname(__file__), "..", "scripts", "git-dispatch.py"),
)
spec = importlib.util.spec_from_loader("git_dispatch", loader)
gd = importlib.util.module_from_spec(spec)
loader.exec_module(gd)


class TestRouteTaskToArea(unittest.TestCase):
    def test_dispatcher_keywords(self):
        self.assertEqual(gd.route_task_to_area("Fix dispatcher heartbeat timeout"), "dispatcher")

    def test_fleet_keywords(self):
        self.assertEqual(gd.route_task_to_area("Fleet monitor daemon for idle workers"), "fleet")

    def test_teams_keywords(self):
        self.assertEqual(gd.route_task_to_area("Move Teams polling to chatbot"), "teams-integration")

    def test_tdd_keywords(self):
        self.assertEqual(gd.route_task_to_area("Add REVIEW stage to TDD pipeline"), "tdd-pipeline")

    def test_infrastructure_keywords(self):
        self.assertEqual(gd.route_task_to_area("Fix Dockerfile bootstrap sequence"), "infrastructure")

    def test_no_match_returns_none(self):
        self.assertIsNone(gd.route_task_to_area("Something completely unrelated to anything"))

    def test_multiple_keywords_highest_score_wins(self):
        # "dispatcher relay poll" has 3 dispatcher keywords vs 0 for others
        result = gd.route_task_to_area("Fix dispatcher relay poll loop")
        self.assertEqual(result, "dispatcher")

    def test_case_insensitive(self):
        self.assertEqual(gd.route_task_to_area("Fix DISPATCHER Heartbeat"), "dispatcher")

    def test_worker_routes_to_fleet(self):
        self.assertEqual(gd.route_task_to_area("Worker self-reports idle status"), "fleet")

    def test_test_routes_to_tdd(self):
        self.assertEqual(gd.route_task_to_area("Add test gate verification to pipeline stage"), "tdd-pipeline")

    def test_container_routes_to_infrastructure(self):
        self.assertEqual(gd.route_task_to_area("Fix container bootstrap crash"), "infrastructure")


class TestGetAreaContext(unittest.TestCase):
    def test_existing_area(self):
        repo_dir = os.path.join(os.path.dirname(__file__), "..")
        content = gd.get_area_context(repo_dir, "dispatcher")
        self.assertIn("Dispatcher", content)

    def test_missing_area(self):
        repo_dir = os.path.join(os.path.dirname(__file__), "..")
        content = gd.get_area_context(repo_dir, "nonexistent-area")
        self.assertEqual(content, "")


class TestPendingTasksIncludeArea(unittest.TestCase):
    def test_tasks_have_area_field(self):
        repo_dir = os.path.join(os.path.dirname(__file__), "..")
        tasks = gd.get_pending_tasks(repo_dir)
        # All tasks should have an 'area' key (may be None)
        for task in tasks:
            self.assertIn("area", task)


class TestPickWorkerForArea(unittest.TestCase):
    def setUp(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()

    def tearDown(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()

    def test_affinity_match_preferred(self):
        """Worker with matching last_area is picked over any idle worker."""
        with gd._fleet_roster_lock:
            gd._fleet_roster["w-generic"] = {
                "status": "idle", "ip": "10.0.1.1", "last_area": None,
            }
            gd._fleet_roster["w-dispatcher"] = {
                "status": "idle", "ip": "10.0.1.2", "last_area": "dispatcher",
            }
        name, ip = gd.pick_worker_for_area("dispatcher")
        self.assertEqual(name, "w-dispatcher")
        self.assertEqual(ip, "10.0.1.2")

    def test_fallback_to_any_idle(self):
        """If no affinity match, pick any idle worker."""
        with gd._fleet_roster_lock:
            gd._fleet_roster["w-fleet"] = {
                "status": "idle", "ip": "10.0.1.3", "last_area": "fleet",
            }
        name, ip = gd.pick_worker_for_area("dispatcher")
        self.assertEqual(name, "w-fleet")

    def test_no_idle_workers(self):
        """No idle workers returns empty strings."""
        with gd._fleet_roster_lock:
            gd._fleet_roster["w-busy"] = {
                "status": "busy", "ip": "10.0.1.4", "last_area": "dispatcher",
            }
        name, ip = gd.pick_worker_for_area("dispatcher")
        self.assertEqual(name, "")
        self.assertEqual(ip, "")

    def test_none_area_picks_any(self):
        """None area just picks any idle worker."""
        with gd._fleet_roster_lock:
            gd._fleet_roster["w1"] = {
                "status": "idle", "ip": "10.0.1.5", "last_area": "fleet",
            }
        name, ip = gd.pick_worker_for_area(None)
        self.assertEqual(name, "w1")

    def test_picked_worker_marked_busy(self):
        """Picked worker is set to busy in the roster."""
        with gd._fleet_roster_lock:
            gd._fleet_roster["w1"] = {
                "status": "idle", "ip": "10.0.1.6", "last_area": None,
            }
        gd.pick_worker_for_area(None)
        with gd._fleet_roster_lock:
            self.assertEqual(gd._fleet_roster["w1"]["status"], "busy")

    def test_skip_worker_without_ip(self):
        """Workers with no IP are skipped."""
        with gd._fleet_roster_lock:
            gd._fleet_roster["w-noip"] = {
                "status": "idle", "ip": "", "last_area": "dispatcher",
            }
        name, ip = gd.pick_worker_for_area("dispatcher")
        self.assertEqual(name, "")


if __name__ == "__main__":
    unittest.main()
