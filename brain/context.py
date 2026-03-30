"""
context.py -- Build system prompt from CLAUDE.md + fleet state + recent PRs.

Assembles the system context that gives the brain full architectural awareness
when generating specs and making decisions.
"""

import logging
import os
import subprocess

log = logging.getLogger(__name__)


def _read_file(path: str, max_chars: int = 10000) -> str:
    """Read a file, truncating to max_chars. Returns empty string on error."""
    try:
        with open(path) as f:
            content = f.read(max_chars)
        if len(content) == max_chars:
            content += "\n... (truncated)"
        return content
    except (OSError, IOError):
        return ""


def _run_git(args: list[str], cwd: str, timeout: int = 10) -> str:
    """Run a git command and return stdout. Returns empty string on error."""
    try:
        r = subprocess.run(
            ["git"] + args,
            capture_output=True, text=True, timeout=timeout, cwd=cwd,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def get_recent_prs(repo_dir: str, n: int = 10) -> str:
    """Get recent merged PRs from git log (looks for merge commits or PR references)."""
    log_output = _run_git(
        ["log", "--oneline", f"-{n}", "--grep=PR\\|Merge\\|feat\\|fix"],
        cwd=repo_dir,
    )
    if not log_output:
        log_output = _run_git(["log", "--oneline", f"-{n}"], cwd=repo_dir)
    return log_output


def get_active_branches(repo_dir: str) -> str:
    """Get active feature branches (potential in-progress work)."""
    return _run_git(
        ["branch", "-r", "--sort=-committerdate", "--format=%(refname:short) %(committerdate:relative)"],
        cwd=repo_dir,
    )


def build_system_prompt(repo_dir: str, fleet_summary: str = "",
                         task_summaries: str = "") -> str:
    """Build the full system prompt for the brain conversation.

    Args:
        repo_dir: Path to the target repository (e.g., /workspace/boothapp)
        fleet_summary: Current fleet state from fleet.py
        task_summaries: Summary of recent task outcomes from storage
    """
    sections = []

    sections.append(
        "You are the dispatcher brain for a Claude Code fleet. "
        "Your job is to generate high-quality specifications for incoming tasks, "
        "select the best worker, and learn from task outcomes.\n\n"
        "When generating a spec, write THREE sections:\n"
        "1. spec.md -- Problem, Solution, Components, Success Criteria, Out of Scope\n"
        "2. plan.md -- Technical Approach with specific file paths, Dependency Order, Risks\n"
        "3. tasks.md -- Numbered actionable tasks with checkboxes, ordered by dependency\n\n"
        "Format your response as:\n"
        "===SPEC===\n<spec.md content>\n===PLAN===\n<plan.md content>\n===TASKS===\n<tasks.md content>\n"
    )

    # CLAUDE.md for architectural context
    claude_md_path = os.path.join(repo_dir, "CLAUDE.md")
    claude_md = _read_file(claude_md_path)
    if claude_md:
        sections.append(f"## Project CLAUDE.md\n\n{claude_md}")

    # Recent commits/PRs
    recent_prs = get_recent_prs(repo_dir)
    if recent_prs:
        sections.append(f"## Recent Commits\n\n{recent_prs}")

    # Active branches
    branches = get_active_branches(repo_dir)
    if branches:
        sections.append(f"## Active Branches\n\n{branches}")

    # Fleet state
    if fleet_summary:
        sections.append(f"## Fleet State\n\n{fleet_summary}")

    # Recent task outcomes for learning
    if task_summaries:
        sections.append(f"## Recent Task Outcomes (learn from these)\n\n{task_summaries}")

    return "\n\n---\n\n".join(sections)


def estimate_tokens(text: str) -> int:
    """Rough token estimate (1 token ~ 4 chars for English text)."""
    return len(text) // 4
