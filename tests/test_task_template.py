#!/usr/bin/env python3
"""Tests for task template checker."""

import importlib.machinery
import importlib.util
import os
import sys
import unittest

_checker_path = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "scripts", "check-task-template.py"
))
loader = importlib.machinery.SourceFileLoader("check_task_template", _checker_path)
spec = importlib.util.spec_from_loader("check_task_template", loader)
ct = importlib.util.module_from_spec(spec)
loader.exec_module(ct)

VALID_TASK = """\
- [ ] Add rolling chat cache to dispatcher
  - What: dispatcher writes last 50 Teams messages to disk
  - Why: workers have no conversation context
  - How: in teams-chat-bridge.py poll_once(), write to txt
  - Acceptance: file exists after one poll cycle with 50 lines
  - PR title: "feat: rolling chat cache"
"""

MISSING_WHY = """\
- [ ] Add something
  - What: a thing
  - How: do it
  - Acceptance: it works
  - PR title: "feat: add something"
"""

MINIMAL_BAD = """\
- [ ] Fix the thing
  - PR title: "fix: stuff"
"""

MIXED = """\
- [x] Already done task
  - PR title: "feat: done"

- [ ] Valid task
  - What: a thing
  - Why: needed
  - How: do it
  - Acceptance: test passes
  - PR title: "feat: valid"

- [ ] Invalid task
  - PR title: "feat: bad"
"""


class TestParseTasks(unittest.TestCase):
    def test_parse_valid_task(self):
        tasks = ct.parse_tasks(VALID_TASK)
        self.assertEqual(len(tasks), 1)
        self.assertIn("what", tasks[0]["fields"])
        self.assertIn("why", tasks[0]["fields"])
        self.assertIn("how", tasks[0]["fields"])
        self.assertIn("acceptance", tasks[0]["fields"])
        self.assertIn("pr title", tasks[0]["fields"])

    def test_parse_skips_checked_tasks(self):
        tasks = ct.parse_tasks("- [x] Done task\n  - PR title: \"done\"")
        self.assertEqual(len(tasks), 0)

    def test_parse_multiple_tasks(self):
        tasks = ct.parse_tasks(MIXED)
        self.assertEqual(len(tasks), 2)  # Only unchecked

    def test_parse_empty(self):
        tasks = ct.parse_tasks("")
        self.assertEqual(len(tasks), 0)


class TestCheckTasks(unittest.TestCase):
    def test_valid_task_passes(self):
        tasks = ct.parse_tasks(VALID_TASK)
        errors = ct.check_tasks(tasks)
        self.assertEqual(errors, [])

    def test_missing_why_detected(self):
        tasks = ct.parse_tasks(MISSING_WHY)
        errors = ct.check_tasks(tasks)
        self.assertEqual(len(errors), 1)
        self.assertIn("why", errors[0].lower())

    def test_minimal_bad_many_missing(self):
        tasks = ct.parse_tasks(MINIMAL_BAD)
        errors = ct.check_tasks(tasks)
        self.assertEqual(len(errors), 1)
        # Should list what, why, how, acceptance as missing
        self.assertIn("what", errors[0].lower())
        self.assertIn("why", errors[0].lower())

    def test_mixed_only_bad_flagged(self):
        tasks = ct.parse_tasks(MIXED)
        errors = ct.check_tasks(tasks)
        self.assertEqual(len(errors), 1)
        self.assertIn("Invalid task", errors[0])

    def test_context_field_optional(self):
        """Context is optional — task without it should pass."""
        no_context = """\
- [ ] Task without context
  - What: thing
  - Why: reason
  - How: approach
  - Acceptance: test
  - PR title: "feat: no context"
"""
        tasks = ct.parse_tasks(no_context)
        errors = ct.check_tasks(tasks)
        self.assertEqual(errors, [])

    def test_code_block_tasks_skipped(self):
        """Tasks inside fenced code blocks should not be parsed."""
        content = """\
- [ ] Real task
  - What: do stuff
  - Why: because
  - How: like this
  - Acceptance: it works
  - PR title: "feat: real"

Example:
```
- [ ] Example task in code block
  - PR title: "feat: example"
```
"""
        tasks = ct.parse_tasks(content)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["description"], "Real task")


if __name__ == "__main__":
    unittest.main()
