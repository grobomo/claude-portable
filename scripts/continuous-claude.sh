#!/bin/bash
# Continuous Claude runner -- loops through TODO.md tasks via micro-PRs.
# Each task runs through a 7-stage TDD pipeline with separate claude invocations:
#   1. RESEARCH  -> /tmp/task-{N}-research.md
#   2. REVIEW    -> /tmp/task-{N}-review.md (codebase audit for duplicates/dead code)
#   3. PLAN      -> /tmp/task-{N}-plan.md
#   4. TESTS     -> write failing tests, commit to branch
#   5. IMPLEMENT -> write code until tests pass
#   6. VERIFY    -> full suite + lint + secret check
#   7. PR        -> push, create PR, mark done, merge
# Each stage is retried independently on failure.
#
# Usage:
#   continuous-claude.sh <repo-url> [branch] [workdir]
#
# Environment:
#   CONTINUOUS_CLAUDE_MAX_ERRORS  Max consecutive errors before stopping (default: 3)
#   CONTINUOUS_CLAUDE_COOLDOWN    Seconds between iterations (default: 30)
#   CONTINUOUS_CLAUDE_MAX_RETRIES Max per-stage retries before aborting task (default: 2)
#   CONTINUOUS_CLAUDE_IDLE_TIMEOUT  Minutes idle before reporting to dispatcher for scale-down (default: 30)
#   DISPATCHER_URL                Dispatcher health endpoint base URL (optional, e.g. http://10.0.0.1:8080)
#   GITHUB_TOKEN                  Required for gh CLI auth
set -euo pipefail

REPO_URL="${1:?Usage: continuous-claude.sh <repo-url> [branch] [workdir]}"
BRANCH="${2:-main}"
WORKDIR="${3:-/workspace/continuous-claude}"
LOG_FILE="/data/continuous-claude.log"
MAX_ERRORS="${CONTINUOUS_CLAUDE_MAX_ERRORS:-3}"
COOLDOWN="${CONTINUOUS_CLAUDE_COOLDOWN:-30}"
MAX_RETRIES="${CONTINUOUS_CLAUDE_MAX_RETRIES:-2}"
IDLE_TIMEOUT="${CONTINUOUS_CLAUDE_IDLE_TIMEOUT:-30}"  # minutes
INSTANCE_ID="${CLAUDE_PORTABLE_ID:-$(hostname)}"
DISPATCHER_URL="${DISPATCHER_URL:-}"

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

