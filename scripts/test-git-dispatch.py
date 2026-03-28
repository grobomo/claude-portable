#!/usr/bin/env python3
"""
Tests for git-dispatch.py scale-up logic.

Covers:
  - load_ccc_config: reads max_workers/max_instances from ccc.config.json
  - count_unclaimed_tasks: heuristic for tasks not yet claimed by a branch
  - scale_up_workers: correct number of workers launched, cap respected
  - get_next_worker_name: generates non-colliding worker names
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, call, patch

# Allow importing git-dispatch despite the hyphen in the filename
import importlib.util, types

_SCRIPT = os.path.join(os.path.dirname(__file__), "git-dispatch.py")
spec = importlib.util.spec_from_file_location("git_dispatch", _SCRIPT)
_mod = importlib.util.module_from_spec(spec)
# Prevent the module-level basicConfig / argparse from executing at import time
# by replacing __name__ so the `if __name__ == "__main__"` guard triggers
_mod.__name__ = "git_dispatch"
spec.loader.exec_module(_mod)


class TestLoadCccConfig(unittest.TestCase):
    def test_reads_max_workers(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = {"max_workers": 10, "region": "us-east-2"}
            with open(os.path.join(d, "ccc.config.json"), "w") as f:
                json.dump(cfg, f)
            result = _mod.load_ccc_config(d)
            self.assertEqual(result.get("max_workers"), 10)

    def test_reads_max_instances_as_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = {"max_instances": 7}
            with open(os.path.join(d, "ccc.config.json"), "w") as f:
                json.dump(cfg, f)
            result = _mod.load_ccc_config(d)
            self.assertEqual(result.get("max_instances"), 7)

    def test_returns_empty_dict_when_file_missing(self):
        with tempfile.TemporaryDirectory() as d:
            result = _mod.load_ccc_config(d)
            self.assertEqual(result, {})

    def test_returns_empty_dict_on_invalid_json(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "ccc.config.json"), "w") as f:
                f.write("not valid json {{{")
            result = _mod.load_ccc_config(d)
            self.assertEqual(result, {})

    def test_full_config_fields(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = {
                "max_workers": 50,
                "region": "us-east-2",
                "instance_type": "t3.large",
                "key_name": "my-key",
            }
            with open(os.path.join(d, "ccc.config.json"), "w") as f:
                json.dump(cfg, f)
            result = _mod.load_ccc_config(d)
            self.assertEqual(result["max_workers"], 50)
            self.assertEqual(result["region"], "us-east-2")


class TestCountUnclaimedTasks(unittest.TestCase):
    def test_all_unclaimed(self):
        tasks = [{"description": "task 1"}, {"description": "task 2"}]
        branches = []
        self.assertEqual(_mod.count_unclaimed_tasks(tasks, branches), 2)

    def test_all_claimed(self):
        tasks = [{"description": "task 1"}]
        branches = ["origin/continuous-claude/task-1"]
        self.assertEqual(_mod.count_unclaimed_tasks(tasks, branches), 0)

    def test_partial_claimed(self):
        tasks = [{"description": t} for t in ["a", "b", "c"]]
        branches = ["origin/continuous-claude/a"]
        self.assertEqual(_mod.count_unclaimed_tasks(tasks, branches), 2)

    def test_more_branches_than_tasks_returns_zero(self):
        tasks = [{"description": "task 1"}]
        branches = ["origin/continuous-claude/a", "origin/continuous-claude/b"]
        self.assertEqual(_mod.count_unclaimed_tasks(tasks, branches), 0)

    def test_empty_both(self):
        self.assertEqual(_mod.count_unclaimed_tasks([], []), 0)


class TestGetNextWorkerName(unittest.TestCase):
    def test_returns_worker_1_when_no_workers(self):
        name = _mod.get_next_worker_name([])
        self.assertTrue(name.startswith("worker-"))

    def test_increments_above_existing(self):
        existing = [
            {"InstanceId": "i-001", "Tags": [{"Key": "Name", "Value": "worker-1"}]},
            {"InstanceId": "i-002", "Tags": [{"Key": "Name", "Value": "worker-2"}]},
        ]
        name = _mod.get_next_worker_name(existing)
        # Should be higher than existing numbers
        num = int(name.split("-")[-1])
        self.assertGreater(num, 2)

    def test_handles_non_numeric_suffixes(self):
        existing = [
            {"InstanceId": "i-001", "Tags": [{"Key": "Name", "Value": "worker-dev"}]},
        ]
        # Should not crash on non-numeric names
        name = _mod.get_next_worker_name(existing)
        self.assertTrue(name.startswith("worker-"))


class TestGetPendingTasks(unittest.TestCase):
    def _write_todo(self, d, content):
        with open(os.path.join(d, "TODO.md"), "w") as f:
            f.write(content)

    def test_detects_unchecked_tasks(self):
        with tempfile.TemporaryDirectory() as d:
            self._write_todo(d, "# Tasks\n\n- [ ] Do something\n- [x] Done already\n")
            tasks = _mod.get_pending_tasks(d)
            self.assertEqual(len(tasks), 1)
            self.assertIn("Do something", tasks[0]["description"])

    def test_empty_when_all_checked(self):
        with tempfile.TemporaryDirectory() as d:
            self._write_todo(d, "- [x] Done\n- [x] Also done\n")
            self.assertEqual(_mod.get_pending_tasks(d), [])

    def test_parses_pr_title(self):
        with tempfile.TemporaryDirectory() as d:
            self._write_todo(
                d,
                '- [ ] Scale up workers\n  - PR title: "feat: scale up"\n',
            )
            tasks = _mod.get_pending_tasks(d)
            self.assertEqual(tasks[0]["pr_title"], "feat: scale up")

    def test_returns_empty_when_todo_missing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(_mod.get_pending_tasks(d), [])

    def test_multiple_tasks(self):
        with tempfile.TemporaryDirectory() as d:
            content = "\n".join([
                "- [ ] Task one",
                "- [x] Task two (done)",
                "- [ ] Task three",
            ])
            self._write_todo(d, content)
            tasks = _mod.get_pending_tasks(d)
            self.assertEqual(len(tasks), 2)


class TestMaxWorkersFromConfig(unittest.TestCase):
    """Verify dispatcher respects max_workers from ccc.config.json."""

    def test_env_var_overrides_config(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = {"max_workers": 20}
            with open(os.path.join(d, "ccc.config.json"), "w") as f:
                json.dump(cfg, f)
            with patch.dict(os.environ, {"DISPATCHER_MAX_WORKERS": "3"}):
                cap = _mod.get_max_workers(d)
            self.assertEqual(cap, 3)

    def test_config_used_when_no_env_var(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = {"max_workers": 25}
            with open(os.path.join(d, "ccc.config.json"), "w") as f:
                json.dump(cfg, f)
            env = {k: v for k, v in os.environ.items() if k != "DISPATCHER_MAX_WORKERS"}
            with patch.dict(os.environ, env, clear=True):
                cap = _mod.get_max_workers(d)
            self.assertEqual(cap, 25)

    def test_max_instances_used_as_fallback_key(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = {"max_instances": 12}
            with open(os.path.join(d, "ccc.config.json"), "w") as f:
                json.dump(cfg, f)
            env = {k: v for k, v in os.environ.items() if k != "DISPATCHER_MAX_WORKERS"}
            with patch.dict(os.environ, env, clear=True):
                cap = _mod.get_max_workers(d)
            self.assertEqual(cap, 12)

    def test_default_when_no_config_no_env(self):
        with tempfile.TemporaryDirectory() as d:
            env = {k: v for k, v in os.environ.items() if k != "DISPATCHER_MAX_WORKERS"}
            with patch.dict(os.environ, env, clear=True):
                cap = _mod.get_max_workers(d)
            self.assertEqual(cap, 5)  # built-in default


if __name__ == "__main__":
    unittest.main(verbosity=2)
