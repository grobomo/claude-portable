#!/usr/bin/env python3
"""Tests for dispatcher dependency analysis feature.

Validates:
- Claude output parsing: extract dependency annotations from analysis text
- TODO.md annotation: inject depends-on lines without duplicating existing ones
- Skip already-annotated tasks
- Don't annotate completed tasks
- Git commit only when TODO.md actually changed
"""

import importlib
import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

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

- [ ] Second task no deps
  - PR title: "feat: second thing"

- [ ] Third task should depend on second
  - PR title: "feat: third thing"

- [ ] Fourth task already has deps
  - PR title: "feat: fourth thing"
  - depends-on: 8

- [ ] Fifth task should depend on third and second
  - PR title: "feat: fifth thing"
"""

# Simulated Claude analysis output
SAMPLE_ANALYSIS = """\
After analyzing the codebase and TODO.md, here are the dependency annotations:

DEPENDENCY: line 11 depends-on: 8
DEPENDENCY: line 17 depends-on: 11, 8
"""


class TestParseAnalysisOutput(unittest.TestCase):
    """Test parsing Claude's dependency analysis output."""

    def test_parse_single_dependency(self):
        output = "DEPENDENCY: line 8 depends-on: 5"
        deps = gd.parse_dependency_analysis(output)
        self.assertEqual(deps, {8: [5]})

    def test_parse_multiple_dependencies(self):
        output = "DEPENDENCY: line 17 depends-on: 11, 8"
        deps = gd.parse_dependency_analysis(output)
        self.assertEqual(deps, {17: [11, 8]})

    def test_parse_multiple_lines(self):
        deps = gd.parse_dependency_analysis(SAMPLE_ANALYSIS)
        self.assertEqual(deps, {11: [8], 17: [11, 8]})

    def test_parse_empty_output(self):
        deps = gd.parse_dependency_analysis("")
        self.assertEqual(deps, {})

    def test_parse_no_dependencies_found(self):
        output = "After analysis, no dependencies were found between tasks."
        deps = gd.parse_dependency_analysis(output)
        self.assertEqual(deps, {})

    def test_parse_ignores_non_dependency_lines(self):
        output = """\
I found some relationships.
DEPENDENCY: line 8 depends-on: 5
This is just commentary.
DEPENDENCY: line 11 depends-on: 8
More text here.
"""
        deps = gd.parse_dependency_analysis(output)
        self.assertEqual(deps, {8: [5], 11: [8]})

    def test_parse_deduplicates_deps(self):
        output = "DEPENDENCY: line 8 depends-on: 5, 5, 5"
        deps = gd.parse_dependency_analysis(output)
        self.assertEqual(deps, {8: [5]})


