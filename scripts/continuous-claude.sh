#!/bin/bash
# Continuous Claude runner -- loops through TODO.md tasks via micro-PRs.
# Each task runs through a 6-stage TDD pipeline with separate claude invocations:
#   1. RESEARCH  -> /tmp/task-{N}-research.md
#   2. PLAN      -> /tmp/task-{N}-plan.md
#   3. TESTS     -> write failing tests, commit to branch
#   4. IMPLEMENT -> write code until tests pass
#   5. VERIFY    -> full suite + lint + secret check
#   6. PR        -> push, create PR, mark done, merge
# Each stage is retried independently on failure.
#
# Usage:
#   continuous-claude.sh <repo-url> [branch] [workdir]
#
# Environment:
#   CONTINUOUS_CLAUDE_MAX_ERRORS  Max consecutive errors before stopping (default: 3)
#   CONTINUOUS_CLAUDE_COOLDOWN    Seconds between iterations (default: 30)
#   CONTINUOUS_CLAUDE_MAX_RETRIES Max per-stage retries before aborting task (default: 2)
#   GITHUB_TOKEN                  Required for gh CLI auth
set -euo pipefail

REPO_URL="${1:?Usage: continuous-claude.sh <repo-url> [branch] [workdir]}"
BRANCH="${2:-main}"
WORKDIR="${3:-/workspace/continuous-claude}"
LOG_FILE="/data/continuous-claude.log"
MAX_ERRORS="${CONTINUOUS_CLAUDE_MAX_ERRORS:-3}"
COOLDOWN="${CONTINUOUS_CLAUDE_COOLDOWN:-30}"
MAX_RETRIES="${CONTINUOUS_CLAUDE_MAX_RETRIES:-2}"
INSTANCE_ID="${CLAUDE_PORTABLE_ID:-$(hostname)}"

# Redirect all output to log file (and stdout for docker logs)
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== Continuous Claude Runner (TDD Pipeline) ==="
echo "  Instance:   $INSTANCE_ID"
echo "  Repo:       $REPO_URL"
echo "  Branch:     $BRANCH"
echo "  Workdir:    $WORKDIR"
echo "  Max errors: $MAX_ERRORS"
echo "  Cooldown:   ${COOLDOWN}s"
echo "  Max retries/stage: $MAX_RETRIES"
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
  if grep -qE '^\s*- \[ \]' TODO.md; then
    return 1
  fi
  return 0
}

# --- Count remaining tasks ---
count_remaining() {
  if [ ! -f "TODO.md" ]; then
    echo "0"
    return
  fi
  grep -cE '^\s*- \[ \]' TODO.md 2>/dev/null || echo "0"
}

# --- Get claimed task numbers ---
get_claimed_tasks() {
  local claimed=""

  local pr_branches
  pr_branches=$(gh pr list --state open --json headRefName \
    --jq '.[].headRefName' 2>/dev/null || echo "")
  for b in $pr_branches; do
    if [[ "$b" =~ continuous-claude/task-([0-9]+) ]]; then
      claimed="$claimed ${BASH_REMATCH[1]}"
    fi
  done

  local remote_branches
  remote_branches=$(git ls-remote --heads origin 'refs/heads/continuous-claude/task-*' 2>/dev/null \
    | sed 's|.*refs/heads/||' || echo "")
  for b in $remote_branches; do
    if [[ "$b" =~ continuous-claude/task-([0-9]+) ]]; then
      claimed="$claimed ${BASH_REMATCH[1]}"
    fi
  done

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

  local task_num=0
  while IFS= read -r line; do
    task_num=$((task_num + 1))
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

  echo ""
}

# --- Get task description for a task number ---
get_task_description() {
  local task_num="$1"
  # Find the Nth unchecked task in TODO.md (1-indexed)
  grep -E '^\s*- \[ \]' TODO.md | sed -n "${task_num}p" | sed 's/^\s*- \[ \] //'
}

# --- Get PR title for a task ---
get_pr_title() {
  local task_num="$1"
  # Find the Nth unchecked task block and extract "PR title:" line
  local task_line
  task_line=$(grep -nE '^\s*- \[ \]' TODO.md | sed -n "${task_num}p" | cut -d: -f1)
  if [ -z "$task_line" ]; then
    echo "feat: task ${task_num}"
    return
  fi
  # Look at the line after the task for "PR title:"
  local next_line=$((task_line + 1))
  local pr_title
  pr_title=$(sed -n "${next_line}p" TODO.md | grep -oP '(?<=PR title: ").*(?=")' || echo "")
  if [ -z "$pr_title" ]; then
    # Try without quotes
    pr_title=$(sed -n "${next_line}p" TODO.md | grep -oP '(?<=PR title: ).*' | tr -d '"' || echo "")
  fi
  echo "${pr_title:-feat: task ${task_num}}"
}

