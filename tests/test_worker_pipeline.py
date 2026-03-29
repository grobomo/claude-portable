#!/usr/bin/env python3
"""Tests for worker-pipeline.py state tracker."""

import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import unittest

# Load worker-pipeline.py as a module
_pipeline_path = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "scripts", "worker-pipeline.py"
))
loader = importlib.machinery.SourceFileLoader("worker_pipeline", _pipeline_path)
spec = importlib.util.spec_from_loader("worker_pipeline", loader)
wp = importlib.util.module_from_spec(spec)
loader.exec_module(wp)


class TestWorkerPipelineStart(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.tmpdir, "pipeline-state.json")
        self._orig = wp.STATE_FILE
        wp.STATE_FILE = self.state_file

    def tearDown(self):
        wp.STATE_FILE = self._orig
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_start_creates_state_file(self):
        wp.cmd_start(["1", "Add", "dark", "mode"])
        self.assertTrue(os.path.isfile(self.state_file))

    def test_start_state_has_required_fields(self):
        wp.cmd_start(["3", "Fix", "the", "bug"])
        with open(self.state_file) as f:
            state = json.load(f)
        self.assertEqual(state["task_num"], 3)
        self.assertEqual(state["description"], "Fix the bug")
        self.assertEqual(state["status"], "running")
        self.assertIsNone(state["current_phase"])
        self.assertIn("started_at", state)
        self.assertIn("updated_at", state)
        self.assertEqual(state["phases"], {})

    def test_start_missing_args_returns_error(self):
        result = wp.cmd_start(["1"])
        self.assertEqual(result, 1)


class TestWorkerPipelinePhase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.tmpdir, "pipeline-state.json")
        self._orig = wp.STATE_FILE
        wp.STATE_FILE = self.state_file
        wp.cmd_start(["1", "Test", "task"])

    def tearDown(self):
        wp.STATE_FILE = self._orig
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_phase_running(self):
        wp.cmd_phase(["RESEARCH", "running"])
        with open(self.state_file) as f:
            state = json.load(f)
        self.assertEqual(state["current_phase"], "RESEARCH")
        self.assertEqual(state["phases"]["RESEARCH"]["status"], "running")
        self.assertIn("start", state["phases"]["RESEARCH"])

    def test_phase_passed_with_output(self):
        wp.cmd_phase(["RESEARCH", "running"])
        wp.cmd_phase(["RESEARCH", "passed", "/tmp/task-1-research.md"])
        with open(self.state_file) as f:
            state = json.load(f)
        self.assertEqual(state["phases"]["RESEARCH"]["status"], "passed")
        self.assertEqual(state["phases"]["RESEARCH"]["output_file"], "/tmp/task-1-research.md")
        self.assertIn("end", state["phases"]["RESEARCH"])

    def test_phase_failed_with_error(self):
        wp.cmd_phase(["PLAN", "running"])
        wp.cmd_phase(["PLAN", "failed", "Output too short"])
        with open(self.state_file) as f:
            state = json.load(f)
        self.assertEqual(state["phases"]["PLAN"]["status"], "failed")
        self.assertEqual(state["phases"]["PLAN"]["error"], "Output too short")

    def test_phase_names_uppercased(self):
        wp.cmd_phase(["research", "running"])
        with open(self.state_file) as f:
            state = json.load(f)
        self.assertIn("RESEARCH", state["phases"])

    def test_multiple_phases_tracked(self):
        for phase in ["RESEARCH", "REVIEW", "PLAN"]:
            wp.cmd_phase([phase, "running"])
            wp.cmd_phase([phase, "passed"])
        with open(self.state_file) as f:
            state = json.load(f)
        self.assertEqual(len(state["phases"]), 3)
        for phase in ["RESEARCH", "REVIEW", "PLAN"]:
            self.assertEqual(state["phases"][phase]["status"], "passed")

    def test_phase_no_active_task_returns_error(self):
        wp.STATE_FILE = os.path.join(self.tmpdir, "nonexistent.json")
        result = wp.cmd_phase(["RESEARCH", "running"])
        self.assertEqual(result, 1)

    def test_phase_unknown_status_returns_error(self):
        result = wp.cmd_phase(["RESEARCH", "banana"])
        self.assertEqual(result, 1)


class TestWorkerPipelineGate(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.tmpdir, "pipeline-state.json")
        self._orig = wp.STATE_FILE
        wp.STATE_FILE = self.state_file
        wp.cmd_start(["1", "Test", "task"])

    def tearDown(self):
        wp.STATE_FILE = self._orig
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_gate_passed(self):
        wp.cmd_phase(["RESEARCH", "passed"])
        wp.cmd_gate(["RESEARCH", "passed"])
        with open(self.state_file) as f:
            state = json.load(f)
        self.assertEqual(state["phases"]["RESEARCH"]["gate_result"], "passed")

    def test_gate_failed_with_reason(self):
        wp.cmd_gate(["TESTS", "failed", "No test files found"])
        with open(self.state_file) as f:
            state = json.load(f)
        self.assertEqual(state["phases"]["TESTS"]["gate_result"], "failed")
        self.assertEqual(state["phases"]["TESTS"]["gate_reason"], "No test files found")