class TestAnnotateTodo(unittest.TestCase):
    """Test injecting depends-on lines into TODO.md content."""

    def test_add_new_dependency(self):
        deps = {11: [8]}  # line 11 = "Third task" depends on line 8
        result = gd.annotate_todo_with_deps(SAMPLE_TODO, deps)
        lines = result.splitlines()
        third_idx = next(i for i, l in enumerate(lines) if "Third task" in l)
        sub_lines = []
        for j in range(third_idx + 1, len(lines)):
            if lines[j].startswith("  ") or lines[j].startswith("\t"):
                sub_lines.append(lines[j])
            elif lines[j].strip() == "":
                continue
            else:
                break
        dep_lines = [l for l in sub_lines if "depends-on:" in l.lower()]
        self.assertEqual(len(dep_lines), 1)
        self.assertIn("8", dep_lines[0])

    def test_skip_existing_dependency(self):
        # Fourth task already has depends-on: 8, so adding 8 again should not duplicate
        deps = {14: [8]}  # line 14 = "Fourth task"
        result = gd.annotate_todo_with_deps(SAMPLE_TODO, deps)
        lines = result.splitlines()
        fourth_idx = next(i for i, l in enumerate(lines) if "Fourth task" in l)
        dep_count = 0
        for j in range(fourth_idx + 1, min(fourth_idx + 5, len(lines))):
            if "depends-on:" in lines[j].lower():
                dep_count += 1
        self.assertEqual(dep_count, 1, "Should not duplicate existing depends-on line")

    def test_no_changes_returns_original(self):
        deps = {}
        result = gd.annotate_todo_with_deps(SAMPLE_TODO, deps)
        self.assertEqual(result, SAMPLE_TODO)

    def test_skip_completed_tasks(self):
        # Line 5 is completed ("First task done") - deps should not be added
        deps = {5: [99]}
        result = gd.annotate_todo_with_deps(SAMPLE_TODO, deps)
        self.assertEqual(result, SAMPLE_TODO, "Should not annotate completed tasks")

    def test_multiple_deps_added(self):
        deps = {17: [11, 8]}  # line 17 = "Fifth task" depends on 11 and 8
        result = gd.annotate_todo_with_deps(SAMPLE_TODO, deps)
        lines = result.splitlines()
        fifth_idx = next(i for i, l in enumerate(lines) if "Fifth task" in l)
        sub_lines = []
        for j in range(fifth_idx + 1, len(lines)):
            if lines[j].strip().startswith("-") and "  " in lines[j][:4]:
                sub_lines.append(lines[j])
            elif lines[j].strip() == "":
                continue
            else:
                break
        dep_lines = [l for l in sub_lines if "depends-on:" in l.lower()]
        self.assertEqual(len(dep_lines), 1)
        self.assertIn("11", dep_lines[0])
        self.assertIn("8", dep_lines[0])

    def test_merge_new_deps_with_existing(self):
        # Fourth task has depends-on: 8. Adding dep on 11 should merge.
        deps = {14: [8, 11]}
        result = gd.annotate_todo_with_deps(SAMPLE_TODO, deps)
        lines = result.splitlines()
        fourth_idx = next(i for i, l in enumerate(lines) if "Fourth task" in l)
        dep_lines = []
        for j in range(fourth_idx + 1, min(fourth_idx + 5, len(lines))):
            if "depends-on:" in lines[j].lower():
                dep_lines.append(lines[j])
        self.assertEqual(len(dep_lines), 1)
        self.assertIn("11", dep_lines[0])
        self.assertIn("8", dep_lines[0])


class TestBuildAnalysisPrompt(unittest.TestCase):
    """Test that the analysis prompt includes necessary context."""

    def test_prompt_includes_todo_content(self):
        prompt = gd.build_dependency_analysis_prompt(SAMPLE_TODO)
        self.assertIn("Third task", prompt)
        self.assertIn("DEPENDENCY:", prompt)

    def test_prompt_includes_line_numbers(self):
        prompt = gd.build_dependency_analysis_prompt(SAMPLE_TODO)
        # Should have numbered lines for reference
        self.assertIn("8:", prompt)

    def test_prompt_includes_format_instruction(self):
        prompt = gd.build_dependency_analysis_prompt(SAMPLE_TODO)
        self.assertIn("DEPENDENCY: line", prompt)


class TestApplyAnnotations(unittest.TestCase):
    """Test the full apply flow."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.todo_path = os.path.join(self.tmpdir, "TODO.md")
        with open(self.todo_path, "w") as f:
            f.write(SAMPLE_TODO)

    def test_no_change_when_no_deps(self):
        changed = gd._apply_dependency_annotations(self.tmpdir, {})
        self.assertFalse(changed)

    def test_applies_deps_to_file(self):
        deps = {11: [8]}
        changed = gd._apply_dependency_annotations(self.tmpdir, deps)
        self.assertTrue(changed)
        with open(self.todo_path) as f:
            content = f.read()
        self.assertIn("depends-on:", content.lower())

    def test_no_change_when_already_annotated(self):
        # Fourth task already has depends-on: 8
        deps = {14: [8]}
        changed = gd._apply_dependency_annotations(self.tmpdir, deps)
        self.assertFalse(changed)


if __name__ == "__main__":
    unittest.main()