# --- Run a single pipeline stage ---
# Returns 0 on success, 1 on failure
run_stage() {
  local stage_name="$1"
  local stage_num="$2"
  local prompt="$3"
  local stage_log="$4"

  local start_time
  start_time=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  echo "  [Stage ${stage_num}: ${stage_name}] Starting at ${start_time}"

  # Update stage log: mark stage as started
  python3 -c "
import json, os, sys
path = sys.argv[1]
data = {}
if os.path.exists(path):
    with open(path) as f:
        data = json.load(f)
data['${stage_name}'] = {'status': 'running', 'start': '${start_time}'}
with open(path, 'w') as f:
    json.dump(data, f, indent=2)
" "$stage_log" 2>/dev/null || true

  local claude_exit=0
  claude --print \
    --dangerously-skip-permissions \
    "$prompt" \
    2>&1 || claude_exit=$?

  local end_time
  end_time=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  if [ "$claude_exit" -ne 0 ]; then
    echo "  [Stage ${stage_num}: ${stage_name}] FAILED (exit ${claude_exit}) at ${end_time}"
    python3 -c "
import json, os, sys
path = sys.argv[1]
data = {}
if os.path.exists(path):
    with open(path) as f:
        data = json.load(f)
data['${stage_name}'] = {'status': 'failed', 'start': '${start_time}', 'end': '${end_time}', 'exit_code': ${claude_exit}}
with open(path, 'w') as f:
    json.dump(data, f, indent=2)
" "$stage_log" 2>/dev/null || true
    return 1
  fi

  echo "  [Stage ${stage_num}: ${stage_name}] PASSED at ${end_time}"
  python3 -c "
import json, os, sys
path = sys.argv[1]
data = {}
if os.path.exists(path):
    with open(path) as f:
        data = json.load(f)
data['${stage_name}'] = {'status': 'passed', 'start': '${start_time}', 'end': '${end_time}'}
with open(path, 'w') as f:
    json.dump(data, f, indent=2)
" "$stage_log" 2>/dev/null || true
  return 0
}

# --- Run stage with retries ---
run_stage_with_retry() {
  local stage_name="$1"
  local stage_num="$2"
  local prompt="$3"
  local stage_log="$4"
  local max_retries="${5:-$MAX_RETRIES}"

  local attempt=0
  while [ "$attempt" -le "$max_retries" ]; do
    if [ "$attempt" -gt 0 ]; then
      echo "  [Stage ${stage_num}: ${stage_name}] Retry ${attempt}/${max_retries}..."
    fi
    if run_stage "$stage_name" "$stage_num" "$prompt" "$stage_log"; then
      return 0
    fi
    attempt=$((attempt + 1))
  done

  echo "  [Stage ${stage_num}: ${stage_name}] EXHAUSTED all retries. Aborting task."
  return 1
}

