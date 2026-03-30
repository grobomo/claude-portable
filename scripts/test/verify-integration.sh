#!/bin/bash
# verify-integration.sh -- Pre-PR verification suite for worker tasks.
#
# Runs all checks that must pass before a PR can be created.
# Outputs structured JSON results to stdout when --json flag is used.
# Exit code: 0 = all passed, 1 = failures found.
#
# Usage:
#   verify-integration.sh [--json] [--base-branch main] [workdir]
#
# Environment:
#   TEST_RUN_CMD        Test command to run (default: auto-detect)
#   VERIFY_BASE_BRANCH  Base branch for diff checks (default: main)
set -uo pipefail

JSON_OUTPUT=false
BASE_BRANCH="${VERIFY_BASE_BRANCH:-main}"
WORKDIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --json) JSON_OUTPUT=true; shift ;;
    --base-branch) BASE_BRANCH="$2"; shift 2 ;;
    *) WORKDIR="$1"; shift ;;
  esac
done

if [[ -n "$WORKDIR" ]]; then
  cd "$WORKDIR" || exit 1
fi

# Track results
declare -a CHECK_NAMES=()
declare -a CHECK_RESULTS=()
declare -a CHECK_DETAILS=()
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

add_result() {
  local name="$1" result="$2" detail="$3"
  CHECK_NAMES+=("$name")
  CHECK_RESULTS+=("$result")
  CHECK_DETAILS+=("$detail")
  case "$result" in
    pass) PASS_COUNT=$((PASS_COUNT + 1)) ;;
    fail) FAIL_COUNT=$((FAIL_COUNT + 1)) ;;
    warn) WARN_COUNT=$((WARN_COUNT + 1)) ;;
  esac
}

# ── Check 1: Shell script syntax ──────────────────────────────────────────────
check_shell_syntax() {
  local changed_sh errors=""
  changed_sh=$(git diff --name-only "${BASE_BRANCH}"...HEAD 2>/dev/null | grep '\.sh$' || true)
  if [[ -z "$changed_sh" ]]; then
    add_result "shell_syntax" "pass" "No shell scripts changed"
    return
  fi
  local bad=0
  for sh_file in $changed_sh; do
    if [[ -f "$sh_file" ]]; then
      if ! bash -n "$sh_file" 2>/tmp/verify-syntax-err; then
        errors="${errors}${sh_file}: $(cat /tmp/verify-syntax-err)\n"
        bad=$((bad + 1))
      fi
    fi
  done
  if [[ $bad -gt 0 ]]; then
    add_result "shell_syntax" "fail" "${bad} script(s) with syntax errors: ${errors}"
  else
    add_result "shell_syntax" "pass" "All changed shell scripts pass syntax check"
  fi
}

# ── Check 2: Secret/path scan ────────────────────────────────────────────────
check_secrets() {
  local hits
  hits=$(git diff "${BASE_BRANCH}"...HEAD -- '*.sh' '*.json' '*.js' '*.py' '*.yml' 2>/dev/null \
    | grep -cE '^\+.*(C:/Users/|AKIA[0-9A-Z]{16}|ghp_[a-zA-Z0-9]{36}|sk-[a-zA-Z0-9]{48}|PASSWORD=|SECRET=)' || echo "0")
  if [[ "$hits" -gt 0 ]]; then
    add_result "secret_scan" "fail" "Found ${hits} potential secret(s) or personal path(s) in diff"
  else
    add_result "secret_scan" "pass" "No secrets or personal paths in diff"
  fi
}

# ── Check 3: Run tests ──────────────────────────────────────────────────────
check_tests() {
  local test_cmd="${TEST_RUN_CMD:-}"
  local output=""
  local rc=0

  # Auto-detect test command
  if [[ -z "$test_cmd" ]]; then
    if [[ -f "package.json" ]] && grep -q '"test"' package.json 2>/dev/null; then
      test_cmd="npm test"
    elif [[ -f "pytest.ini" ]] || [[ -f "setup.cfg" ]] || [[ -d "tests" ]]; then
      test_cmd="python3 -m pytest tests/ -x --tb=short 2>&1"
    elif [[ -f "Makefile" ]] && grep -q '^test:' Makefile 2>/dev/null; then
      test_cmd="make test"
    fi
  fi

  if [[ -z "$test_cmd" ]]; then
    add_result "tests" "warn" "No test command found (set TEST_RUN_CMD or add tests/)"
    return
  fi

  output=$(eval "$test_cmd" 2>&1) || rc=$?
  if [[ $rc -eq 0 ]]; then
    # Extract summary line (last non-empty line usually has counts)
    local summary
    summary=$(echo "$output" | tail -5 | grep -E '(passed|failed|error|ok|PASSED|FAILED)' | tail -1)
    add_result "tests" "pass" "${summary:-All tests passed}"
  else
    local last_lines
    last_lines=$(echo "$output" | tail -10)
    add_result "tests" "fail" "Tests failed (exit ${rc}): ${last_lines}"
  fi
}

