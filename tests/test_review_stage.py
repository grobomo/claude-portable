#!/usr/bin/env python3
"""Tests for the REVIEW stage in the TDD pipeline.

Tests:
- Review verdict parsing (PROCEED, ALREADY_DONE, REFACTOR_FIRST)
- ALREADY_DONE auto-skip logic
- Stage numbering consistency (7 stages)
- Review file path generation
"""

import os
import re
import subprocess
import tempfile
import unittest


SCRIPT_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "scripts", "continuous-claude.sh"
))


class TestReviewStageStructure(unittest.TestCase):
    """Verify the REVIEW stage is correctly wired into the pipeline."""

    @classmethod
    def setUpClass(cls):
        with open(SCRIPT_PATH) as f:
            cls.script = f.read()

    def test_syntax_valid(self):
        """Script passes bash -n syntax check."""
        with open(SCRIPT_PATH, "rb") as f:
            script_bytes = f.read()
        # Strip \r so WSL/non-Git bash doesn't choke on CRLF
        script_bytes = script_bytes.replace(b"\r\n", b"\n")
        result = subprocess.run(
            ["bash", "-n"],
            input=script_bytes, capture_output=True
        )
        self.assertEqual(
            result.returncode, 0,
            f"Syntax error: {result.stderr.decode(errors='replace')}"
        )

    def test_seven_stages_in_header(self):
        """Header comment lists 7 stages."""
        header_lines = []
        for line in self.script.splitlines():
            if line.startswith("#"):
                header_lines.append(line)
            elif header_lines:
                break
        header = "\n".join(header_lines)
        self.assertIn("7-stage", header)
        self.assertIn("REVIEW", header)

    def test_stage_numbers_sequential(self):
        """Stage comments are numbered 1-7 with no gaps or duplicates."""
        stage_pattern = re.compile(r"# ===== STAGE (\d+):")
        stage_nums = [int(m.group(1)) for m in stage_pattern.finditer(self.script)]
        self.assertEqual(stage_nums, [1, 2, 3, 4, 5, 6, 7])

    def test_stage_names_match(self):
        """Stage names in comments match expected order."""
        stage_pattern = re.compile(r"# ===== STAGE \d+: (\w+)")
        stage_names = [m.group(1) for m in stage_pattern.finditer(self.script)]
        self.assertEqual(
            stage_names,
            ["RESEARCH", "REVIEW", "PLAN", "TESTS", "IMPLEMENT", "VERIFY", "PR"]
        )

    def test_run_stage_numbers_match_comments(self):
        """run_stage_with_retry calls use correct stage numbers."""
        call_pattern = re.compile(
            r'run_stage_with_retry\s+"(\w+)"\s+"(\d+)"'
        )
        calls = {m.group(1): int(m.group(2)) for m in call_pattern.finditer(self.script)}
        expected = {
            "RESEARCH": 1, "REVIEW": 2, "PLAN": 3, "TESTS": 4,
            "IMPLEMENT": 5, "VERIFY": 6, "PR": 7,
        }
        self.assertEqual(calls, expected)

    def test_review_file_variable_exists(self):
        """review_file variable is declared in run_pipeline."""
        self.assertIn('review_file="/tmp/task-${task_num}-review.md"', self.script)

    def test_review_prompt_includes_verdict_options(self):
        """REVIEW prompt requires one of three verdicts."""
        self.assertIn("PROCEED", self.script)
        self.assertIn("ALREADY_DONE", self.script)
        self.assertIn("REFACTOR_FIRST", self.script)

    def test_already_done_skip_logic(self):
        """Script checks review verdict and skips ALREADY_DONE tasks."""
        self.assertIn('review_verdict', self.script)
        self.assertIn('"ALREADY_DONE"', self.script)
        self.assertIn("Task is already implemented. Skipping.", self.script)

    def test_plan_reads_review_file(self):
        """PLAN stage prompt references the review file."""
        plan_section = self.script[self.script.index("STAGE 3: PLAN"):]
        plan_section = plan_section[:plan_section.index("run_stage_with_retry")]
        self.assertIn("review_file", plan_section)
        self.assertIn("Code review is at:", plan_section)

    def test_plan_handles_refactor_first(self):
        """PLAN prompt mentions REFACTOR_FIRST verdict."""
        plan_section = self.script[self.script.index("STAGE 3: PLAN"):]
        plan_section = plan_section[:plan_section.index("run_stage_with_retry")]
        self.assertIn("REFACTOR_FIRST", plan_section)


