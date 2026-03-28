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
INSTANCE_ID="${CLAUDE_PORTABLE_ID:-$(hostname)}"

# Redirect all output to log file (and stdout for docker logs)
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== Continuous Claude Runner ==="
echo "  Instance:   $INSTANCE_ID"
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
  echo "[+] Checking for leftover PRs..."
  local prs
  # Only merge PRs authored by this git identity (not other instances)
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

# --- Get claimed task numbers (open PRs or remote branches from any instance) ---
get_claimed_tasks() {
  # Claimed = has an open PR on a continuous-claude/* branch, or a remote branch exists
  local claimed=""

  # Method 1: open PRs with continuous-claude/ branch prefix
  local pr_branches
  pr_branches=$(gh pr list --state open --json headRefName \
    --jq '.[].headRefName' 2>/dev/null || echo "")
  for b in $pr_branches; do
    if [[ "$b" =~ continuous-claude/task-([0-9]+) ]]; then
      claimed="$claimed ${BASH_REMATCH[1]}"
    fi
  done

  # Method 2: remote branches (catches cases where PR hasn't been created yet)
  local remote_branches
  remote_branches=$(git ls-remote --heads origin 'refs/heads/continuous-claude/task-*' 2>/dev/null \
    | sed 's|.*refs/heads/||' || echo "")
  for b in $remote_branches; do
    if [[ "$b" =~ continuous-claude/task-([0-9]+) ]]; then
      claimed="$claimed ${BASH_REMATCH[1]}"
    fi
  done

  # Deduplicate
  echo "$claimed" | tr ' ' '\n' | sort -un | tr '\n' ' '
}

# --- Find next unclaimed task number ---
find_next_task() {
  if [ ! -f "TODO.md" ]; then
    echo ""
    return
  fi

  local claimed
  claimed=$(get_claimed_tasks)
  echo "  Claimed tasks: ${claimed:-none}"

  # Parse TODO.md: find unchecked tasks, extract task number, skip claimed ones
  local task_num=0
  while IFS= read -r line; do
    task_num=$((task_num + 1))
    # Check if this task number is already claimed
    local is_claimed=false
    for c in $claimed; do
      if [ "$c" = "$task_num" ]; then
        is_claimed=true
        break
      fi
    done
    if [ "$is_claimed" = false ]; then
      echo "$task_num"
      return
    fi
  done < <(grep -nE '^\s*- \[ \]' TODO.md | head -20)

  # All unchecked tasks are claimed by other instances
  echo ""
}

# --- Maintenance mode ---
# Touch /data/.maintenance to pause task pickup. Remove to resume.
# Workers still run, SSH still works, just no new tasks started.
MAINTENANCE_FILE="/data/.maintenance"

check_maintenance() {
  if [ -f "$MAINTENANCE_FILE" ]; then
    return 0  # in maintenance
  fi
  return 1
}

# --- Main loop ---
ERROR_COUNT=0
ITERATION=0

merge_leftover_prs

while true; do
  # Check maintenance mode before each iteration
  if check_maintenance; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [$INSTANCE_ID] Maintenance mode -- paused (touch $MAINTENANCE_FILE to stay paused, rm to resume)"
    sleep "$COOLDOWN"
    continue
  fi

  ITERATION=$((ITERATION + 1))
  echo ""
  echo "=== Iteration $ITERATION [$INSTANCE_ID] ($(date -u +%Y-%m-%dT%H:%M:%SZ)) ==="

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

  # Find next unclaimed task (skip tasks other instances are working on)
  NEXT_TASK=$(find_next_task)
  if [ -z "$NEXT_TASK" ]; then
    echo "  All remaining tasks are claimed by other instances. Waiting..."
    sleep "$COOLDOWN"
    continue
  fi
  echo "  Claiming task #${NEXT_TASK}"

  # Run Claude to execute this specific task
  echo "[+] Invoking Claude for task #${NEXT_TASK}..."
  CLAUDE_EXIT=0
  claude --print \
    --dangerously-skip-permissions \
    "Read TODO.md and .claude/rules/continuous-claude.md.

You are instance '${INSTANCE_ID}'. Pick task #${NEXT_TASK} (the ${NEXT_TASK}th unchecked '- [ ]' item in TODO.md). Workflow:
1. Create branch: git checkout -b continuous-claude/task-${NEXT_TASK}
2. Push branch and open PR: gh pr create --title '<PR title from TODO>' --body 'Task #${NEXT_TASK} by ${INSTANCE_ID}'
3. Do the work. Push commits as you go.
4. Mark task done in TODO.md, commit, push.
5. Merge: gh pr merge --squash --delete-branch
Then STOP. Do NOT proceed to the next task.

CRITICAL: Branch MUST be continuous-claude/task-${NEXT_TASK} exactly. Other instances use the branch name to avoid conflicts.
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

  # Safety net: merge any PRs this instance may have left open
  git checkout "$BRANCH" 2>/dev/null || true
  git pull origin "$BRANCH" 2>/dev/null || true
  merge_leftover_prs

  echo "[+] Cooling down for ${COOLDOWN}s..."
  sleep "$COOLDOWN"
done