# --- Execute full TDD pipeline for a task ---
run_pipeline() {
  local task_num="$1"
  local task_desc="$2"
  local pr_title="$3"
  local branch_name="continuous-claude/task-${task_num}"

  local research_file="/tmp/task-${task_num}-research.md"
  local plan_file="/tmp/task-${task_num}-plan.md"
  local stage_log="/data/task-${task_num}-stages.json"

  echo ""
  echo "--- TDD Pipeline: Task #${task_num} ---"
  echo "  Description: ${task_desc}"
  echo "  PR title:    ${pr_title}"
  echo "  Branch:      ${branch_name}"
  echo "  Stage log:   ${stage_log}"
  echo ""

  # Initialize stage log
  echo '{}' > "$stage_log"

  # Create and push branch
  git checkout -b "$branch_name"
  git push -u origin "$branch_name"

  # ===== STAGE 1: RESEARCH =====
  local research_prompt="You are instance '${INSTANCE_ID}' working on task #${task_num}.

TASK: ${task_desc}

STAGE: RESEARCH
Your job in this stage is ONLY to research. Do NOT write any implementation code yet.

1. Read all existing relevant files in the repo that relate to this task (use Read and Grep tools).
2. Search for existing patterns, best practices, and similar implementations in the codebase.
3. Write a comprehensive research summary to '${research_file}' covering:
   - What files will need to be created or modified
   - What the existing code does that is related
   - What patterns/conventions are used in this codebase
   - Any gotchas, edge cases, or constraints to be aware of
   - What the tests should verify

Output ONLY the research file. No code changes yet.
CRITICAL: Write the research summary to ${research_file} using the Write tool."

  run_stage_with_retry "RESEARCH" "1" "$research_prompt" "$stage_log" || return 1

  # ===== STAGE 2: PLAN =====
  local plan_prompt="You are instance '${INSTANCE_ID}' working on task #${task_num}.

TASK: ${task_desc}

STAGE: PLAN
Research summary is at: ${research_file}
Read it first, then create an implementation plan.

Write a detailed plan to '${plan_file}' that includes:
1. Exact list of files to create or modify (with paths)
2. What each file should contain (high-level, not code yet)
3. What tests to write first (TDD - tests before implementation)
4. What each test should verify (specific behaviors, edge cases)
5. Implementation order (which files to write first)

Output ONLY the plan file. No code changes yet.
CRITICAL: Write the plan to ${plan_file} using the Write tool."

  run_stage_with_retry "PLAN" "2" "$plan_prompt" "$stage_log" || return 1

  # ===== STAGE 3: TESTS FIRST =====
  local tests_prompt="You are instance '${INSTANCE_ID}' working on task #${task_num}.

TASK: ${task_desc}
BRANCH: ${branch_name}

STAGE: TESTS FIRST
You are on branch ${branch_name}. Read the plan at ${plan_file}.

Write the tests BEFORE writing any implementation code:
1. Create test files as described in the plan
2. Tests should clearly define the expected behavior
3. Run the tests -- they MUST FAIL at this point (no implementation exists yet)
4. If tests pass when they should fail, the tests are wrong -- fix them
5. Commit the failing tests to the branch with message: 'test: add failing tests for task ${task_num}'
   Use: git add <test files> && git commit -m 'test: add failing tests for task ${task_num}'

CRITICAL: Tests must be committed to branch ${branch_name}
CRITICAL: Do NOT write any implementation code in this stage -- only tests
CRITICAL: Verify tests fail before committing (this confirms tests are actually testing something)"

  run_stage_with_retry "TESTS" "3" "$tests_prompt" "$stage_log" || return 1

  # ===== STAGE 4: IMPLEMENT =====
  local implement_prompt="You are instance '${INSTANCE_ID}' working on task #${task_num}.

TASK: ${task_desc}
BRANCH: ${branch_name}

STAGE: IMPLEMENT
Tests are already written and failing (see previous commit). Now write the implementation.

Read the plan at ${plan_file} and the failing tests to understand what to implement.

1. Write the minimum code needed to make the failing tests pass
2. Run tests after each significant change
3. Iterate until ALL tests pass
4. Commit the implementation with message: 'feat: implement task ${task_num}'
   Use: git add <implementation files> && git commit -m 'feat: implement task ${task_num}'

CRITICAL: Do NOT change the tests -- only add implementation code
CRITICAL: ALL tests must pass before committing
CRITICAL: Check for secrets before committing: grep -rn 'password\|secret\|token\|key' --include='*.sh' --include='*.js' --include='*.py' (remove any real credentials)"

  run_stage_with_retry "IMPLEMENT" "4" "$implement_prompt" "$stage_log" || return 1

  # ===== STAGE 5: VERIFY =====
  local verify_prompt="You are instance '${INSTANCE_ID}' working on task #${task_num}.

TASK: ${task_desc}
BRANCH: ${branch_name}

STAGE: VERIFY
Run the full verification suite before pushing:

1. Run all tests -- ALL must pass
2. Check shell script syntax: bash -n <script> for any .sh files you modified
3. Check for secrets or personal paths:
   grep -rn 'C:/Users/' . --exclude-dir=.git --include='*.sh' --include='*.json' --include='*.js'
   (should return nothing)
4. Check no hardcoded tokens/keys were added
5. Verify line endings are LF (not CRLF) for shell scripts

If anything fails, fix it and re-run. Commit any fixes with: 'fix: verification fixes for task ${task_num}'

When ALL checks pass, output: VERIFY_PASSED
If you cannot fix all issues after attempting, output: VERIFY_FAILED with details."

  run_stage_with_retry "VERIFY" "5" "$verify_prompt" "$stage_log" || return 1

  # ===== STAGE 6: PR =====
  local pr_prompt="You are instance '${INSTANCE_ID}' working on task #${task_num}.

TASK: ${task_desc}
BRANCH: ${branch_name}
PR TITLE: ${pr_title}

STAGE: PR
All tests pass and verification is complete. Now finalize the task.

1. Push all commits to the branch:
   git push origin ${branch_name}

2. Create a PR (or update the existing one):
   gh pr create --title '${pr_title}' --body 'Task #${task_num} by ${INSTANCE_ID}

TDD pipeline stages completed:
- Research: ${research_file}
- Plan: ${plan_file}
- Tests written first (failing), then implementation added
- All tests passing, verification complete'

   (If PR already exists from branch push, use: gh pr edit --body '...' instead)

3. Mark the task as done in TODO.md:
   - Find task #${task_num} (the ${task_num}th unchecked '- [ ]' item)
   - Change '- [ ]' to '- [x]'
   - git add TODO.md && git commit -m 'chore: mark task ${task_num} complete'
   - git push origin ${branch_name}

4. Merge the PR:
   gh pr merge --squash --delete-branch

CRITICAL: You MUST merge the PR. If gh pr merge fails, try: gh pr merge --squash --delete-branch --admin
CRITICAL: After merge, confirm with: git checkout ${BRANCH} && git pull origin ${BRANCH}"

  run_stage_with_retry "PR" "6" "$pr_prompt" "$stage_log" || return 1

  echo ""
  echo "--- Pipeline complete for task #${task_num} ---"
  return 0
}

