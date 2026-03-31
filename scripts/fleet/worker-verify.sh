#!/bin/bash
# worker-verify.sh -- Run e2e tests after worker completes a task.
#
# Creates .test-results/T<NNN>.worker-passed marker on success,
# then pushes the marker to the PR branch so the manager can see it.
#
# Usage:
#   worker-verify.sh <task-number> [workdir]
#
# Environment:
#   WORKER_TEST_CMD   Custom test command (default: auto-detect)
#   WORKER_TEST_DIR   Directory containing tests (default: tests/)
set -euo pipefail

TASK_NUM="${1:?Usage: worker-verify.sh <task-number> [workdir]}"
WORKDIR="${2:-.}"

cd "$WORKDIR"

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
RESULTS_DIR="${REPO_ROOT}/.test-results"
MARKER="${RESULTS_DIR}/T${TASK_NUM}.worker-passed"

mkdir -p "$RESULTS_DIR"

echo "=== Worker Verification for T${TASK_NUM} ==="
echo "Repo root: ${REPO_ROOT}"
echo "Branch:    $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'detached')"
echo ""

# ── Determine test command ────────────────────────────────────────────────────
TEST_CMD="${WORKER_TEST_CMD:-}"

if [[ -z "$TEST_CMD" ]]; then
  if [[ -f "${REPO_ROOT}/package.json" ]] && grep -q '"test"' "${REPO_ROOT}/package.json" 2>/dev/null; then
    TEST_CMD="npm test"
  elif [[ -f "${REPO_ROOT}/Makefile" ]] && grep -q '^test:' "${REPO_ROOT}/Makefile" 2>/dev/null; then
    TEST_CMD="make test"
  elif [[ -d "${REPO_ROOT}/tests" ]]; then
    TEST_CMD="bash -c 'for t in tests/*.sh; do bash \"\$t\" || exit 1; done'"
  else
    TEST_CMD="echo 'No test suite found -- passing by default'"
  fi
fi

echo "Test command: ${TEST_CMD}"
echo ""

# ── Run tests ─────────────────────────────────────────────────────────────────
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if eval "$TEST_CMD"; then
  FINISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo ""
  echo "[PASS] Worker tests passed for T${TASK_NUM}"

  # Write marker file with metadata
  cat > "$MARKER" <<EOF
task: T${TASK_NUM}
role: worker
result: passed
test_cmd: ${TEST_CMD}
started_at: ${STARTED_AT}
finished_at: ${FINISHED_AT}
branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')
commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')
hostname: $(hostname 2>/dev/null || echo 'unknown')
EOF

  echo "Marker written: ${MARKER}"

  # Push marker to PR branch
  git add "$MARKER" 2>/dev/null || true
  git commit -m "test: worker verification passed for T${TASK_NUM}" -- "$MARKER" 2>/dev/null || true
  git push 2>/dev/null || echo "[WARN] Could not push marker (will be included in next push)"

  echo "[DONE] Worker verification complete"
  exit 0
else
  FINISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo ""
  echo "[FAIL] Worker tests failed for T${TASK_NUM}"
  echo "Fix the failures and re-run: worker-verify.sh ${TASK_NUM}"
  exit 1
fi
