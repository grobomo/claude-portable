#!/bin/bash
# E2E test for claude-portable: launches an instance, validates all features, tears down.
# Usage: bash test.sh [--keep]   (--keep skips teardown for manual inspection)
set -euo pipefail

INSTANCE_NAME="test-e2e"
KEEP="${1:-}"
PASS=0
FAIL=0
RESULTS=()

# ── Helpers ──────────────────────────────────────────────────────────────────

pass() { PASS=$((PASS + 1)); RESULTS+=("PASS  $1"); echo "  PASS  $1"; }
fail() { FAIL=$((FAIL + 1)); RESULTS+=("FAIL  $1: $2"); echo "  FAIL  $1: $2"; }

ssh_cmd() {
  local IP="$1"; shift
  ssh -i "$KEY_PATH" -o StrictHostKeyChecking=no -o ConnectTimeout=10 "ubuntu@$IP" "$@" 2>&1
}

docker_exec() {
  local IP="$1"; shift
  ssh_cmd "$IP" "docker exec claude-portable bash -c '$*'"
}

cleanup() {
  if [ "$KEEP" = "--keep" ]; then
    echo ""
    echo "  --keep: Instance left running. Clean up with: ccp kill $INSTANCE_NAME"
    return
  fi
  echo ""
  echo "=== Teardown ==="
  ccp kill "$INSTANCE_NAME" 2>/dev/null || true
}

# ── Pre-flight ───────────────────────────────────────────────────────────────

echo "========================================="
echo "  Claude Portable E2E Test"
echo "========================================="
echo ""

# Check prerequisites
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CCP="$SCRIPT_DIR/cpp"
PY="python3"

if ! $PY "$CCP" list &>/dev/null; then
  echo "ERROR: ccp not working. Check .env and AWS credentials."
  exit 1
fi