# --- Maintenance mode ---
MAINTENANCE_FILE="/data/.maintenance"

check_maintenance() {
  if [ -f "$MAINTENANCE_FILE" ]; then
    return 0
  fi
  return 1
}

# --- Main loop ---
ERROR_COUNT=0
ITERATION=0

merge_leftover_prs

while true; do
  if check_maintenance; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [$INSTANCE_ID] Maintenance mode -- paused"
    sleep "$COOLDOWN"
    continue
  fi

  ITERATION=$((ITERATION + 1))
  echo ""
  echo "=== Iteration $ITERATION [$INSTANCE_ID] ($(date -u +%Y-%m-%dT%H:%M:%SZ)) ==="

  # Ensure we're on the base branch with latest
  git checkout "$BRANCH" 2>/dev/null
  git pull origin "$BRANCH" 2>/dev/null

  REMAINING=$(count_remaining)
  echo "  Tasks remaining: $REMAINING"

  if all_tasks_done; then
    echo ""
    echo "CONTINUOUS_CLAUDE_PROJECT_COMPLETE"
    echo "All tasks in TODO.md are done. Exiting."
    exit 0
  fi

  NEXT_TASK=$(find_next_task)
  if [ -z "$NEXT_TASK" ]; then
    echo "  All remaining tasks are claimed by other instances. Waiting..."
    sleep "$COOLDOWN"
    continue
  fi
  echo "  Claiming task #${NEXT_TASK}"

  # Get task details
  TASK_DESC=$(get_task_description "$NEXT_TASK")
  TASK_PR_TITLE=$(get_pr_title "$NEXT_TASK")
  echo "  Task:     $TASK_DESC"
  echo "  PR title: $TASK_PR_TITLE"

  # Run the TDD pipeline
  PIPELINE_EXIT=0
  run_pipeline "$NEXT_TASK" "$TASK_DESC" "$TASK_PR_TITLE" || PIPELINE_EXIT=$?

  if [ "$PIPELINE_EXIT" -ne 0 ]; then
    ERROR_COUNT=$((ERROR_COUNT + 1))
    echo "  ERROR: Pipeline failed for task #${NEXT_TASK} (${ERROR_COUNT}/${MAX_ERRORS})"

    # Clean up: get back to main branch
    git checkout "$BRANCH" 2>/dev/null || true
    git pull origin "$BRANCH" 2>/dev/null || true

    if [ "$ERROR_COUNT" -ge "$MAX_ERRORS" ]; then
      echo ""
      echo "FATAL: $MAX_ERRORS consecutive errors. Stopping."
      exit 1
    fi
  else
    ERROR_COUNT=0
  fi

  # Safety net: merge any leftover PRs
  git checkout "$BRANCH" 2>/dev/null || true
  git pull origin "$BRANCH" 2>/dev/null || true
  merge_leftover_prs

  echo "[+] Cooling down for ${COOLDOWN}s..."
  sleep "$COOLDOWN"
done
