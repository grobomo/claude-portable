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


if __name__ == "__main__":
    unittest.main()