# Syntax check all scripts
echo "=== Pre-flight: Syntax checks ==="
for f in "$SCRIPT_DIR"/scripts/*.sh; do
  if bash -n "$f" 2>/dev/null; then
    pass "syntax: $(basename "$f")"
  else
    fail "syntax: $(basename "$f")" "bash -n failed"
  fi
done
echo ""

# ── Launch ───────────────────────────────────────────────────────────────────

echo "=== Launch instance ==="
# Kill any existing test instance
ccp kill "$INSTANCE_NAME" 2>/dev/null || true

OUTPUT=$($PY "$CCP" --name "$INSTANCE_NAME" 2>&1 || true)
echo "$OUTPUT"

# Extract IP from ccp output or from list
IP=$($PY "$CCP" list 2>/dev/null | grep "$INSTANCE_NAME" | awk '{print $4}')
KEY_PATH="$HOME/.ssh/cpp-keys/${INSTANCE_NAME}.pem"

if [ -z "$IP" ]; then
  fail "launch" "No IP found for $INSTANCE_NAME"
  echo ""
  echo "=== Results ==="
  printf '%s\n' "${RESULTS[@]}"
  echo ""
  echo "PASS: $PASS  FAIL: $FAIL"
  exit 1
fi

echo "  Instance IP: $IP"
echo ""
trap cleanup EXIT

# Wait for container to be healthy (may still be starting)
echo "=== Waiting for container ==="
for i in $(seq 1 30); do
  if ssh_cmd "$IP" 'docker ps --format "{{.Names}} {{.Status}}"' 2>/dev/null | grep -q "claude-portable.*Up"; then
    break
  fi
  echo -n "."
  sleep 10
done
echo ""

# ── Test: Bootstrap =════════════════════════════════════════════════════════

echo "=== Test: Bootstrap ==="
LOGS=$(ssh_cmd "$IP" 'docker logs claude-portable 2>&1')

if echo "$LOGS" | grep -q "Claude Portable Ready"; then
  pass "bootstrap completes"
else
  fail "bootstrap" "No 'Claude Portable Ready' in logs"
fi

if echo "$LOGS" | grep -q "OAuth credentials present"; then
  pass "auth: OAuth configured"
else
  fail "auth" "OAuth not detected in bootstrap"
fi

echo ""

# ── Test: Idle monitor ═══════════════════════════════════════════════════════

echo "=== Test: Idle monitor ==="
IDLE_PS=$(docker_exec "$IP" "ps aux | grep idle-monitor | grep -v grep" || true)
if echo "$IDLE_PS" | grep -q "idle-monitor"; then
  pass "idle-monitor: process running"
else
  fail "idle-monitor" "process not found"
fi

if echo "$LOGS" | grep -q "Starting idle monitor"; then
  pass "idle-monitor: started by bootstrap"
else
  fail "idle-monitor" "not started by bootstrap"
fi

if echo "$LOGS" | grep -q "30min"; then
  pass "idle-monitor: 30min timeout configured"
else
  fail "idle-monitor" "timeout not shown in logs"
fi

echo ""

# ── Test: S3 state sync ═════════════════════════════════════════════════════

echo "=== Test: S3 state sync ==="
SYNC_PS=$(docker_exec "$IP" "ps aux | grep state-sync | grep -v grep" || true)
if echo "$SYNC_PS" | grep -q "state-sync.*auto"; then
  pass "state-sync: auto-sync daemon running"
else
  fail "state-sync" "auto-sync daemon not found"
fi

if echo "$LOGS" | grep -q "auto-sync"; then
  pass "state-sync: started by bootstrap"
else
  fail "state-sync" "not started by bootstrap"
fi

# Check S3 last-sync marker
LAST_SYNC=$(docker_exec "$IP" "aws s3 cp s3://claude-portable-state-\\\$(aws sts get-caller-identity --query Account --output text)/claude-state/.last-sync.json - 2>/dev/null" || true)
if echo "$LAST_SYNC" | grep -q '"synced"'; then
  pass "state-sync: S3 marker present"
else
  fail "state-sync" "no .last-sync.json in S3"
fi

echo ""

# ── Test: Credential refresh ════════════════════════════════════════════════

echo "=== Test: Credential refresh ==="
CRED_PS=$(docker_exec "$IP" "ps aux | grep cred-refresh | grep -v grep" || true)
if echo "$CRED_PS" | grep -q "cred-refresh"; then
  pass "cred-refresh: daemon running"
else
  fail "cred-refresh" "daemon not found"
fi

echo ""

# ── Test: Browser/VNC ═══════════════════════════════════════════════════════

echo "=== Test: Browser ==="
if echo "$LOGS" | grep -q "Chrome running"; then
  pass "browser: Chrome started"
else
  fail "browser" "Chrome not running"
fi

if echo "$LOGS" | grep -q "VNC on port 5900"; then
  pass "browser: VNC running"
else
  fail "browser" "VNC not running"
fi

echo ""

# ── Test: Session storage ═══════════════════════════════════════════════════

echo "=== Test: Sessions ==="
SESSION_DIR=$(docker_exec "$IP" "ls -d /data/sessions 2>/dev/null" || true)
if echo "$SESSION_DIR" | grep -q "/data/sessions"; then
  pass "sessions: /data/sessions exists"
else
  fail "sessions" "/data/sessions missing"
fi

echo ""

# ── Test: Health check ══════════════════════════════════════════════════════

echo "=== Test: Health check ==="
HEALTH=$(docker_exec "$IP" "/opt/claude-portable/scripts/health-check.sh 2>/dev/null" || true)
if echo "$HEALTH" | grep -qi "healthy"; then
  pass "health-check: HEALTHY"
else
  fail "health-check" "not healthy: $(echo "$HEALTH" | tail -1)"
fi

echo ""

# ── Summary ══════════════════════════════════════════════════════════════════

echo "========================================="
echo "  Results"
echo "========================================="
printf '  %s\n' "${RESULTS[@]}"
echo ""
echo "  PASS: $PASS  FAIL: $FAIL"
echo ""

if [ "$FAIL" -gt 0 ]; then
  echo "  Some tests failed. Instance: $IP"
  exit 1
fi
