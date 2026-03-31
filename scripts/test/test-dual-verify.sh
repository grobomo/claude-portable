#!/bin/bash
# test-dual-verify.sh -- End-to-end test for the dual verification system.
#
# Creates a mock scenario, runs both worker and manager verification,
# and confirms the gate blocks until both markers exist.
#
# Usage:
#   test-dual-verify.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
GATE_SCRIPT="${REPO_ROOT}/.claude/hooks/run-modules/PreToolUse/dual-verify-gate.js"
WORKER_SCRIPT="${REPO_ROOT}/scripts/fleet/worker-verify.sh"
MANAGER_SCRIPT="${REPO_ROOT}/scripts/fleet/manager-review.sh"

# Test tracking
PASS=0
FAIL=0
TOTAL=0

assert() {
  local name="$1" expected="$2" actual="$3"
  TOTAL=$((TOTAL + 1))
  if [[ "$expected" == "$actual" ]]; then
    echo "  [PASS] ${name}"
    PASS=$((PASS + 1))
  else
    echo "  [FAIL] ${name}: expected=${expected} actual=${actual}"
    FAIL=$((FAIL + 1))
  fi
}

# ── Setup: temp git repo ──────────────────────────────────────────────────────
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

echo "=== Dual-Verify Gate Test ==="
echo "Temp dir: ${TMPDIR}"
echo ""

cd "$TMPDIR"
git init -q
git checkout -b task-042-test-feature -q 2>/dev/null || git checkout -b task-042-test-feature
mkdir -p .test-results tests

# Create a trivial test suite for the worker
cat > tests/smoke.sh <<'SMOKE'
#!/bin/bash
echo "Smoke test running..."
exit 0
SMOKE
chmod +x tests/smoke.sh

git add -A && git commit -q -m "init"

TASK_NUM="042"

# ── Test 1: Gate blocks with no markers ───────────────────────────────────────
echo "--- Test 1: Gate blocks with no markers ---"

GATE_INPUT='{"tool_name":"Bash","tool_input":{"command":"gh pr merge --squash"}}'
GATE_EXIT=0
GATE_OUT="$(echo "$GATE_INPUT" | node "$GATE_SCRIPT" 2>/dev/null)" || GATE_EXIT=$?

assert "gate exits 2 (block) with no markers" "2" "$GATE_EXIT"

if echo "$GATE_OUT" | grep -q '"block"'; then
  assert "gate output contains block decision" "yes" "yes"
else
  assert "gate output contains block decision" "yes" "no"
fi
echo ""

# ── Test 2: Worker verify creates marker ──────────────────────────────────────
echo "--- Test 2: Worker verification ---"

export WORKER_TEST_CMD="bash tests/smoke.sh"
WORKER_EXIT=0
bash "$WORKER_SCRIPT" "$TASK_NUM" "$TMPDIR" || WORKER_EXIT=$?

assert "worker-verify exits 0" "0" "$WORKER_EXIT"
assert "worker marker exists" "yes" "$(test -f .test-results/T${TASK_NUM}.worker-passed && echo yes || echo no)"
echo ""

# ── Test 3: Gate still blocks with only worker marker ─────────────────────────
echo "--- Test 3: Gate blocks with only worker marker ---"

GATE_EXIT=0
GATE_OUT="$(echo "$GATE_INPUT" | node "$GATE_SCRIPT" 2>/dev/null)" || GATE_EXIT=$?

assert "gate still exits 2 (only worker)" "2" "$GATE_EXIT"

if echo "$GATE_OUT" | grep -q "manager-reviewed"; then
  assert "gate mentions missing manager-reviewed" "yes" "yes"
else
  assert "gate mentions missing manager-reviewed" "yes" "no"
fi
echo ""

# ── Test 4: Manager review creates marker ─────────────────────────────────────
echo "--- Test 4: Manager verification ---"

export MANAGER_TEST_CMD="echo 'Manager tests OK'"
MANAGER_EXIT=0
bash "$MANAGER_SCRIPT" "$TASK_NUM" "" "$TMPDIR" || MANAGER_EXIT=$?

assert "manager-review exits 0" "0" "$MANAGER_EXIT"
assert "manager marker exists" "yes" "$(test -f .test-results/T${TASK_NUM}.manager-reviewed && echo yes || echo no)"
echo ""

# ── Test 5: Gate allows with both markers ─────────────────────────────────────
echo "--- Test 5: Gate allows with both markers ---"

GATE_EXIT=0
GATE_OUT="$(echo "$GATE_INPUT" | node "$GATE_SCRIPT" 2>/dev/null)" || GATE_EXIT=$?

assert "gate exits 0 (allow) with both markers" "0" "$GATE_EXIT"

if echo "$GATE_OUT" | grep -q '"allow"'; then
  assert "gate output contains allow decision" "yes" "yes"
else
  assert "gate output contains allow decision" "yes" "no"
fi
echo ""

# ── Test 6: Gate ignores non-merge commands ───────────────────────────────────
echo "--- Test 6: Gate ignores non-merge commands ---"

NON_MERGE='{"tool_name":"Bash","tool_input":{"command":"gh pr create --title test"}}'
GATE_EXIT=0
echo "$NON_MERGE" | node "$GATE_SCRIPT" 2>/dev/null || GATE_EXIT=$?

assert "gate exits 0 for non-merge command" "0" "$GATE_EXIT"
echo ""

# ── Test 7: Gate ignores non-Bash tools ───────────────────────────────────────
echo "--- Test 7: Gate ignores non-Bash tools ---"

NON_BASH='{"tool_name":"Write","tool_input":{"file_path":"test.txt","content":"hello"}}'
GATE_EXIT=0
echo "$NON_BASH" | node "$GATE_SCRIPT" 2>/dev/null || GATE_EXIT=$?

assert "gate exits 0 for non-Bash tool" "0" "$GATE_EXIT"
echo ""

# ── Test 8: Manager blocks if worker hasn't run ──────────────────────────────
echo "--- Test 8: Manager blocks without worker marker ---"

TMPDIR2="$(mktemp -d)"
cd "$TMPDIR2"
git init -q
git checkout -b task-099-no-worker -q 2>/dev/null || git checkout -b task-099-no-worker
mkdir -p .test-results
git add -A && git commit -q -m "init" --allow-empty

MANAGER_EXIT=0
bash "$MANAGER_SCRIPT" "099" "" "$TMPDIR2" 2>&1 || MANAGER_EXIT=$?

assert "manager exits 1 without worker marker" "1" "$MANAGER_EXIT"

rm -rf "$TMPDIR2"
cd "$TMPDIR"
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
echo "==============================="
echo "Results: ${PASS}/${TOTAL} passed, ${FAIL} failed"
echo "==============================="

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
exit 0
