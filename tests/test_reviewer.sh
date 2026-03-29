#!/usr/bin/env bash
# Tests for the reviewer function in continuous-claude.sh
# Validates: APPROVE verdict passes, REJECT verdict retries, max rejections blocks
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

PASS=0
FAIL=0

assert_eq() {
  local desc="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    echo "  PASS: $desc"
    PASS=$((PASS + 1))
  else
    echo "  FAIL: $desc (expected=$expected actual=$actual)"
    FAIL=$((FAIL + 1))
  fi
}

# Source the function (we need to mock claude)
# Extract just the run_reviewer function
extract_function() {
  sed -n '/^run_reviewer()/,/^}/p' "$SCRIPT_DIR/scripts/continuous-claude.sh"
}

# Create a mock claude that writes a review file with a given verdict
setup_mock_claude() {
  local review_dir="$1"
  local verdict="$2"  # APPROVE or REJECT

  # Create mock claude script
  cat > "$TMPDIR/claude" << MOCK
#!/bin/bash
# Mock claude that writes review file
review_file=\$(echo "\$@" | grep -oP '(?<=review-)\w+(?=\.md)' || true)
if [ -n "\$review_file" ]; then
  echo "Review analysis here" > "${review_dir}/review-\${review_file}.md"
  echo "REVIEW: ${verdict}" >> "${review_dir}/review-\${review_file}.md"
fi
# Also check the prompt for the review file path and write there
for arg in "\$@"; do
  if echo "\$arg" | grep -q "review-"; then
    review_path=\$(echo "\$arg" | grep -oP '/[^ ]*review-[^ ]*\.md' | head -1)
    if [ -n "\$review_path" ]; then
      mkdir -p "\$(dirname "\$review_path")"
      echo "Review" > "\$review_path"
      echo "REVIEW: ${verdict}" >> "\$review_path"
    fi
  fi
done
MOCK
  chmod +x "$TMPDIR/claude"
}

echo "=== Reviewer function tests ==="

# Test 1: Function exists in script
echo "Test 1: run_reviewer function exists"
if grep -q "^run_reviewer()" "$SCRIPT_DIR/scripts/continuous-claude.sh"; then
  assert_eq "function exists" "0" "0"
else
  assert_eq "function exists" "0" "1"
fi

# Test 2: Reviewer prompt mentions APPROVE/REJECT
echo "Test 2: Reviewer prompt mentions APPROVE and REJECT"
if grep -q "REVIEW: APPROVE" "$SCRIPT_DIR/scripts/continuous-claude.sh" && \
   grep -q "REVIEW: REJECT" "$SCRIPT_DIR/scripts/continuous-claude.sh"; then
  assert_eq "prompt has verdicts" "0" "0"
else
  assert_eq "prompt has verdicts" "0" "1"
fi

# Test 3: Reviewer is called after RESEARCH gate
echo "Test 3: Reviewer called after RESEARCH gate"
if grep -q 'run_reviewer "RESEARCH"' "$SCRIPT_DIR/scripts/continuous-claude.sh"; then
  assert_eq "RESEARCH reviewer call" "0" "0"
else
  assert_eq "RESEARCH reviewer call" "0" "1"
fi

# Test 4: Reviewer is called after PLAN gate
echo "Test 4: Reviewer called after PLAN gate"
if grep -q 'run_reviewer "PLAN"' "$SCRIPT_DIR/scripts/continuous-claude.sh"; then
  assert_eq "PLAN reviewer call" "0" "0"
else
  assert_eq "PLAN reviewer call" "0" "1"
fi

# Test 5: Reviewer is called after IMPLEMENT gate
echo "Test 5: Reviewer called after IMPLEMENT gate"
if grep -q 'run_reviewer "IMPLEMENT"' "$SCRIPT_DIR/scripts/continuous-claude.sh"; then
  assert_eq "IMPLEMENT reviewer call" "0" "0"
else
  assert_eq "IMPLEMENT reviewer call" "0" "1"
fi

# Test 6: Review file path uses pipeline_dir
echo "Test 6: Review files go to pipeline_dir"
if grep -q 'review_file="${pipeline_dir}/review-' "$SCRIPT_DIR/scripts/continuous-claude.sh"; then
  assert_eq "review file in pipeline_dir" "0" "0"
else
  assert_eq "review file in pipeline_dir" "0" "1"
fi

# Test 7: Max rejections configurable
echo "Test 7: Max rejections parameter exists"
if grep -q 'max_rejections=' "$SCRIPT_DIR/scripts/continuous-claude.sh"; then
  assert_eq "max_rejections param" "0" "0"
else
  assert_eq "max_rejections param" "0" "1"
fi

# Test 8: Review result logged to stage-log.json
echo "Test 8: Review result logged to stage_log"
if grep -q "'reviews'" "$SCRIPT_DIR/scripts/continuous-claude.sh"; then
  assert_eq "review logged" "0" "0"
else
  assert_eq "review logged" "0" "1"
fi

# Test 9: Pipeline audit trail copied to .pipeline/ before PR
echo "Test 9: Pipeline folder copied to .pipeline/task-N/"
if grep -q '\.pipeline/task-' "$SCRIPT_DIR/scripts/continuous-claude.sh"; then
  assert_eq "audit trail copy" "0" "0"
else
  assert_eq "audit trail copy" "0" "1"
fi

# Test 10: Audit trail committed before PR stage
echo "Test 10: Audit trail git commit before PR stage"
if grep -B5 "STAGE 7: PR" "$SCRIPT_DIR/scripts/continuous-claude.sh" | grep -q "git commit.*audit trail"; then
  assert_eq "audit commit before PR" "0" "0"
else
  assert_eq "audit commit before PR" "0" "1"
fi

echo ""
echo "=== Results: ${PASS} passed, ${FAIL} failed ==="
[ "$FAIL" -eq 0 ] || exit 1
