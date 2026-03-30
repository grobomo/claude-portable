#!/usr/bin/env bash
# Test that _drain_task_store exists in git-dispatch.py
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
COUNT=$(grep -c '_drain_task_store' "$SCRIPT_DIR/scripts/git-dispatch.py")
if [ "$COUNT" -gt 0 ]; then
  echo "PASS: _drain_task_store found ($COUNT refs)"
  exit 0
else
  echo "FAIL: _drain_task_store not found"
  exit 1
fi
