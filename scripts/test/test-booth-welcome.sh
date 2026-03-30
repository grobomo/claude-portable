#!/usr/bin/env bash
# Validates booth-welcome.html structure and content
set -euo pipefail

FILE="web/booth-welcome.html"
PASS=0
FAIL=0

check() {
  local desc="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "  PASS: $desc"
    PASS=$((PASS + 1))
  else
    echo "  FAIL: $desc"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== Booth Welcome Page Tests ==="
echo ""

# File exists
check "file exists" test -f "$FILE"

# Required content
check "header text"          grep -q "Welcome to.*BoothApp.*Demo" "$FILE"
check "QR placeholder"       grep -q "QR" "$FILE"
check "logo placeholder"     grep -q "LOGO\|logo" "$FILE"
check "pulse animation"      grep -q "@keyframes pulse" "$FILE"
check "S3 polling endpoint"  grep -q "active-session.json" "$FILE"
check "bucket reference"     grep -q "boothapp-sessions" "$FILE"
check "dark theme bg"        grep -q "0d1117" "$FILE"
check "recording state"      grep -q "RECORDING" "$FILE"
check "visitor name element" grep -q "visitor.name\|visitorName\|visitor_name" "$FILE"
check "elapsed timer"        grep -q "elapsed" "$FILE"
check "scan/follow-up text"  grep -q "Scan\|follow-up\|follow.up" "$FILE"

# Font size >= 1.4rem for readability (header should be 3+ rem)
check "large header font"    grep -q "font-size: [3-9]" "$FILE"
check "readable body text"   grep -q "font-size: 1\.[4-9]rem\|font-size: [2-9]" "$FILE"

# No build tool artifacts
check "no ES module imports" bash -c "! grep -q 'import .* from' '$FILE'"
check "no require() calls"  bash -c "! grep -q 'require(' '$FILE'"

# Valid HTML structure
check "has doctype"          grep -q "<!DOCTYPE html>" "$FILE"
check "closing html tag"     grep -q "</html>" "$FILE"
check "has style block"      grep -q "<style>" "$FILE"
check "has script block"     grep -q "<script>" "$FILE"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] || exit 1
