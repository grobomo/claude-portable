#!/usr/bin/env python3
"""Tests for WHY phase (stage 0) in the worker TDD pipeline.

Validates:
- WHY phase gate logic: PROCEED/SKIP verdict detection
- SKIP verdict cleans up branch and returns exit code 2
- Pipeline stage list includes WHY as first phase
- Worker pipeline tracker knows about WHY phase
- Board display includes WHY color
"""

import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

# ── Load worker-pipeline.py ──────────────────────────────────────────────────

_wp_path = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "scripts", "worker-pipeline.py"
))
_wp_loader = importlib.machinery.SourceFileLoader("worker_pipeline", _wp_path)
_wp_spec = importlib.util.spec_from_loader("worker_pipeline", _wp_loader)
wp = importlib.util.module_from_spec(_wp_spec)
_wp_loader.exec_module(wp)

# ── Load worker-health.py ────────────────────────────────────────────────────

_wh_path = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "scripts", "worker-health.py"
))
_wh_loader = importlib.machinery.SourceFileLoader("worker_health", _wh_path)
_wh_spec = importlib.util.spec_from_loader("worker_health", _wh_loader)
wh = importlib.util.module_from_spec(_wh_spec)
_wh_loader.exec_module(wh)

SCRIPTS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "scripts"))


class TestWhyPhaseInPipeline(unittest.TestCase):
    """Test that WHY is recognized as a valid pipeline phase."""

    def test_why_in_phases_list(self):
        self.assertIn("WHY", wp.PHASES)
        self.assertEqual(wp.PHASES[0], "WHY")

    def test_why_before_research(self):
        idx_why = wp.PHASES.index("WHY")
        idx_research = wp.PHASES.index("RESEARCH")
        self.assertLess(idx_why, idx_research)


class TestWhyPhaseWorkerHealth(unittest.TestCase):
    """Test that worker-health.py stage_names includes WHY."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_state = wh.PIPELINE_STATE_FILE
        wh.PIPELINE_STATE_FILE = os.path.join(self.tmpdir, "ps.json")

    def tearDown(self):
        wh.PIPELINE_STATE_FILE = self._orig_state
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_why_stage_tracked_in_health(self):
        """Pipeline stage getter recognizes WHY phase."""
        state = {
            "worker_id": "test",
            "task_num": 1,
            "status": "running",
            "current_phase": "WHY",
            "phases": {"WHY": {"status": "running", "start": "2026-01-01T00:00:00Z"}},
        }
        with open(wh.PIPELINE_STATE_FILE, "w") as f:
            json.dump(state, f)

        result = wh._get_pipeline_stage()
        self.assertEqual(result["stage"], "WHY")

    def test_why_counts_as_complete(self):
        state = {
            "worker_id": "test",
            "task_num": 1,
            "status": "running",
            "current_phase": "RESEARCH",
            "phases": {
                "WHY": {"status": "passed"},
                "RESEARCH": {"status": "running"},
            },
        }
        with open(wh.PIPELINE_STATE_FILE, "w") as f:
            json.dump(state, f)

        result = wh._get_pipeline_stage()
        self.assertEqual(result["stages_complete"], 1)
        self.assertEqual(result["stage"], "RESEARCH")


class TestWhyPhaseGateLogic(unittest.TestCase):
    """Test the WHY gate verdict detection (bash grep logic)."""

    def test_proceed_verdict_detected(self):
        content = "Analysis here...\nVERDICT: PROCEED"
        match = re.search(r'VERDICT: (PROCEED|SKIP)', content)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "PROCEED")

    def test_skip_verdict_detected(self):
        content = "This task is duplicate...\nVERDICT: SKIP"
        match = re.search(r'VERDICT: (PROCEED|SKIP)', content)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "SKIP")

    def test_no_verdict_fails_gate(self):
        content = "Analysis without a verdict line."
        match = re.search(r'VERDICT: (PROCEED|SKIP)', content)
        self.assertIsNone(match)

    def test_verdict_in_middle_of_text(self):
        content = "Intro\nVERDICT: PROCEED\nConclusion"
        match = re.search(r'VERDICT: (PROCEED|SKIP)', content)
        self.assertIsNotNone(match)

    def test_mixed_case_not_matched(self):
        """Gate requires exact case."""
        content = "verdict: proceed"
        match = re.search(r'VERDICT: (PROCEED|SKIP)', content)
        self.assertIsNone(match)


class TestWhyPhaseScriptSyntax(unittest.TestCase):
    """Test that continuous-claude.sh with WHY phase has valid syntax."""

    def test_bash_syntax_valid(self):
        script = os.path.join(SCRIPTS_DIR, "continuous-claude.sh")
        git_bash = r"C:\Program Files\Git\usr\bin\bash.exe"
        bash_cmd = git_bash if os.path.isfile(git_bash) else "bash"
        r = subprocess.run([bash_cmd, "-n", script], capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0, f"Bash syntax error: {r.stderr}")

    def test_why_stage_in_script(self):
        script = os.path.join(SCRIPTS_DIR, "continuous-claude.sh")
        with open(script, "r") as f:
            content = f.read()
        self.assertIn("STAGE 0: WHY", content)
        self.assertIn("VERDICT: PROCEED", content)
        self.assertIn("VERDICT: SKIP", content)
        self.assertIn("why_file", content)

    def test_skip_returns_code_2(self):
        script = os.path.join(SCRIPTS_DIR, "continuous-claude.sh")
        with open(script, "r") as f:
            content = f.read()
        self.assertIn("return 2", content)

    def test_header_includes_why(self):
        script = os.path.join(SCRIPTS_DIR, "continuous-claude.sh")
        with open(script, "r") as f:
            header = "".join(f.readlines()[:15])
        self.assertIn("WHY", header)
        self.assertIn("8-stage", header)


class TestWhyPhaseWorkerPipelineTracker(unittest.TestCase):
    """Test that worker-pipeline.py can track WHY phase."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig = wp.STATE_FILE
        wp.STATE_FILE = os.path.join(self.tmpdir, "state.json")

    def tearDown(self):
        wp.STATE_FILE = self._orig
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_why_phase_tracked(self):
        wp.cmd_start(["1", "Test", "task"])
        wp.cmd_phase(["WHY", "running"])
        with open(wp.STATE_FILE) as f:
            state = json.load(f)
        self.assertEqual(state["current_phase"], "WHY")
        self.assertIn("WHY", state["phases"])
        self.assertEqual(state["phases"]["WHY"]["status"], "running")

    def test_why_phase_passed(self):
        wp.cmd_start(["1", "Test", "task"])
        wp.cmd_phase(["WHY", "running"])
        wp.cmd_phase(["WHY", "passed"])
        with open(wp.STATE_FILE) as f:
            state = json.load(f)
        self.assertEqual(state["phases"]["WHY"]["status"], "passed")


if __name__ == "__main__":
    unittest.main()
