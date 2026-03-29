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
        with open(SCRIPT_PATH) as f:
            script_content = f.read()
        # Strip \r so WSL bash doesn't choke on CRLF
        script_content = script_content.replace("\r", "")
        result = subprocess.run(
            ["bash", "-n"],
            input=script_content, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, f"Syntax error: {result.stderr}")

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


if __name__ == "__main__":
    unittest.main()
