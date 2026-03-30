#!/usr/bin/env bash
# Test that git-dispatch.py reads TARGET_REPO_URL/TARGET_WORKDIR config.
# Verifies the config vars exist and _resolve_target works.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DISPATCH="$(cd "$SCRIPT_DIR/.." && pwd)/git-dispatch.py"
# Convert Git Bash /c/ paths to C:/ for Python on Windows
[[ "$DISPATCH" == /c/* ]] && DISPATCH="C:/${DISPATCH#/c/}"
[[ "$DISPATCH" == /d/* ]] && DISPATCH="D:/${DISPATCH#/d/}"

PASS=0
FAIL=0

check() {
  local desc="$1" cmd="$2"
  if eval "$cmd" >/dev/null 2>&1; then
    echo "  PASS: $desc"
    PASS=$((PASS + 1))
  else
    echo "  FAIL: $desc"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== Multi-Repo Dispatch Config Tests ==="

# Check config vars exist in code
check "TARGET_REPO_URL defined" "grep -q 'TARGET_REPO_URL' '$DISPATCH'"
check "TARGET_WORKDIR defined" "grep -q 'TARGET_WORKDIR' '$DISPATCH'"
check "TARGET_BRANCH defined" "grep -q 'TARGET_BRANCH' '$DISPATCH'"
check "_resolve_target function exists" "grep -q 'def _resolve_target' '$DISPATCH'"
check "No hardcoded /workspace/boothapp outside defaults" "test \$(grep -c 'workspace/boothapp' '$DISPATCH') -le 2"
check "No hardcoded altarr/boothapp outside defaults" "test \$(grep -c 'altarr/boothapp' '$DISPATCH') -le 2"
check "_dispatch_relay_request calls _resolve_target" "grep -A5 'def _dispatch_relay_request' '$DISPATCH' | grep -q '_resolve_target'"

# Test Python import
# Direct parse check (eval quoting mangles paths)
if python3 -c "import ast; ast.parse(open('$DISPATCH').read())" 2>/dev/null; then
  echo "  PASS: git-dispatch.py parses without errors"
  PASS=$((PASS + 1))
else
  echo "  FAIL: git-dispatch.py parses without errors"
  FAIL=$((FAIL + 1))
fi

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
