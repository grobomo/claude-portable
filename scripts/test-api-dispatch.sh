#!/bin/bash
# Integration test for the API dispatch system.
#
# Validates core dispatch endpoints:
#   1. GET  /health              -> 200
#   2. POST /task                -> returns task_id (auth required)
#   3. GET  /task/{id}           -> PENDING status
#   4. POST /worker/heartbeat    -> updates worker status
#   5. GET  /tasks?status=pending -> lists the task
#   6. Unauthenticated requests  -> 401
#   7. Invalid task ID           -> 404
#
# Usage:
#   DISPATCHER_URL=http://localhost:8080 DISPATCH_API_TOKEN=secret \
#     bash scripts/test-api-dispatch.sh
#
# Required env vars:
#   DISPATCHER_URL       Base URL of the dispatcher (e.g. http://localhost:8080)
#   DISPATCH_API_TOKEN   Bearer token for authenticated requests
set -uo pipefail

# ── Config ────────────────────────────────────────────────────────────────────

if [ -z "${DISPATCHER_URL:-}" ]; then
  echo "ERROR: DISPATCHER_URL not set (e.g. http://localhost:8080)"
  exit 2
fi

if [ -z "${DISPATCH_API_TOKEN:-}" ]; then
  echo "ERROR: DISPATCH_API_TOKEN not set"
  exit 2
fi

BASE_URL="${DISPATCHER_URL%/}"
AUTH_HEADER="Authorization: Bearer ${DISPATCH_API_TOKEN}"
CURL_OPTS="-s --max-time 10"

PASS=0
FAIL=0
RESULTS=()

# ── Helpers ───────────────────────────────────────────────────────────────────

pass() {
  PASS=$((PASS + 1))
  RESULTS+=("  PASS  $1")
  echo "  PASS  $1"
}

fail() {
  FAIL=$((FAIL + 1))
  RESULTS+=("  FAIL  $1: $2")
  echo "  FAIL  $1: $2"
}

# Extract HTTP status code from curl output (last line when using -w)
http_get() {
  local url="$1"; shift
  curl $CURL_OPTS -w '\n%{http_code}' "$@" "$url"
}

http_post() {
  local url="$1"; local data="$2"; shift 2
  curl $CURL_OPTS -w '\n%{http_code}' -X POST \
    -H "Content-Type: application/json" \
    -d "$data" "$@" "$url"
}

# Split curl output into body + status code
parse_response() {
  local raw="$1"
  HTTP_BODY=$(echo "$raw" | sed '$d')
  HTTP_CODE=$(echo "$raw" | tail -1)
}

echo "================================================="
echo "  API Dispatch Integration Tests"
echo "  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "  Target: ${BASE_URL}"
echo "================================================="
echo ""

# ── Test 1: Health endpoint returns 200 ───────────────────────────────────────

echo "=== 1. Health endpoint ==="

RAW=$(http_get "${BASE_URL}/health")
parse_response "$RAW"

if [ "$HTTP_CODE" = "200" ]; then
  pass "GET /health returns 200"
else
  fail "GET /health" "expected 200, got ${HTTP_CODE}"
fi

# Verify response is valid JSON with a status field
if echo "$HTTP_BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); assert 'status' in d or 'uptime_seconds' in d" 2>/dev/null; then
  pass "GET /health returns valid JSON with status"
else
  fail "GET /health JSON" "response is not valid JSON or missing status field"
fi

echo ""

# ── Test 2: POST /task returns task ID (authenticated) ────────────────────────

echo "=== 2. Create task ==="

TASK_PAYLOAD='{"prompt":"integration test task","repo":"test/repo","branch":"main"}'

RAW=$(http_post "${BASE_URL}/task" "$TASK_PAYLOAD" -H "$AUTH_HEADER")
parse_response "$RAW"

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "201" ]; then
  pass "POST /task returns ${HTTP_CODE}"
else
  fail "POST /task" "expected 200 or 201, got ${HTTP_CODE}"
fi

TASK_ID=$(echo "$HTTP_BODY" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('task_id', d.get('id', '')))
except Exception:
    print('')
" 2>/dev/null)

if [ -n "$TASK_ID" ]; then
  pass "POST /task returned task_id: ${TASK_ID}"
else
  fail "POST /task task_id" "no task_id in response body"
  # Use a placeholder so subsequent tests can still run (and fail gracefully)
  TASK_ID="nonexistent-test-id"
fi

echo ""

# ── Test 3: GET /task/{id} shows PENDING status ──────────────────────────────

echo "=== 3. Get task status ==="

RAW=$(http_get "${BASE_URL}/task/${TASK_ID}" -H "$AUTH_HEADER")
parse_response "$RAW"

if [ "$HTTP_CODE" = "200" ]; then
  pass "GET /task/${TASK_ID} returns 200"
else
  fail "GET /task/${TASK_ID}" "expected 200, got ${HTTP_CODE}"
fi

