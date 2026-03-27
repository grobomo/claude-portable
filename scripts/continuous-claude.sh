#!/bin/bash
# Continuous Claude runner -- loops through TODO.md tasks via micro-PRs.
# Each iteration: pick one unchecked task, create branch + PR, do the work, merge.
# Designed to run as a background daemon inside the claude-portable container.
#
# Usage:
#   continuous-claude.sh <repo-url> [branch] [workdir]
#
# Environment:
#   CONTINUOUS_CLAUDE_MAX_ERRORS  Max consecutive errors before stopping (default: 3)
#   CONTINUOUS_CLAUDE_COOLDOWN    Seconds between iterations (default: 30)
#   GITHUB_TOKEN                  Required for gh CLI auth
set -euo pipefail

REPO_URL="${1:?Usage: continuous-claude.sh <repo-url> [branch] [workdir]}"
BRANCH="${2:-main}"
WORKDIR="${3:-/workspace/continuous-claude}"
LOG_FILE="/data/continuous-claude.log"
MAX_ERRORS="${CONTINUOUS_CLAUDE_MAX_ERRORS:-3}"
COOLDOWN="${CONTINUOUS_CLAUDE_COOLDOWN:-30}"

# Redirect all output to log file (and stdout for docker logs)
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== Continuous Claude Runner ==="
echo "  Repo:       $REPO_URL"
echo "  Branch:     $BRANCH"
echo "  Workdir:    $WORKDIR"
echo "  Max errors: $MAX_ERRORS"
echo "  Cooldown:   ${COOLDOWN}s"
echo "  Started:    $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

# --- Preflight checks ---
if ! command -v claude >/dev/null 2>&1; then
  echo "FATAL: claude CLI not found on PATH."
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "FATAL: gh CLI not found on PATH."
  exit 1
fi

if ! gh auth status &>/dev/null; then
  echo "FATAL: gh CLI not authenticated. Set GITHUB_TOKEN or run gh auth login."
  exit 1
fi

# --- Clone or update the repo ---
if [ -d "$WORKDIR/.git" ]; then
  echo "[+] Repo already cloned. Pulling latest..."
  cd "$WORKDIR"
  git checkout "$BRANCH" 2>/dev/null || git checkout -b "$BRANCH" "origin/$BRANCH"
  git pull origin "$BRANCH"
else
  echo "[+] Cloning $REPO_URL..."
  mkdir -p "$(dirname "$WORKDIR")"
  git clone --branch "$BRANCH" "$REPO_URL" "$WORKDIR"
  cd "$WORKDIR"
fi

echo "[+] Working directory: $(pwd)"
echo ""

# --- Safety net: merge any leftover PRs from previous runs ---
merge_leftover_prs() {
  echo "[+] Checking for leftover PRs from previous runs..."
  local prs
  prs=$(gh pr list --state open --author "@me" --json number,headRefName \
    --jq '.[] | select(.headRefName | startswith("continuous-claude/")) | .number' 2>/dev/null || echo "")

  if [ -n "$prs" ]; then
    for pr_num in $prs; do
      echo "  Merging leftover PR #${pr_num}..."
      gh pr merge "$pr_num" --squash --delete-branch 2>/dev/null || {
        echo "  WARNING: Could not merge PR #${pr_num}. Closing it."
        gh pr close "$pr_num" --delete-branch 2>/dev/null || true
      }
    done
    # Return to main after merging leftovers
    git checkout "$BRANCH"
    git pull origin "$BRANCH"
  else
    echo "  No leftover PRs found."
  fi
}

# --- Check if all tasks are done ---
all_tasks_done() {
  if [ ! -f "TODO.md" ]; then
    echo "WARNING: No TODO.md found."
    return 0
  fi
  # Check for any unchecked tasks: lines matching "- [ ]"
  if grep -qE '^\s*- \[ \]' TODO.md; then
    return 1  # tasks remaining
  fi
  return 0  # all done
}

# --- Count remaining tasks ---
count_remaining() {
  if [ ! -f "TODO.md" ]; then
    echo "0"
    return
  fi
  grep -cE '^\s*- \[ \]' TODO.md 2>/dev/null || echo "0"
}

# --- Main loop ---
ERROR_COUNT=0
ITERATION=0

merge_leftover_prs

while true; do
  ITERATION=$((ITERATION + 1))
  echo ""
  echo "=== Iteration $ITERATION ($(date -u +%Y-%m-%dT%H:%M:%SZ)) ==="

  # Ensure we're on the base branch with latest
  git checkout "$BRANCH" 2>/dev/null
  git pull origin "$BRANCH" 2>/dev/null

  # Check if all tasks are complete
  REMAINING=$(count_remaining)
  echo "  Tasks remaining: $REMAINING"

  if all_tasks_done; then
    echo ""
    echo "CONTINUOUS_CLAUDE_PROJECT_COMPLETE"
    echo "All tasks in TODO.md are done. Exiting."
    exit 0
  fi

  # Run Claude to pick up and execute the next task
  # The prompt tells Claude to follow the workflow in .claude/rules/continuous-claude.md
  echo "[+] Invoking Claude for next task..."
  CLAUDE_EXIT=0
  claude --print \
    --dangerously-skip-permissions \
    "Read TODO.md and .claude/rules/continuous-claude.md. Pick the FIRST unchecked task. Workflow:
1. Create a new branch from ${BRANCH} (git checkout -b continuous-claude/task-N)
2. Push the branch and open a PR with gh pr create -- title = the PR title specified in TODO.md for that task, body = \"Starting task...\"
3. Do the actual work. Push commits to the branch as you go.
4. When done, mark the task done in TODO.md, commit, push.
5. Merge the PR with: gh pr merge --squash --delete-branch
Then stop. Do NOT proceed to the next task.

CRITICAL: You MUST merge the PR before stopping. If you stop without merging, the task loops forever.
CRITICAL: No secrets, personal paths, or hardcoded credentials in any file. This is a public repo." \
    2>&1 || CLAUDE_EXIT=$?

  if [ "$CLAUDE_EXIT" -ne 0 ]; then
    ERROR_COUNT=$((ERROR_COUNT + 1))
    echo "  ERROR: Claude exited with code $CLAUDE_EXIT (${ERROR_COUNT}/${MAX_ERRORS})"

    if [ "$ERROR_COUNT" -ge "$MAX_ERRORS" ]; then
      echo ""
      echo "FATAL: $MAX_ERRORS consecutive errors. Stopping."
      echo "  Check $LOG_FILE for details."
      exit 1
    fi
  else
    ERROR_COUNT=0  # Reset on success
  fi

  # Safety net: merge any PRs Claude may have left open
  git checkout "$BRANCH" 2>/dev/null || true
  git pull origin "$BRANCH" 2>/dev/null || true
  merge_leftover_prs

  echo "[+] Cooling down for ${COOLDOWN}s..."
  sleep "$COOLDOWN"
done