# --- Check and clear API control flags ---
check_api_flags() {
  # Force pull flag (set by worker-health.py POST /pull)
  if [ -f /data/.force-pull ]; then
    echo "[+] Force-pull requested via API. Pulling..."
    rm -f /data/.force-pull
    git pull origin "$BRANCH" || true
  fi
  # Interrupt flag (set by worker-health.py POST /interrupt)
  if [ -f /data/.interrupt ]; then
    echo "[!] Interrupt requested via API. Aborting current task."
    rm -f /data/.interrupt
    return 1
  fi
  return 0
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

# --- Check if a task is blocked by unmet dependencies ---
# Returns 0 if blocked, 1 if not blocked
is_task_blocked() {
  local task_line_num="$1"  # actual line number in TODO.md
  if [ -z "$task_line_num" ]; then
    return 1
  fi

  # Look at sub-lines after this task for "depends-on:" annotations
  local deps=""
  local next=$((task_line_num + 1))
  local total_lines
  total_lines=$(wc -l < TODO.md)

  while [ "$next" -le "$total_lines" ]; do
    local sub
    sub=$(sed -n "${next}p" TODO.md)
    # Stop at next task item
    if echo "$sub" | grep -qE '^\s*- \['; then
      break
    fi
    # Stop at non-indented non-blank line
    if [ -n "$sub" ] && ! echo "$sub" | grep -qE '^\s'; then
      break
    fi
    # Check for depends-on
    if echo "$sub" | grep -iqE '^\s*-\s+depends-on:'; then
      local dep_refs
      dep_refs=$(echo "$sub" | sed 's/.*depends-on:\s*//i' | tr ',' ' ')
      for ref in $dep_refs; do
        local dep_line
        dep_line=$(echo "$ref" | grep -oE '[0-9]+' || echo "")
        if [ -n "$dep_line" ]; then
          # Check if that line is checked in TODO.md
          local dep_content
          dep_content=$(sed -n "${dep_line}p" TODO.md 2>/dev/null || echo "")
          if echo "$dep_content" | grep -qE '^\s*- \[ \]'; then
            echo "  Task at line ${task_line_num} blocked by unchecked dependency at line ${dep_line}"
            return 0  # blocked
          fi
        fi
      done
    fi
    next=$((next + 1))
  done

  return 1  # not blocked
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
    if [ "$is_claimed" = true ]; then
      continue
    fi

    # Check dependencies — get the actual line number from TODO.md
    local actual_line
    actual_line=$(echo "$line" | cut -d: -f1)
    if is_task_blocked "$actual_line"; then
      continue
    fi

    echo "$task_num"
    return
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

# --- Detect the test framework used in a repo ---
# Outputs a multi-line string: FRAMEWORK, RUN_CMD, NOTES
# Usage: read -r FRAMEWORK RUN_CMD NOTES < <(detect_test_framework /path/to/repo)
detect_test_framework() {
  local repo_dir="${1:-.}"
  local framework="bash"
  local run_cmd="bash -n"
  local notes="No test framework detected; using bash -n for shell script syntax checking"

  # Node/JS: check package.json for test runner
  if [ -f "$repo_dir/package.json" ]; then
    local pkg_content
    pkg_content=$(cat "$repo_dir/package.json" 2>/dev/null || echo "")
    local test_script
    test_script=$(echo "$pkg_content" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(d.get('scripts',{}).get('test',''))
" 2>/dev/null || echo "")

    if echo "$pkg_content" | grep -qE '"(jest|@jest/core)"'; then
      framework="jest"
      run_cmd="npx jest"
      notes="Detected Jest (package.json devDependencies)"
    elif echo "$pkg_content" | grep -q '"vitest"'; then
      framework="vitest"
      run_cmd="npx vitest run"
      notes="Detected Vitest (package.json devDependencies)"
    elif echo "$pkg_content" | grep -q '"mocha"'; then
      framework="mocha"
      run_cmd="npx mocha"
      notes="Detected Mocha (package.json devDependencies)"
    elif echo "$pkg_content" | grep -q '"ava"'; then
      framework="ava"
      run_cmd="npx ava"
      notes="Detected AVA (package.json devDependencies)"
    elif echo "$pkg_content" | grep -q '"tap"'; then
      framework="tap"
      run_cmd="npx tap"
      notes="Detected node-tap (package.json devDependencies)"
    elif [ -n "$test_script" ] && [ "$test_script" != "echo \"Error: no test specified\" && exit 1" ]; then
      framework="npm-test"
      run_cmd="npm test"
      notes="Detected npm test script: $test_script"
    fi

  # Python: check for pytest config or imports
  elif [ -f "$repo_dir/pyproject.toml" ] || [ -f "$repo_dir/setup.cfg" ] || [ -f "$repo_dir/pytest.ini" ]; then
    if grep -qE '^\[tool.pytest|^\[pytest\]' "$repo_dir/pyproject.toml" "$repo_dir/setup.cfg" "$repo_dir/pytest.ini" 2>/dev/null; then
      framework="pytest"
      run_cmd="python3 -m pytest"
      notes="Detected pytest (pyproject.toml/setup.cfg/pytest.ini)"
    else
      framework="pytest"
      run_cmd="python3 -m pytest"
      notes="Detected Python project; defaulting to pytest"
    fi
  elif [ -f "$repo_dir/requirements.txt" ] && grep -qi "pytest" "$repo_dir/requirements.txt" 2>/dev/null; then
    framework="pytest"
    run_cmd="python3 -m pytest"
    notes="Detected pytest (requirements.txt)"

  # Go: check for go.mod
  elif [ -f "$repo_dir/go.mod" ]; then
    framework="go-test"
    run_cmd="go test ./..."
    notes="Detected Go module (go.mod)"

  # Ruby: check for Gemfile with rspec or minitest
  elif [ -f "$repo_dir/Gemfile" ]; then
    if grep -q "rspec" "$repo_dir/Gemfile" 2>/dev/null; then
      framework="rspec"
      run_cmd="bundle exec rspec"
      notes="Detected RSpec (Gemfile)"
    else
      framework="minitest"
      run_cmd="bundle exec rake test"
      notes="Detected Ruby project; defaulting to rake test"
    fi

  # Makefile: check for 'test' target
  elif [ -f "$repo_dir/Makefile" ] && grep -qE '^test[[:space:]]*:' "$repo_dir/Makefile" 2>/dev/null; then
    framework="make"
    run_cmd="make test"
    notes="Detected Makefile with 'test' target"

  # Shell scripts: bash -n for syntax + test scripts
  elif find "$repo_dir" -maxdepth 3 -name "*.test.sh" -o -name "test_*.sh" 2>/dev/null | grep -q .; then
    framework="bash"
    run_cmd="bash"
    notes="Detected shell test scripts (*.test.sh / test_*.sh); run each with 'bash <script>'"

  else
    # Default: bash -n for any .sh files in repo
    framework="bash"
    run_cmd="bash -n"
    notes="No test framework detected; using bash -n for shell script syntax checking. Write assertion scripts if integration tests are needed."
  fi

  echo "$framework"
  echo "$run_cmd"
  echo "$notes"
}

# --- Execute full TDD pipeline for a task ---
run_pipeline() {
  local task_num="$1"
  local task_desc="$2"
  local pr_title="$3"
  local branch_name="continuous-claude/task-${task_num}"

  local research_file="/tmp/task-${task_num}-research.md"
  local review_file="/tmp/task-${task_num}-review.md"
  local plan_file="/tmp/task-${task_num}-plan.md"
  local stage_log="/data/task-${task_num}-stages.json"

  # Detect test framework for this repo
  local fw_lines
  mapfile -t fw_lines < <(detect_test_framework "$(pwd)")
  local test_framework="${fw_lines[0]:-bash}"
  local test_run_cmd="${fw_lines[1]:-bash -n}"
  local test_framework_notes="${fw_lines[2]:-No test framework detected}"

  echo ""
  echo "--- TDD Pipeline: Task #${task_num} ---"
  echo "  Description:      ${task_desc}"
  echo "  PR title:         ${pr_title}"
  echo "  Branch:           ${branch_name}"
  echo "  Stage log:        ${stage_log}"
  echo "  Test framework:   ${test_framework} (${test_run_cmd})"
  echo "  Framework notes:  ${test_framework_notes}"
  echo ""

  # Initialize stage log with task metadata
  python3 -c "
import json, sys
path, task_num, instance, branch, started = sys.argv[1:]
data = {
    '_meta': {
        'task_num': int(task_num),
        'instance': instance,
        'branch': branch,
        'started': started,
        'status': 'running'
    }
}
with open(path, 'w') as f:
    json.dump(data, f, indent=2)
" "$stage_log" "$task_num" "$INSTANCE_ID" "$branch_name" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" 2>/dev/null \
    || echo '{"_meta": {}}' > "$stage_log"

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

  # ===== STAGE 2: REVIEW =====
  local review_prompt="You are instance '${INSTANCE_ID}' working on task #${task_num}.

TASK: ${task_desc}

STAGE: REVIEW (mandatory codebase audit)
Research summary is at: ${research_file}
Read it first.

Your job is to audit the ENTIRE codebase for issues that affect this task BEFORE any planning or coding begins. You must:

1. Read ALL files in the repo that relate to this task (use Grep and Glob to find them).
2. Identify and document in '${review_file}':

   ## Existing Implementations
   Code that ALREADY does what this task asks (partially or fully). If found, note the file and function.
   If the task is already fully implemented, write: VERDICT: ALREADY_DONE

   ## Dead Code
   Code from previous tasks/PRs that is no longer used or referenced. List file:line for each.

   ## Conflicting Implementations
   Multiple implementations of the same concept (e.g. two dispatch systems, duplicate helpers).
   Note which should be kept and which removed.

   ## Refactoring Needed
   Code that must be changed to cleanly accommodate the new feature. If >3 files need refactoring,
   write: VERDICT: REFACTOR_FIRST

   ## Verdict
   One of:
   - PROCEED: codebase is clean, task can be implemented directly
   - ALREADY_DONE: task is already implemented, skip it
   - REFACTOR_FIRST: clean up required before new code (list the refactoring steps)

CRITICAL: Write the review to ${review_file} using the Write tool.
CRITICAL: Be thorough -- read actual file contents, don't guess from filenames.
CRITICAL: The verdict MUST be one of: PROCEED, ALREADY_DONE, REFACTOR_FIRST"

  run_stage_with_retry "REVIEW" "2" "$review_prompt" "$stage_log" || return 1

  # Check review verdict -- skip task if already done
  local review_verdict=""
  if [ -f "$review_file" ]; then
    review_verdict=$(grep -oE 'VERDICT: (PROCEED|ALREADY_DONE|REFACTOR_FIRST)' "$review_file" | tail -1 | sed 's/VERDICT: //' || echo "")
  fi
  if [ "$review_verdict" = "ALREADY_DONE" ]; then
    echo "  [REVIEW] Task is already implemented. Skipping."
    python3 -c "
import re, sys
task_num = int(sys.argv[1])
with open('TODO.md') as f:
    lines = f.readlines()
count = 0
for i, line in enumerate(lines):
    if re.match(r'\s*- \[ \]', line):
        count += 1
        if count == task_num:
            lines[i] = line.replace('- [ ]', '- [x]', 1)
            break
with open('TODO.md', 'w') as f:
    f.writelines(lines)
" "$task_num" 2>/dev/null || true
    git add TODO.md 2>/dev/null && git commit -m "chore: skip task ${task_num} (already implemented per review)" 2>/dev/null && git push origin "$BRANCH" 2>/dev/null || true
    git branch -D "$branch_name" 2>/dev/null || true
    git push origin --delete "$branch_name" 2>/dev/null || true
    return 0
  fi

  # ===== STAGE 3: PLAN =====
  local plan_prompt="You are instance '${INSTANCE_ID}' working on task #${task_num}.

TASK: ${task_desc}

STAGE: PLAN
Research summary is at: ${research_file}
Code review is at: ${review_file}
Read BOTH files first, then create an implementation plan.

Write a detailed plan to '${plan_file}' that includes:
1. Exact list of files to create or modify (with paths)
2. What each file should contain (high-level, not code yet)
3. What tests to write first (TDD - tests before implementation)
4. What each test should verify (specific behaviors, edge cases)
5. Implementation order (which files to write first)
6. Any refactoring from the review that must happen first

If the review verdict was REFACTOR_FIRST, the plan must start with refactoring steps
(remove dead code, consolidate duplicates) BEFORE adding new functionality.

Output ONLY the plan file. No code changes yet.
CRITICAL: Write the plan to ${plan_file} using the Write tool."

  run_stage_with_retry "PLAN" "3" "$plan_prompt" "$stage_log" || return 1

  # ===== STAGE 4: TESTS FIRST =====
  local tests_prompt="You are instance '${INSTANCE_ID}' working on task #${task_num}.

TASK: ${task_desc}
BRANCH: ${branch_name}

TEST FRAMEWORK: ${test_framework}
TEST COMMAND: ${test_run_cmd}
FRAMEWORK NOTES: ${test_framework_notes}

STAGE: TESTS FIRST
You are on branch ${branch_name}. Read the plan at ${plan_file}.

Write the tests BEFORE writing any implementation code:
1. Create test files as described in the plan, using the detected test framework above
2. Tests should clearly define the expected behavior
3. Run the tests using '${test_run_cmd}' -- they MUST FAIL at this point (no implementation exists yet)
4. If tests pass when they should fail, the tests are wrong -- fix them
5. Commit the failing tests to the branch with message: 'test: add failing tests for task ${task_num}'
   Use: git add <test files> && git commit -m 'test: add failing tests for task ${task_num}'

CRITICAL: Tests must be committed to branch ${branch_name}
CRITICAL: Do NOT write any implementation code in this stage -- only tests
CRITICAL: Verify tests fail before committing (this confirms tests are actually testing something)
CRITICAL: Use the detected framework '${test_framework}'. If no framework was detected (bash -n), write a test shell script with explicit assertions that exit non-zero on failure."

  run_stage_with_retry "TESTS" "4" "$tests_prompt" "$stage_log" || return 1

  # ===== STAGE 5: IMPLEMENT =====
  local implement_prompt="You are instance '${INSTANCE_ID}' working on task #${task_num}.

TASK: ${task_desc}
BRANCH: ${branch_name}

TEST FRAMEWORK: ${test_framework}
TEST COMMAND: ${test_run_cmd}

STAGE: IMPLEMENT
Tests are already written and failing (see previous commit). Now write the implementation.

Read the plan at ${plan_file} and the failing tests to understand what to implement.

1. Write the minimum code needed to make the failing tests pass
2. Run tests after each significant change using: ${test_run_cmd}
3. Iterate until ALL tests pass
4. Commit the implementation with message: 'feat: implement task ${task_num}'
   Use: git add <implementation files> && git commit -m 'feat: implement task ${task_num}'

CRITICAL: Do NOT change the tests -- only add implementation code
CRITICAL: ALL tests must pass before committing (run: ${test_run_cmd})
CRITICAL: Check for secrets before committing: grep -rn 'password\|secret\|token\|key' --include='*.sh' --include='*.js' --include='*.py' (remove any real credentials)"

  run_stage_with_retry "IMPLEMENT" "5" "$implement_prompt" "$stage_log" || return 1

  # ===== STAGE 6: VERIFY =====
  local verify_prompt="You are instance '${INSTANCE_ID}' working on task #${task_num}.

TASK: ${task_desc}
BRANCH: ${branch_name}

TEST FRAMEWORK: ${test_framework}
TEST COMMAND: ${test_run_cmd}

STAGE: VERIFY
Run the full verification suite before pushing:

1. Run all tests using '${test_run_cmd}' -- ALL must pass
2. Check shell script syntax: bash -n <script> for any .sh files you modified
3. Check for secrets or personal paths:
   grep -rn 'C:/Users/' . --exclude-dir=.git --include='*.sh' --include='*.json' --include='*.js'
   (should return nothing)
4. Check no hardcoded tokens/keys were added
5. Verify line endings are LF (not CRLF) for shell scripts

If anything fails, fix it and re-run. Commit any fixes with: 'fix: verification fixes for task ${task_num}'

When ALL checks pass, output: VERIFY_PASSED
If you cannot fix all issues after attempting, output: VERIFY_FAILED with details."

  run_stage_with_retry "VERIFY" "6" "$verify_prompt" "$stage_log" || return 1

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

  run_stage_with_retry "PR" "7" "$pr_prompt" "$stage_log" || return 1

  # Update meta: pipeline complete
  python3 -c "
import json, os, sys
path = sys.argv[1]
data = {}
if os.path.exists(path):
    with open(path) as f:
        data = json.load(f)
if '_meta' in data:
    data['_meta']['status'] = 'complete'
    data['_meta']['ended'] = sys.argv[2]
with open(path, 'w') as f:
    json.dump(data, f, indent=2)
" "$stage_log" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" 2>/dev/null || true

  echo ""
  echo "--- Pipeline complete for task #${task_num} ---"
  return 0
}

# --- Register this worker with the dispatcher ---
register_with_dispatcher() {
  if [ -z "$DISPATCHER_URL" ]; then
    return 0
  fi

  # Try to get the IP address from EC2 metadata (IMDSv2) first, fall back to hostname
  local ip=""
  local token
  token=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" \
    --connect-timeout 2 2>/dev/null || echo "")
  if [ -n "$token" ]; then
    ip=$(curl -s -H "X-aws-ec2-metadata-token: $token" \
      "http://169.254.169.254/latest/meta-data/local-ipv4" \
      --connect-timeout 2 2>/dev/null || echo "")
  fi
  if [ -z "$ip" ]; then
    ip=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "unknown")
  fi

  local payload
  payload=$(printf '{"worker_id":"%s","ip":"%s","role":"worker","capabilities":["continuous-claude","tdd-pipeline"]}' \
    "$INSTANCE_ID" "$ip")

  if curl -s -f -X POST \
      -H "Content-Type: application/json" \
      -d "$payload" \
      --connect-timeout 5 \
      --max-time 10 \
      "${DISPATCHER_URL}/worker/register" >/dev/null 2>&1; then
    echo "[+] Registered with dispatcher at ${DISPATCHER_URL} (id=${INSTANCE_ID}, ip=${ip})"
  else
    echo "[!] Warning: could not register with dispatcher at ${DISPATCHER_URL} (non-fatal)"
  fi
}

# --- Report task completion to dispatcher ---
report_task_done() {
  local task_num="$1"
  local task_desc="$2"
  local duration="$3"

  if [ -z "$DISPATCHER_URL" ]; then
    return 0
  fi

  local payload
  payload=$(printf '{"worker_id":"%s","task":"%s","duration":%d}' \
    "$INSTANCE_ID" "task-${task_num}: ${task_desc}" "$duration")

  if curl -s -f -X POST \
      -H "Content-Type: application/json" \
      -d "$payload" \
      --connect-timeout 5 \
      --max-time 10 \
      "${DISPATCHER_URL}/worker/done" >/dev/null 2>&1; then
    echo "[+] Reported task #${task_num} done to dispatcher"
  else
    echo "[!] Warning: could not reach dispatcher at ${DISPATCHER_URL} (non-fatal)"
  fi
}

# --- Report idle status to dispatcher for scale-down ---
report_worker_idle() {
  local idle_since="$1"

  if [ -z "$DISPATCHER_URL" ]; then
    return 0
  fi

  local payload
  payload=$(printf '{"worker_id":"%s","idle_since":"%s"}' "$INSTANCE_ID" "$idle_since")

  local response
  response=$(curl -s -f -X POST \
      -H "Content-Type: application/json" \
      -d "$payload" \
      --connect-timeout 5 \
      --max-time 15 \
      "${DISPATCHER_URL}/worker/idle" 2>/dev/null || echo "")

  if [ -z "$response" ]; then
    echo "[!] Warning: could not reach dispatcher at ${DISPATCHER_URL} for idle report (non-fatal)"
    return 1
  fi

  local status
  status=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "")
  echo "[+] Idle report response from dispatcher: status=${status}"
  echo "$status"
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
IDLE_START=0  # epoch seconds when worker first went idle (0 = not idle)

register_with_dispatcher
merge_leftover_prs

while true; do
  if check_maintenance; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [$INSTANCE_ID] Maintenance mode -- paused"
    IDLE_START=0
    sleep "$COOLDOWN"
    continue
  fi

  # Check API control flags (interrupt, force-pull)
  if ! check_api_flags; then
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
    NOW=$(date +%s)

    # Start idle timer on first idle iteration
    if [ "$IDLE_START" -eq 0 ]; then
      IDLE_START="$NOW"
      IDLE_SINCE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
      echo "  All remaining tasks are claimed by other instances. Idle timer started."
    fi

    IDLE_SECS=$(( NOW - IDLE_START ))
    IDLE_TIMEOUT_SECS=$(( IDLE_TIMEOUT * 60 ))
    echo "  All remaining tasks are claimed. Idle for ${IDLE_SECS}s / ${IDLE_TIMEOUT_SECS}s."

    if [ "$IDLE_SECS" -ge "$IDLE_TIMEOUT_SECS" ]; then
      echo "[+] Idle timeout reached (${IDLE_TIMEOUT}min). Reporting to dispatcher for scale-down..."
      IDLE_REPORT_STATUS=$(report_worker_idle "$IDLE_SINCE")

      if [ "$IDLE_REPORT_STATUS" = "stopping" ]; then
        echo "[+] Dispatcher confirmed scale-down. Waiting for EC2 stop-instances..."
        # Wait up to 10 minutes for the instance to be stopped externally.
        # Do NOT self-terminate -- the dispatcher issues stop-instances.
        for _ in $(seq 1 120); do
          sleep 5
        done
        # If still running after 10 min, reset idle timer and continue
        echo "[!] Instance not stopped after 10 minutes. Resetting idle timer."
        IDLE_START=0
      elif [ "$IDLE_REPORT_STATUS" = "busy" ]; then
        echo "  Dispatcher says tasks are pending -- resetting idle timer."
        IDLE_START=0
      else
        # No dispatcher or unexpected response -- reset timer and keep polling
        IDLE_START=0
      fi
    fi

    sleep "$COOLDOWN"
    continue
  fi

  # A task was found -- reset idle timer
  IDLE_START=0
  echo "  Claiming task #${NEXT_TASK}"

  # Get task details
  TASK_DESC=$(get_task_description "$NEXT_TASK")
  TASK_PR_TITLE=$(get_pr_title "$NEXT_TASK")
  echo "  Task:     $TASK_DESC"
  echo "  PR title: $TASK_PR_TITLE"

  # Run the TDD pipeline
  PIPELINE_EXIT=0
  TASK_START=$(date +%s)
  run_pipeline "$NEXT_TASK" "$TASK_DESC" "$TASK_PR_TITLE" || PIPELINE_EXIT=$?
  TASK_DURATION=$(( $(date +%s) - TASK_START ))

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
    report_task_done "$NEXT_TASK" "$TASK_DESC" "$TASK_DURATION"
  fi

  # Safety net: merge any leftover PRs
  git checkout "$BRANCH" 2>/dev/null || true
  git pull origin "$BRANCH" 2>/dev/null || true
  merge_leftover_prs

  echo "[+] Cooling down for ${COOLDOWN}s..."
  sleep "$COOLDOWN"
done
