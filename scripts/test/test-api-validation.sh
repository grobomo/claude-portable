#!/usr/bin/env bash
# test-api-validation.sh -- validate input validation on dispatcher API endpoints
#
# Usage: bash scripts/test/test-api-validation.sh [port]
#
# Starts git-dispatch.py on a random port, runs validation tests, then kills it.
# Exit 0 = all pass, exit 1 = failures.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
DISPATCH="$REPO_DIR/scripts/git-dispatch.py"

PORT="${1:-0}"
PASS=0
FAIL=0
TOTAL=0

# ── Helpers ────────────────────────────────────────────────────────────────────

log()  { printf "[TEST] %s\n" "$*"; }
pass() { PASS=$((PASS + 1)); TOTAL=$((TOTAL + 1)); log "PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); TOTAL=$((TOTAL + 1)); log "FAIL: $1 -- $2"; }

# POST JSON and capture status + body
post() {
    local path="$1" data="$2"
    local tmpfile
    tmpfile=$(mktemp)
    local status
    status=$(curl -s -o "$tmpfile" -w "%{http_code}" \
        -X POST "http://127.0.0.1:$PORT$path" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $TOKEN" \
        -d "$data" 2>/dev/null)
    LAST_STATUS="$status"
    LAST_BODY=$(cat "$tmpfile")
    rm -f "$tmpfile"
}

assert_status() {
    local expected="$1" label="$2"
    if [ "$LAST_STATUS" = "$expected" ]; then
        pass "$label"
    else
        fail "$label" "expected status $expected, got $LAST_STATUS (body: $LAST_BODY)"
    fi
}

assert_field_error() {
    local field="$1" label="$2"
    if echo "$LAST_BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert '$field' in d.get('fields', {}), 'field not in errors'
" 2>/dev/null; then
        pass "$label"
    else
        fail "$label" "expected field error for '$field' in: $LAST_BODY"
    fi
}

# ── Start dispatcher ──────────────────────────────────────────────────────────

TOKEN="test-validation-token-$$"

# Find a free port if not specified
if [ "$PORT" = "0" ]; then
    PORT=$(python3 -c "import socket; s=socket.socket(); s.bind(('',0)); print(s.getsockname()[1]); s.close()")
fi

log "Starting dispatcher on port $PORT..."
DISPATCH_API_TOKEN="$TOKEN" \
DISPATCHER_HEALTH_PORT="$PORT" \
DISPATCHER_REPO_DIR="$REPO_DIR" \
DRY_RUN=1 \
    python3 "$DISPATCH" --no-poll &
DISPATCH_PID=$!

cleanup() {
    kill "$DISPATCH_PID" 2>/dev/null || true
    wait "$DISPATCH_PID" 2>/dev/null || true
}
trap cleanup EXIT

# Wait for server to be ready
for i in $(seq 1 30); do
    if curl -s "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
        break
    fi
    sleep 0.2
done

log "Dispatcher ready (pid=$DISPATCH_PID)"
echo

# ══════════════════════════════════════════════════════════════════════════════
# TEST: POST /worker/register validation
# ══════════════════════════════════════════════════════════════════════════════

log "=== /worker/register ==="

# Bad name (doesn't match hackathon26-worker-N)
post "/worker/register" '{"name": "bad-worker", "ip": "172.31.1.1"}'
assert_status "400" "register: bad name rejected"
assert_field_error "name" "register: name field error present"

# Missing name
post "/worker/register" '{"ip": "172.31.1.1"}'
assert_status "400" "register: missing name rejected"

# Bad IP (not 172.31.x.x)
post "/worker/register" '{"name": "hackathon26-worker-1", "ip": "10.0.0.1"}'
assert_status "400" "register: bad IP rejected"
assert_field_error "ip" "register: ip field error present"

# Missing IP
post "/worker/register" '{"name": "hackathon26-worker-1"}'
assert_status "400" "register: missing IP rejected"

# Both bad
post "/worker/register" '{"name": "x", "ip": "1.2.3.4"}'
assert_status "400" "register: both bad rejected"

# Valid registration
post "/worker/register" '{"name": "hackathon26-worker-1", "ip": "172.31.0.1"}'
assert_status "200" "register: valid worker accepted"

# Valid with worker_id key
post "/worker/register" '{"worker_id": "hackathon26-worker-2", "ip": "172.31.10.50"}'
assert_status "200" "register: valid worker_id key accepted"

echo

# ══════════════════════════════════════════════════════════════════════════════
# TEST: POST /task (submit) validation
# ══════════════════════════════════════════════════════════════════════════════

log "=== /task (submit) ==="

# Missing text
post "/task" '{"sender": "joel"}'
assert_status "400" "submit: missing text rejected"
assert_field_error "text" "submit: text field error present"

# Empty text
post "/task" '{"text": "", "sender": "joel"}'
assert_status "400" "submit: empty text rejected"

# Missing sender
post "/task" '{"text": "do something"}'
assert_status "400" "submit: missing sender rejected"
assert_field_error "sender" "submit: sender field error present"

# Both missing
post "/task" '{}'
assert_status "400" "submit: both missing rejected"

# Invalid priority
post "/task" '{"text": "do it", "sender": "joel", "priority": "mega"}'
assert_status "400" "submit: bad priority rejected"
assert_field_error "priority" "submit: priority field error present"

# Valid submission
post "/task" '{"text": "refactor auth", "sender": "joel"}'
assert_status "201" "submit: valid task accepted"

echo

# ══════════════════════════════════════════════════════════════════════════════
# TEST: POST /worker/report validation
# ══════════════════════════════════════════════════════════════════════════════

log "=== /worker/report ==="

# Missing worker_id
post "/worker/report" '{"status": "idle"}'
assert_status "400" "report: missing worker_id rejected"
assert_field_error "worker_id" "report: worker_id field error present"

# Worker not in roster
post "/worker/report" '{"worker_id": "hackathon26-worker-99", "status": "idle"}'
assert_status "400" "report: unknown worker rejected"
assert_field_error "worker_id" "report: unknown worker field error"

# Invalid status
post "/worker/report" '{"worker_id": "hackathon26-worker-1", "status": "sleeping"}'
assert_status "400" "report: bad status rejected"
assert_field_error "status" "report: status field error present"

# Missing status
post "/worker/report" '{"worker_id": "hackathon26-worker-1"}'
assert_status "400" "report: missing status rejected"

# Valid report (worker-1 was registered above)
post "/worker/report" '{"worker_id": "hackathon26-worker-1", "status": "busy"}'
assert_status "200" "report: valid report accepted"

# Valid report with message
post "/worker/report" '{"worker_id": "hackathon26-worker-1", "status": "idle", "message": "task done"}'
assert_status "200" "report: valid report with message accepted"

echo

# ══════════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════════

echo "============================================"
echo "  Results: $PASS passed, $FAIL failed ($TOTAL total)"
echo "============================================"

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
exit 0
