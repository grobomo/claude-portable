#!/usr/bin/env python3
"""Tests for task dependency tracking in git-dispatch.py.

Validates:
- depends-on: syntax parsed from indented sub-lines
- Blocked tasks have blocked=True and blocked_by populated
- Unblocked tasks (deps satisfied) have blocked=False
- Tasks with no dependencies are never blocked
- Multiple dependency formats: "task-5", "line-5", "5"
- Comma-separated dependencies
"""

import importlib
import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

loader = importlib.machinery.SourceFileLoader(
    "git_dispatch",
    os.path.join(os.path.dirname(__file__), "..", "scripts", "git-dispatch.py"),
)
spec = importlib.util.spec_from_loader("git_dispatch", loader)
gd = importlib.util.module_from_spec(spec)
loader.exec_module(gd)


SAMPLE_TODO = """\
# Test TODO

## Phase 1

- [x] First task done
  - PR title: "feat: first thing"

- [ ] Second task (no deps)
  - PR title: "feat: second thing"

- [ ] Third task depends on second
  - PR title: "feat: third thing"
  - depends-on: 8

- [ ] Fourth task depends on first (done) and second (not done)
  - PR title: "feat: fourth thing"
  - depends-on: 5, 8

- [ ] Fifth task depends on first (done)
  - PR title: "feat: fifth thing"
  - depends-on: task-5
"""


class TestParseAllTasks(unittest.TestCase):
    def test_counts_all_tasks(self):
        tasks, completed = gd._parse_all_tasks(SAMPLE_TODO)
        self.assertEqual(len(tasks), 5)

    def test_completed_lines(self):
        tasks, completed = gd._parse_all_tasks(SAMPLE_TODO)
        # First task "First task done" is checked
        checked_tasks = [t for t in tasks if t["checked"]]
        self.assertEqual(len(checked_tasks), 1)
        self.assertIn("First task done", checked_tasks[0]["description"])
        self.assertIn(checked_tasks[0]["line"], completed)

    def test_depends_on_parsed(self):
        tasks, _ = gd._parse_all_tasks(SAMPLE_TODO)
        # Third task depends on line 8
        third = [t for t in tasks if "Third" in t["description"]][0]
        self.assertEqual(third["depends_on"], [8])

    def test_multiple_deps_parsed(self):
        tasks, _ = gd._parse_all_tasks(SAMPLE_TODO)
        fourth = [t for t in tasks if "Fourth" in t["description"]][0]
        self.assertEqual(sorted(fourth["depends_on"]), [5, 8])

    def test_task_ref_format(self):
        tasks, _ = gd._parse_all_tasks(SAMPLE_TODO)
        fifth = [t for t in tasks if "Fifth" in t["description"]][0]
        self.assertEqual(fifth["depends_on"], [5])

    def test_no_deps(self):
        tasks, _ = gd._parse_all_tasks(SAMPLE_TODO)
        second = [t for t in tasks if "Second" in t["description"]][0]
        self.assertEqual(second["depends_on"], [])


class TestGetPendingTasksWithDeps(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        todo_path = os.path.join(self.tmpdir, "TODO.md")
        with open(todo_path, "w") as f:
            f.write(SAMPLE_TODO)

    def test_no_deps_not_blocked(self):
        tasks = gd.get_pending_tasks(self.tmpdir)
        second = [t for t in tasks if "Second" in t["description"]][0]
        self.assertFalse(second["blocked"])
        self.assertEqual(second["blocked_by"], [])

    def test_unmet_dep_is_blocked(self):
        tasks = gd.get_pending_tasks(self.tmpdir)
        third = [t for t in tasks if "Third" in t["description"]][0]
        # Line 8 is "Second task" which is unchecked
        self.assertTrue(third["blocked"])
        self.assertEqual(third["blocked_by"], [8])

    def test_met_dep_not_blocked(self):
        tasks = gd.get_pending_tasks(self.tmpdir)
        fifth = [t for t in tasks if "Fifth" in t["description"]][0]
        # Depends on line 5 which is "First task done" (checked)
        self.assertFalse(fifth["blocked"])

    def test_partial_deps_blocked(self):
        tasks = gd.get_pending_tasks(self.tmpdir)
        fourth = [t for t in tasks if "Fourth" in t["description"]][0]
        # Depends on 5 (done) and 8 (not done) -> blocked by 8
        self.assertTrue(fourth["blocked"])
        self.assertEqual(fourth["blocked_by"], [8])

    def test_all_pending_have_blocked_field(self):
        tasks = gd.get_pending_tasks(self.tmpdir)
        for task in tasks:
            self.assertIn("blocked", task)
            self.assertIn("blocked_by", task)
            self.assertIn("depends_on", task)


class TestNoDepsFile(unittest.TestCase):
    """Tasks without any depends-on lines should all be unblocked."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        todo_path = os.path.join(self.tmpdir, "TODO.md")
        with open(todo_path, "w") as f:
            f.write("# TODO\n\n- [ ] Task A\n- [ ] Task B\n- [x] Task C\n")

    def test_all_unblocked(self):
        tasks = gd.get_pending_tasks(self.tmpdir)
        for task in tasks:
            self.assertFalse(task["blocked"])


if __name__ == "__main__":
    unittest.main()