# ── Check 4: Python syntax (changed .py files) ──────────────────────────────
check_python_syntax() {
  local changed_py
  changed_py=$(git diff --name-only "${BASE_BRANCH}"...HEAD 2>/dev/null | grep '\.py$' || true)
  if [[ -z "$changed_py" ]]; then
    add_result "python_syntax" "pass" "No Python files changed"
    return
  fi
  local bad=0 errors=""
  for py_file in $changed_py; do
    if [[ -f "$py_file" ]]; then
      if ! python3 -c "import ast; ast.parse(open('${py_file}').read())" 2>/tmp/verify-py-err; then
        errors="${errors}${py_file}: $(cat /tmp/verify-py-err)\n"
        bad=$((bad + 1))
      fi
    fi
  done
  if [[ $bad -gt 0 ]]; then
    add_result "python_syntax" "fail" "${bad} file(s) with syntax errors: ${errors}"
  else
    add_result "python_syntax" "pass" "All changed Python files pass syntax check"
  fi
}

# ── Check 5: Line endings ───────────────────────────────────────────────────
check_line_endings() {
  local changed_sh
  changed_sh=$(git diff --name-only "${BASE_BRANCH}"...HEAD 2>/dev/null | grep '\.sh$' || true)
  if [[ -z "$changed_sh" ]]; then
    add_result "line_endings" "pass" "No shell scripts to check"
    return
  fi
  local crlf_files=""
  for sh_file in $changed_sh; do
    if [[ -f "$sh_file" ]] && grep -qP '\r$' "$sh_file" 2>/dev/null; then
      crlf_files="${crlf_files} ${sh_file}"
    fi
  done
  if [[ -n "$crlf_files" ]]; then
    add_result "line_endings" "fail" "CRLF line endings found in:${crlf_files}"
  else
    add_result "line_endings" "pass" "All shell scripts have LF line endings"
  fi
}

# ── Check 6: TODO/FIXME/HACK in new code ────────────────────────────────────
check_todo_markers() {
  local hits
  hits=$(git diff "${BASE_BRANCH}"...HEAD 2>/dev/null \
    | grep -cE '^\+.*(TODO|FIXME|HACK)' || echo "0")
  if [[ "$hits" -gt 0 ]]; then
    add_result "todo_markers" "warn" "${hits} TODO/FIXME/HACK marker(s) in new code"
  else
    add_result "todo_markers" "pass" "No TODO/FIXME/HACK markers in new code"
  fi
}

# ── Run all checks ──────────────────────────────────────────────────────────
check_shell_syntax
check_secrets
check_tests
check_python_syntax
check_line_endings
check_todo_markers

# ── Output results ──────────────────────────────────────────────────────────
if $JSON_OUTPUT; then
  # Build JSON output
  echo "{"
  echo "  \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
  echo "  \"base_branch\": \"${BASE_BRANCH}\","
  echo "  \"pass\": ${PASS_COUNT},"
  echo "  \"fail\": ${FAIL_COUNT},"
  echo "  \"warn\": ${WARN_COUNT},"
  echo "  \"overall\": \"$(if [[ $FAIL_COUNT -eq 0 ]]; then echo "pass"; else echo "fail"; fi)\","
  echo "  \"checks\": ["
  _last_idx=$((${#CHECK_NAMES[@]} - 1))
  for i in "${!CHECK_NAMES[@]}"; do
    _comma=","
    if [[ $i -eq $_last_idx ]]; then _comma=""; fi
    # Escape detail string for JSON
    _escaped_detail=$(echo "${CHECK_DETAILS[$i]}" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\t/\\t/g' | tr '\n' ' ')
    echo "    {\"name\": \"${CHECK_NAMES[$i]}\", \"result\": \"${CHECK_RESULTS[$i]}\", \"detail\": \"${_escaped_detail}\"}${_comma}"
  done
  echo "  ]"
  echo "}"
else
  # Human-readable output
  echo ""
  echo "=== Verification Results ==="
  echo "  Passed: ${PASS_COUNT}  Failed: ${FAIL_COUNT}  Warnings: ${WARN_COUNT}"
  echo ""
  for i in "${!CHECK_NAMES[@]}"; do
    _icon="[PASS]"
    case "${CHECK_RESULTS[$i]}" in
      fail) _icon="[FAIL]" ;;
      warn) _icon="[WARN]" ;;
    esac
    echo "  ${_icon} ${CHECK_NAMES[$i]}: ${CHECK_DETAILS[$i]}"
  done
  echo ""
  if [[ $FAIL_COUNT -gt 0 ]]; then
    echo "VERIFICATION FAILED: ${FAIL_COUNT} check(s) failed"
  else
    echo "VERIFICATION PASSED: All checks passed"
  fi
fi

# Exit with failure if any checks failed
[[ $FAIL_COUNT -eq 0 ]]