class TestReviewVerdictParsing(unittest.TestCase):
    """Test the grep-based verdict extraction logic."""

    def _parse_verdict(self, content):
        """Simulate the bash verdict parsing from the script."""
        # This mirrors: grep -oE 'VERDICT: (PROCEED|ALREADY_DONE|REFACTOR_FIRST)' | tail -1 | sed 's/VERDICT: //'
        matches = re.findall(
            r"VERDICT: (PROCEED|ALREADY_DONE|REFACTOR_FIRST)", content
        )
        return matches[-1] if matches else ""

    def test_proceed_verdict(self):
        review = "## Verdict\nVERDICT: PROCEED\nCodebase is clean."
        self.assertEqual(self._parse_verdict(review), "PROCEED")

    def test_already_done_verdict(self):
        review = "## Existing Implementations\nFound in foo.py:42\n\n## Verdict\nVERDICT: ALREADY_DONE"
        self.assertEqual(self._parse_verdict(review), "ALREADY_DONE")

    def test_refactor_first_verdict(self):
        review = "## Refactoring Needed\n5 files need changes\n\n## Verdict\nVERDICT: REFACTOR_FIRST"
        self.assertEqual(self._parse_verdict(review), "REFACTOR_FIRST")

    def test_no_verdict(self):
        review = "## Review\nSome notes but no verdict line."
        self.assertEqual(self._parse_verdict(review), "")

    def test_multiple_verdicts_takes_last(self):
        review = "VERDICT: REFACTOR_FIRST\n...\n## Final Verdict\nVERDICT: PROCEED"
        self.assertEqual(self._parse_verdict(review), "PROCEED")

    def test_verdict_in_noise(self):
        review = "lots of text\n## Verdict\nAfter reviewing, VERDICT: PROCEED\nmore text"
        self.assertEqual(self._parse_verdict(review), "PROCEED")

    def test_invalid_verdict_ignored(self):
        review = "VERDICT: SKIP\nVERDICT: PROCEED"
        self.assertEqual(self._parse_verdict(review), "PROCEED")


class TestEnforcementGates(unittest.TestCase):
    """Verify enforcement gates are present and numbered correctly."""

    @classmethod
    def setUpClass(cls):
        with open(SCRIPT_PATH) as f:
            cls.script = f.read()

    def test_seven_gates_present(self):
        """All 7 gates exist in the script."""
        for n in range(1, 8):
            self.assertIn(
                f"GATE {n}",
                self.script,
                f"Gate {n} not found in script"
            )

    def test_gate_1_checks_research(self):
        """Gate 1 checks research file size >500 chars."""
        gate1 = self.script[self.script.index("GATE 1"):self.script.index("GATE 2")]
        self.assertIn("500", gate1)
        self.assertIn("research_file", gate1)

    def test_gate_2_checks_review_verdict(self):
        """Gate 2 checks review file has a VERDICT."""
        gate2 = self.script[self.script.index("GATE 2"):self.script.index("GATE 3")]
        self.assertIn("VERDICT", gate2)
        self.assertIn("review_file", gate2)

    def test_gate_3_checks_plan(self):
        """Gate 3 checks plan file size >100 chars."""
        gate3 = self.script[self.script.index("GATE 3"):self.script.index("GATE 4")]
        self.assertIn("100", gate3)
        self.assertIn("plan_file", gate3)

    def test_gate_4_checks_test_files(self):
        """Gate 4 checks test files were added."""
        gate4 = self.script[self.script.index("GATE 4"):self.script.index("GATE 5")]
        self.assertIn("test_files_added", gate4)

    def test_gate_5_checks_tests_fail(self):
        """Gate 5 verifies tests fail before implementation."""
        gate5 = self.script[self.script.index("GATE 5"):self.script.index("GATE 6")]
        self.assertIn("test_run_cmd", gate5)
        self.assertIn("fail", gate5.lower())

    def test_gate_6_checks_tests_pass(self):
        """Gate 6 verifies tests pass after implementation."""
        gate6 = self.script[self.script.index("GATE 6"):self.script.index("GATE 7")]
        self.assertIn("test_run_cmd", gate6)
        self.assertIn("pass", gate6.lower())

    def test_gate_7_checks_secrets(self):
        """Gate 7 checks for secrets and personal paths in diff."""
        gate7_start = self.script.index("GATE 7")
        gate7 = self.script[gate7_start:gate7_start + 1500]
        self.assertIn("C:/Users/", gate7)
        self.assertIn("AKIA", gate7)
        self.assertIn("bash -n", gate7)

    def test_gates_return_1_on_failure(self):
        """All gates return 1 on failure."""
        for n in range(1, 8):
            marker = f"GATE {n} FAILED"
            self.assertIn(marker, self.script, f"Gate {n} missing FAILED message")


if __name__ == "__main__":
    unittest.main()
