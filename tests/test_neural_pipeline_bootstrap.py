#!/usr/bin/env python3
"""Tests for Neural Pipeline bootstrap -- verifies react/ sub-project structure."""

import os
import unittest

PROJECT_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..")
)
REACT_DIR = os.path.join(PROJECT_ROOT, "react")


class TestReactDirectoryExists(unittest.TestCase):
    """Verify the react/ sub-project directory exists."""

    def test_react_dir_exists(self):
        self.assertTrue(
            os.path.isdir(REACT_DIR),
            "react/ directory must exist at project root",
        )

    def test_claude_md_exists(self):
        path = os.path.join(REACT_DIR, "CLAUDE.md")
        self.assertTrue(os.path.isfile(path), "react/CLAUDE.md must exist")

    def test_todo_md_exists(self):
        path = os.path.join(REACT_DIR, "TODO.md")
        self.assertTrue(os.path.isfile(path), "react/TODO.md must exist")


class TestReactTodoMd(unittest.TestCase):
    """Verify react/TODO.md has properly structured tasks."""

    @classmethod
    def setUpClass(cls):
        todo_path = os.path.join(REACT_DIR, "TODO.md")
        if os.path.isfile(todo_path):
            with open(todo_path, "r", encoding="utf-8") as f:
                cls.content = f.read()
            cls.lines = cls.content.splitlines()
        else:
            cls.content = ""
            cls.lines = []

    def test_has_unchecked_tasks(self):
        unchecked = [l for l in self.lines if l.strip().startswith("- [ ]")]
        self.assertGreaterEqual(
            len(unchecked), 3,
            "react/TODO.md must have at least 3 unchecked tasks "
            "(status bar fix, phase enforcement, API endpoint)",
        )

    def test_has_status_bar_task(self):
        self.assertIn(
            "stale", self.content.lower(),
            "TODO must include task about stale worker detection in status bar",
        )

    def test_has_phase_enforcement_task(self):
        found = "enforce" in self.content.lower() or "ordering" in self.content.lower()
        self.assertTrue(
            found,
            "TODO must include task about enforcing phase ordering",
        )

    def test_has_api_endpoint_task(self):
        found = "/pipeline" in self.content.lower() or "status quer" in self.content.lower()
        self.assertTrue(
            found,
            "TODO must include task about API endpoint for status queries",
        )

    def test_tasks_have_pr_titles(self):
        unchecked = [l for l in self.lines if l.strip().startswith("- [ ]")]
        # Find PR title lines (indented under tasks)
        pr_titles = [l for l in self.lines if "PR title:" in l]
        self.assertGreaterEqual(
            len(pr_titles), len(unchecked),
            f"Each of {len(unchecked)} tasks must have a PR title "
            f"(found {len(pr_titles)})",
        )

    def test_tasks_have_template_fields(self):
        """Each task should have What/Why/How/Acceptance fields."""
        required_fields = ["What:", "Why:", "How:", "Acceptance:"]
        unchecked = [l for l in self.lines if l.strip().startswith("- [ ]")]
        for field in required_fields:
            count = sum(1 for l in self.lines if field in l)
            self.assertGreaterEqual(
                count, len(unchecked),
                f"Each task must have '{field}' field "
                f"(found {count} for {len(unchecked)} tasks)",
            )


class TestReactClaudeMd(unittest.TestCase):
    """Verify react/CLAUDE.md has essential project context."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(REACT_DIR, "CLAUDE.md")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                cls.content = f.read()
        else:
            cls.content = ""

    def test_describes_pipeline(self):
        self.assertIn(
            "pipeline", self.content.lower(),
            "CLAUDE.md must describe the pipeline system",
        )

    def test_lists_key_files(self):
        self.assertIn(
            "worker-pipeline.py", self.content,
            "CLAUDE.md must reference worker-pipeline.py",
        )
        self.assertIn(
            "worker-health.py", self.content,
            "CLAUDE.md must reference worker-health.py",
        )
        self.assertIn(
            "continuous-claude.sh", self.content,
            "CLAUDE.md must reference continuous-claude.sh",
        )

    def test_describes_architecture(self):
        self.assertIn(
            "dispatcher", self.content.lower(),
            "CLAUDE.md must describe dispatcher integration",
        )
        self.assertIn(
            "heartbeat", self.content.lower(),
            "CLAUDE.md must describe heartbeat mechanism",
        )

    def test_has_development_rules(self):
        self.assertIn(
            "pytest", self.content.lower(),
            "CLAUDE.md must mention test runner (pytest)",
        )

    def test_no_personal_paths(self):
        self.assertNotIn(
            "C:\\Users\\", self.content,
            "CLAUDE.md must not contain personal Windows paths",
        )
        self.assertNotIn(
            "C:/Users/", self.content,
            "CLAUDE.md must not contain personal Windows paths",
        )


if __name__ == "__main__":
    unittest.main()