class TestWorkerPipelineDoneIdle(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.tmpdir, "pipeline-state.json")
        self._orig = wp.STATE_FILE
        wp.STATE_FILE = self.state_file

    def tearDown(self):
        wp.STATE_FILE = self._orig
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_done_marks_complete(self):
        wp.cmd_start(["1", "Test"])
        wp.cmd_done([])
        with open(self.state_file) as f:
            state = json.load(f)
        self.assertEqual(state["status"], "done")
        self.assertIsNone(state["current_phase"])
        self.assertIn("completed_at", state)

    def test_idle_resets_state(self):
        wp.cmd_start(["1", "Test"])
        wp.cmd_phase(["RESEARCH", "running"])
        wp.cmd_idle([])
        with open(self.state_file) as f:
            state = json.load(f)
        self.assertEqual(state["status"], "idle")
        self.assertIsNone(state["task_num"])
        self.assertEqual(state["phases"], {})

    def test_done_on_empty_state_no_crash(self):
        result = wp.cmd_done([])
        self.assertEqual(result, 0)


class TestWorkerPipelineStatus(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.tmpdir, "pipeline-state.json")
        self._orig = wp.STATE_FILE
        wp.STATE_FILE = self.state_file

    def tearDown(self):
        wp.STATE_FILE = self._orig
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_status_prints_json(self):
        wp.cmd_start(["1", "Test"])
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            wp.cmd_status([])
        output = buf.getvalue()
        data = json.loads(output)
        self.assertEqual(data["task_num"], 1)

    def test_status_empty_state(self):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            wp.cmd_status([])
        data = json.loads(buf.getvalue())
        self.assertEqual(data, {})


class TestWorkerPipelineMain(unittest.TestCase):
    def test_unknown_command_returns_error(self):
        original_argv = sys.argv
        sys.argv = ["worker-pipeline.py", "banana"]
        try:
            result = wp.main()
            self.assertEqual(result, 1)
        finally:
            sys.argv = original_argv

    def test_no_args_returns_error(self):
        original_argv = sys.argv
        sys.argv = ["worker-pipeline.py"]
        try:
            result = wp.main()
            self.assertEqual(result, 1)
        finally:
            sys.argv = original_argv


class TestWorkerPipelineWhyPhase(unittest.TestCase):
    """Test WHY phase is registered as stage 0 in the pipeline."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.tmpdir, "pipeline-state.json")
        self._orig = wp.STATE_FILE
        wp.STATE_FILE = self.state_file

    def tearDown(self):
        wp.STATE_FILE = self._orig
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_why_is_first_phase(self):
        self.assertEqual(wp.PHASES[0], "WHY")

    def test_why_phase_tracked_in_state(self):
        wp.cmd_start(["1", "Test", "task"])
        wp.cmd_phase(["WHY", "running"])
        with open(self.state_file) as f:
            state = json.load(f)
        self.assertEqual(state["current_phase"], "WHY")
        self.assertEqual(state["phases"]["WHY"]["status"], "running")

    def test_why_phase_passed(self):
        wp.cmd_start(["1", "Test"])
        wp.cmd_phase(["WHY", "running"])
        wp.cmd_phase(["WHY", "passed", "/tmp/why.md"])
        with open(self.state_file) as f:
            state = json.load(f)
        self.assertEqual(state["phases"]["WHY"]["status"], "passed")
        self.assertEqual(state["phases"]["WHY"]["output_file"], "/tmp/why.md")

    def test_why_gate_recorded(self):
        wp.cmd_start(["1", "Test"])
        wp.cmd_phase(["WHY", "running"])
        wp.cmd_gate(["WHY", "passed"])
        with open(self.state_file) as f:
            state = json.load(f)
        self.assertEqual(state["phases"]["WHY"]["gate_result"], "passed")

    def test_why_skip_gate_recorded(self):
        wp.cmd_start(["1", "Test"])
        wp.cmd_phase(["WHY", "running"])
        wp.cmd_gate(["WHY", "failed", "VERDICT: SKIP"])
        with open(self.state_file) as f:
            state = json.load(f)
        self.assertEqual(state["phases"]["WHY"]["gate_result"], "failed")
        self.assertEqual(state["phases"]["WHY"]["gate_reason"], "VERDICT: SKIP")

    def test_full_pipeline_sequence_with_why(self):
        """WHY -> RESEARCH -> ... -> PR all track correctly."""
        wp.cmd_start(["1", "Test"])
        for phase in wp.PHASES:
            wp.cmd_phase([phase, "running"])
            wp.cmd_phase([phase, "passed"])
        with open(self.state_file) as f:
            state = json.load(f)
        self.assertEqual(len(state["phases"]), len(wp.PHASES))
        for phase in wp.PHASES:
            self.assertEqual(state["phases"][phase]["status"], "passed")


if __name__ == "__main__":
    unittest.main()
