#!/usr/bin/env bash
# Test: verify git-dispatch.py prompt includes PR creation instructions
set -euo pipefail
PASS=0; FAIL=0

check() {
  local desc="$1" result="$2"
  if [ "$result" = "0" ]; then
    echo "  PASS: $desc"; PASS=$((PASS + 1))
  else
    echo "  FAIL: $desc"; FAIL=$((FAIL + 1))
  fi
}

DISPATCH="$(dirname "$0")/../../scripts/git-dispatch.py"

# T001: Prompt contains PR creation instructions
grep -q "Create a pull request" "$DISPATCH" || grep -q "gh pr create" "$DISPATCH"
check "Prompt mentions PR creation" "$?"

grep -q "Push the branch" "$DISPATCH" || grep -q "git push" "$DISPATCH"
check "Prompt mentions pushing branch" "$?"

grep -q "Create a new git branch" "$DISPATCH" || grep -q "new.*branch" "$DISPATCH"
check "Prompt mentions creating branch" "$?"

# Verify the instruction block is in _dispatch_relay_request
grep -A20 "CRITICAL.*PR creation" "$DISPATCH" | grep -q "gh pr create"
check "PR instruction block in dispatch function" "$?"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
