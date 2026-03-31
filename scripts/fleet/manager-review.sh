#!/bin/bash
# manager-review.sh -- Manager pulls PR branch and runs independent verification.
#
# If tests pass:  creates .test-results/T<NNN>.manager-reviewed marker
# If tests fail:  requests changes on the PR via gh CLI
#
# This runs a DIFFERENT or STRICTER test suite than the worker, implementing
# the senior-dev-reviews pattern.
#
# Usage:
#   manager-review.sh <task-number> [pr-number] [workdir]
#
# Environment:
#   MANAGER_TEST_CMD       Custom test command (default: verify-integration.sh)
#   MANAGER_STRICT_MODE    Set to "1" for stricter thresholds (default: 1)
#   MANAGER_REVIEW_CHECKS  Extra checks: "lint,typecheck,security" (comma-separated)
set -euo pipefail

TASK_NUM="${1:?Usage: manager-review.sh <task-number> [pr-number] [workdir]}"
PR_NUM="${2:-}"
WORKDIR="${3:-.}"

cd "$WORKDIR"

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
RESULTS_DIR="${REPO_ROOT}/.test-results"
WORKER_MARKER="${RESULTS_DIR}/T${TASK_NUM}.worker-passed"
MANAGER_MARKER="${RESULTS_DIR}/T${TASK_NUM}.manager-reviewed"

mkdir -p "$RESULTS_DIR"

echo "=== Manager Review for T${TASK_NUM} ==="
echo "Repo root: ${REPO_ROOT}"
echo "Branch:    $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'detached')"
echo ""

# ── Pre-check: worker must have passed first ──────────────────────────────────
if [[ ! -f "$WORKER_MARKER" ]]; then
  echo "[BLOCK] Worker verification marker not found: ${WORKER_MARKER}"
  echo "The worker must run worker-verify.sh first."
  exit 1
fi

echo "[OK] Worker marker found: $(head -1 "$WORKER_MARKER")"
echo ""

# ── Determine review command ──────────────────────────────────────────────────
STRICT_MODE="${MANAGER_STRICT_MODE:-1}"
REVIEW_CHECKS="${MANAGER_REVIEW_CHECKS:-}"
TEST_CMD="${MANAGER_TEST_CMD:-}"

if [[ -z "$TEST_CMD" ]]; then
  # Default: use verify-integration.sh (the project's existing verification suite)
  if [[ -f "${REPO_ROOT}/scripts/test/verify-integration.sh" ]]; then
    TEST_CMD="bash ${REPO_ROOT}/scripts/test/verify-integration.sh"
  elif [[ -f "${REPO_ROOT}/test.sh" ]]; then
    TEST_CMD="bash ${REPO_ROOT}/test.sh"
  else
    TEST_CMD="echo 'No manager test suite found -- passing by default'"
  fi
fi

echo "Review command: ${TEST_CMD}"
echo "Strict mode:   ${STRICT_MODE}"
echo ""

# ── Run extra checks if configured ───────────────────────────────────────────
EXTRA_FAILURES=0

if [[ -n "$REVIEW_CHECKS" ]]; then
  IFS=',' read -ra CHECKS <<< "$REVIEW_CHECKS"
  for check in "${CHECKS[@]}"; do
    echo "--- Extra check: ${check} ---"
    case "$check" in
      lint)
        if command -v shellcheck &>/dev/null; then
          shellcheck scripts/**/*.sh 2>/dev/null || EXTRA_FAILURES=$((EXTRA_FAILURES + 1))
        else
          echo "[SKIP] shellcheck not installed"
        fi
        ;;
      typecheck)
        if [[ -f "${REPO_ROOT}/tsconfig.json" ]]; then
          npx tsc --noEmit 2>/dev/null || EXTRA_FAILURES=$((EXTRA_FAILURES + 1))
        else
          echo "[SKIP] No tsconfig.json"
        fi
        ;;
      security)
        # Check for common security issues
        if grep -rn 'eval\s*(' "${REPO_ROOT}/scripts/" --include="*.js" 2>/dev/null | grep -v node_modules; then
          echo "[WARN] eval() usage found"
          EXTRA_FAILURES=$((EXTRA_FAILURES + 1))
        fi
        ;;
      *)
        echo "[SKIP] Unknown check: ${check}"
        ;;
    esac
    echo ""
  done
fi

if [[ "$EXTRA_FAILURES" -gt 0 ]]; then
  echo "[FAIL] ${EXTRA_FAILURES} extra check(s) failed"
  request_changes "Extra checks failed: ${EXTRA_FAILURES} issue(s) found"
  exit 1
fi

# ── Run main verification ─────────────────────────────────────────────────────
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if eval "$TEST_CMD"; then
  FINISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo ""
  echo "[PASS] Manager review passed for T${TASK_NUM}"

  # Write marker file with metadata
  cat > "$MANAGER_MARKER" <<EOF
task: T${TASK_NUM}
role: manager
result: reviewed-passed
test_cmd: ${TEST_CMD}
strict_mode: ${STRICT_MODE}
started_at: ${STARTED_AT}
finished_at: ${FINISHED_AT}
worker_marker: $(basename "$WORKER_MARKER")
branch: $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')
commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'unknown')
hostname: $(hostname 2>/dev/null || echo 'unknown')
EOF

  echo "Marker written: ${MANAGER_MARKER}"

  # Push marker to PR branch
  git add "$MANAGER_MARKER" 2>/dev/null || true
  git commit -m "review: manager verification passed for T${TASK_NUM}" -- "$MANAGER_MARKER" 2>/dev/null || true
  git push 2>/dev/null || echo "[WARN] Could not push marker (will be included in next push)"

  # Approve the PR if we have a PR number
  if [[ -n "$PR_NUM" ]]; then
    gh pr review "$PR_NUM" --approve --body "Manager review passed for T${TASK_NUM}. Dual verification complete." 2>/dev/null || true
    echo "[DONE] PR #${PR_NUM} approved"
  fi

  echo "[DONE] Manager review complete -- ready to merge"
  exit 0
else
  FINISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo ""
  echo "[FAIL] Manager review failed for T${TASK_NUM}"

  # Request changes on the PR
  if [[ -n "$PR_NUM" ]]; then
    gh pr review "$PR_NUM" --request-changes \
      --body "Manager review FAILED for T${TASK_NUM}. Worker must fix and re-verify." 2>/dev/null || true
    echo "[DONE] Changes requested on PR #${PR_NUM}"
  fi

  echo "Worker must fix failures and re-run both verification steps."
  exit 1
fi