TASK_STATUS=$(echo "$HTTP_BODY" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('status', '').lower())
except Exception:
    print('')
" 2>/dev/null)

if [ "$TASK_STATUS" = "pending" ]; then
  pass "GET /task/${TASK_ID} status is PENDING"
else
  fail "GET /task/${TASK_ID} status" "expected 'pending', got '${TASK_STATUS}'"
fi

echo ""

# ── Test 4: POST /worker/heartbeat updates worker status ─────────────────────

echo "=== 4. Worker heartbeat ==="

HEARTBEAT_PAYLOAD='{"worker_id":"test-worker-integ","claude_running":true,"idle_seconds":0}'

RAW=$(http_post "${BASE_URL}/worker/heartbeat" "$HEARTBEAT_PAYLOAD" -H "$AUTH_HEADER")
parse_response "$RAW"

if [ "$HTTP_CODE" = "200" ]; then
  pass "POST /worker/heartbeat returns 200"
else
  fail "POST /worker/heartbeat" "expected 200, got ${HTTP_CODE}"
fi

HB_STATUS=$(echo "$HTTP_BODY" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('status', ''))
except Exception:
    print('')
" 2>/dev/null)

if [ "$HB_STATUS" = "ok" ]; then
  pass "POST /worker/heartbeat status is ok"
else
  fail "POST /worker/heartbeat response" "expected status='ok', got '${HB_STATUS}'"
fi

echo ""

# ── Test 5: GET /tasks?status=pending lists the task ─────────────────────────

echo "=== 5. List pending tasks ==="

RAW=$(http_get "${BASE_URL}/tasks?status=pending" -H "$AUTH_HEADER")
parse_response "$RAW"

if [ "$HTTP_CODE" = "200" ]; then
  pass "GET /tasks?status=pending returns 200"
else
  fail "GET /tasks?status=pending" "expected 200, got ${HTTP_CODE}"
fi

FOUND_TASK=$(echo "$HTTP_BODY" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    tasks = d if isinstance(d, list) else d.get('tasks', [])
    ids = [t.get('task_id', t.get('id', '')) for t in tasks]
    print('found' if '${TASK_ID}' in ids else 'not_found')
except Exception:
    print('parse_error')
" 2>/dev/null)

if [ "$FOUND_TASK" = "found" ]; then
  pass "GET /tasks?status=pending contains task ${TASK_ID}"
else
  fail "GET /tasks?status=pending" "task ${TASK_ID} not found in pending list (${FOUND_TASK})"
fi

echo ""

# ── Test 6: Unauthenticated requests return 401 ─────────────────────────────

echo "=== 6. Auth enforcement ==="

# POST /task without token
RAW=$(http_post "${BASE_URL}/task" "$TASK_PAYLOAD")
parse_response "$RAW"

if [ "$HTTP_CODE" = "401" ]; then
  pass "POST /task without auth returns 401"
else
  fail "POST /task no-auth" "expected 401, got ${HTTP_CODE}"
fi

# GET /tasks without token
RAW=$(http_get "${BASE_URL}/tasks?status=pending")
parse_response "$RAW"

if [ "$HTTP_CODE" = "401" ]; then
  pass "GET /tasks without auth returns 401"
else
  fail "GET /tasks no-auth" "expected 401, got ${HTTP_CODE}"
fi

# GET /task/{id} without token
RAW=$(http_get "${BASE_URL}/task/${TASK_ID}")
parse_response "$RAW"

if [ "$HTTP_CODE" = "401" ]; then
  pass "GET /task/{id} without auth returns 401"
else
  fail "GET /task/{id} no-auth" "expected 401, got ${HTTP_CODE}"
fi

echo ""

# ── Test 7: Invalid task ID returns 404 ──────────────────────────────────────

echo "=== 7. Invalid task ID ==="

RAW=$(http_get "${BASE_URL}/task/nonexistent-id-99999" -H "$AUTH_HEADER")
parse_response "$RAW"

if [ "$HTTP_CODE" = "404" ]; then
  pass "GET /task/nonexistent-id-99999 returns 404"
else
  fail "GET /task/nonexistent-id-99999" "expected 404, got ${HTTP_CODE}"
fi

echo ""

# ── Cleanup: deregister test worker ──────────────────────────────────────────

http_post "${BASE_URL}/worker/deregister" '{"worker_id":"test-worker-integ"}' \
  -H "$AUTH_HEADER" >/dev/null 2>&1 || true

# ── Summary ───────────────────────────────────────────────────────────────────

TOTAL=$((PASS + FAIL))
echo "================================================="
echo "  Results: ${PASS}/${TOTAL} passed, ${FAIL} failed"
echo "================================================="
for r in "${RESULTS[@]}"; do
  echo "$r"
done
echo ""

if [ "$FAIL" -gt 0 ]; then
  echo "FAILED: ${FAIL} test(s) did not pass."
  exit 1
else
  echo "ALL TESTS PASSED."
  exit 0
fi
