#!/usr/bin/env bash
# Tests for scripts/ccc-client.sh
# Validates: arg parsing, help, error handling, HTTP response parsing
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CLIENT="$SCRIPT_DIR/scripts/ccc-client.sh"
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
    echo "  FAIL: $desc (expected='$expected' actual='$actual')"
    FAIL=$((FAIL + 1))
  fi
}

assert_contains() {
  local desc="$1" needle="$2" haystack="$3"
  if echo "$haystack" | grep -qF "$needle"; then
    echo "  PASS: $desc"
    PASS=$((PASS + 1))
  else
    echo "  FAIL: $desc (expected to contain '$needle')"
    FAIL=$((FAIL + 1))
  fi
}

assert_exit() {
  local desc="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    echo "  PASS: $desc (exit=$expected)"
    PASS=$((PASS + 1))
  else
    echo "  FAIL: $desc (expected exit=$expected actual=$actual)"
    FAIL=$((FAIL + 1))
  fi
}

# ── Mock HTTP server ───────────────────────────────────────────────────────────

MOCK_PORT=0
MOCK_PID=0

start_mock_server() {
  local response_file="$1"
  # Python one-liner HTTP server that returns canned responses based on path
  python3 -c "
import http.server, json, sys, threading

response_file = '$response_file'

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _load_responses(self):
        with open(response_file) as f:
            return json.load(f)

    def _respond(self, method):
        responses = self._load_responses()
        key = method + ' ' + self.path.split('?')[0]
        # Also try with query string
        key_full = method + ' ' + self.path
        resp = responses.get(key_full) or responses.get(key) or responses.get('default')
        if not resp:
            self.send_response(404)
            self.end_headers()
            return
        code = resp.get('code', 200)
        body = json.dumps(resp.get('body', {})).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self): self._respond('GET')
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        self.rfile.read(length)
        self._respond('POST')
    def do_DELETE(self): self._respond('DELETE')

s = http.server.HTTPServer(('127.0.0.1', 0), H)
port = s.server_address[1]
sys.stdout.write(str(port) + '\n')
sys.stdout.flush()
s.serve_forever()
" &
  MOCK_PID=$!
  # Read the port from stdout
  read -r MOCK_PORT < /proc/$MOCK_PID/fd/1 2>/dev/null || sleep 0.5

  # Fallback: if we couldn't read from fd, find port via lsof
  if [[ "$MOCK_PORT" == "0" ]] || [[ -z "$MOCK_PORT" ]]; then
    sleep 0.5
    MOCK_PORT=$(python3 -c "
import http.server, json, sys
response_file = '$response_file'
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _load_responses(self):
        with open(response_file) as f: return json.load(f)
    def _respond(self, method):
        responses = self._load_responses()
        key = method + ' ' + self.path.split('?')[0]
        key_full = method + ' ' + self.path
        resp = responses.get(key_full) or responses.get(key) or responses.get('default')
        if not resp:
            self.send_response(404); self.end_headers(); return
        code = resp.get('code', 200)
        body = json.dumps(resp.get('body', {})).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self): self._respond('GET')
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0)); self.rfile.read(length); self._respond('POST')
    def do_DELETE(self): self._respond('DELETE')
s = http.server.HTTPServer(('127.0.0.1', 0), H)
print(s.server_address[1])
s.server_close()
" 2>/dev/null)
    # Kill the failed attempt and restart properly
    kill $MOCK_PID 2>/dev/null || true
    wait $MOCK_PID 2>/dev/null || true
    start_mock_server_simple "$response_file"
    return
  fi
}

start_mock_server_simple() {
  local response_file="$1"
  # Simpler approach: write port to a file
  local port_file="$TMPDIR/port"
  python3 "$TMPDIR/mock_server.py" "$response_file" "$port_file" &
  MOCK_PID=$!
  # Wait for port file
  local i=0
  while [[ ! -s "$port_file" ]] && [[ $i -lt 20 ]]; do
    sleep 0.1
    i=$((i + 1))
  done
  MOCK_PORT=$(cat "$port_file" 2>/dev/null || echo "0")
}

stop_mock_server() {
  if [[ $MOCK_PID -ne 0 ]]; then
    kill $MOCK_PID 2>/dev/null || true
    wait $MOCK_PID 2>/dev/null || true
    MOCK_PID=0
  fi
}

# Write the server script to a file for reliable startup
cat > "$TMPDIR/mock_server.py" << 'PYEOF'
import http.server, json, sys

response_file = sys.argv[1]
port_file = sys.argv[2]

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _load_responses(self):
        with open(response_file) as f:
            return json.load(f)
    def _respond(self, method):
        responses = self._load_responses()
        key = method + ' ' + self.path.split('?')[0]
        key_full = method + ' ' + self.path
        resp = responses.get(key_full) or responses.get(key) or responses.get('default')
        if not resp:
            self.send_response(404)
            self.end_headers()
            return
        code = resp.get('code', 200)
        body = json.dumps(resp.get('body', {})).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self): self._respond('GET')
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        self.rfile.read(length)
        self._respond('POST')
    def do_DELETE(self): self._respond('DELETE')

s = http.server.HTTPServer(('127.0.0.1', 0), H)
with open(port_file, 'w') as f:
    f.write(str(s.server_address[1]))
s.serve_forever()
PYEOF

start_mock() {
  local response_file="$1"
  local port_file="$TMPDIR/port"
  rm -f "$port_file"
  python3 "$TMPDIR/mock_server.py" "$response_file" "$port_file" &
  MOCK_PID=$!
  local i=0
  while [[ ! -s "$port_file" ]] && [[ $i -lt 30 ]]; do
    sleep 0.1
    i=$((i + 1))
  done
  MOCK_PORT=$(cat "$port_file" 2>/dev/null || echo "0")
  if [[ "$MOCK_PORT" == "0" ]]; then
    echo "FATAL: mock server failed to start" >&2
    exit 1
  fi
}

# ── Tests: arg validation ─────────────────────────────────────────────────────

echo "=== Arg validation tests ==="

out=$(bash "$CLIENT" 2>&1 || true)
assert_contains "no args shows usage" "Usage:" "$out"

out=$(bash "$CLIENT" help 2>&1 || true)
assert_contains "help shows usage" "Usage:" "$out"

out=$(bash "$CLIENT" submit 2>&1 || true)
assert_contains "submit no args shows error" "usage: ccc-client.sh submit" "$out"

out=$(bash "$CLIENT" status 2>&1 || true)
assert_contains "status no args shows error" "usage: ccc-client.sh status" "$out"

out=$(bash "$CLIENT" poll 2>&1 || true)
assert_contains "poll no args shows error" "usage: ccc-client.sh poll" "$out"

out=$(bash "$CLIENT" cancel 2>&1 || true)
assert_contains "cancel no args shows error" "usage: ccc-client.sh cancel" "$out"

# ── Tests: connection error ────────────────────────────────────────────────────

echo ""
echo "=== Connection error tests ==="

out=$(CCC_API_URL="http://127.0.0.1:19999" bash "$CLIENT" workers 2>&1 || true)
assert_contains "workers connection error" "connection failed" "$out"

out=$(CCC_API_URL="http://127.0.0.1:19999" bash "$CLIENT" submit "test" 2>&1 || true)
assert_contains "submit connection error" "connection failed" "$out"

out=$(CCC_API_URL="http://127.0.0.1:19999" bash "$CLIENT" status abc 2>&1 || true)
assert_contains "status connection error" "connection failed" "$out"

# ── Tests: submit ──────────────────────────────────────────────────────────────

echo ""
echo "=== Submit tests ==="

cat > "$TMPDIR/submit_resp.json" << 'JSON'
{
  "POST /task": {
    "code": 201,
    "body": {"id": "test-uuid-123", "state": "PENDING", "text": "do something"}
  }
}
JSON

start_mock "$TMPDIR/submit_resp.json"
out=$(CCC_API_URL="http://127.0.0.1:$MOCK_PORT" bash "$CLIENT" submit "do something" 2>&1)
assert_contains "submit prints task id" "test-uuid-123" "$out"
assert_contains "submit prints state" "PENDING" "$out"
stop_mock_server

# Submit with auth error
cat > "$TMPDIR/submit_401.json" << 'JSON'
{
  "POST /task": {
    "code": 401,
    "body": {"error": "unauthorized"}
  }
}
JSON

start_mock "$TMPDIR/submit_401.json"
out=$(CCC_API_URL="http://127.0.0.1:$MOCK_PORT" bash "$CLIENT" submit "test" 2>&1 || true)
assert_contains "submit 401 shows auth error" "unauthorized" "$out"
stop_mock_server

# ── Tests: status ──────────────────────────────────────────────────────────────

echo ""
echo "=== Status tests ==="

cat > "$TMPDIR/status_resp.json" << 'JSON'
{
  "GET /task/abc-123": {
    "code": 200,
    "body": {
      "id": "abc-123",
      "state": "RUNNING",
      "text": "refactor auth",
      "dispatched_at": "2026-03-30T10:00:00Z"
    }
  }
}
JSON

start_mock "$TMPDIR/status_resp.json"
out=$(CCC_API_URL="http://127.0.0.1:$MOCK_PORT" bash "$CLIENT" status abc-123 2>&1)
assert_contains "status shows task id" "abc-123" "$out"
assert_contains "status shows state" "RUNNING" "$out"
assert_contains "status shows text" "refactor auth" "$out"
assert_contains "status shows dispatched" "2026-03-30T10:00:00Z" "$out"
stop_mock_server

# Status 404
cat > "$TMPDIR/status_404.json" << 'JSON'
{
  "GET /task/nonexistent": {
    "code": 404,
    "body": {"error": "not found"}
  }
}
JSON

start_mock "$TMPDIR/status_404.json"
out=$(CCC_API_URL="http://127.0.0.1:$MOCK_PORT" bash "$CLIENT" status nonexistent 2>&1 || true)
assert_contains "status 404 shows not found" "not found" "$out"
stop_mock_server

# ── Tests: cancel ──────────────────────────────────────────────────────────────

echo ""
echo "=== Cancel tests ==="

cat > "$TMPDIR/cancel_resp.json" << 'JSON'
{
  "DELETE /task/abc-123": {
    "code": 200,
    "body": {"id": "abc-123", "state": "CANCELLED"}
  }
}
JSON

start_mock "$TMPDIR/cancel_resp.json"
out=$(CCC_API_URL="http://127.0.0.1:$MOCK_PORT" bash "$CLIENT" cancel abc-123 2>&1)
assert_contains "cancel shows cancelled" "cancelled" "$out"
stop_mock_server

# Cancel 409 (already completed)
cat > "$TMPDIR/cancel_409.json" << 'JSON'
{
  "DELETE /task/done-task": {
    "code": 409,
    "body": {"error": "Cannot cancel task in COMPLETED state"}
  }
}
JSON

start_mock "$TMPDIR/cancel_409.json"
out=$(CCC_API_URL="http://127.0.0.1:$MOCK_PORT" bash "$CLIENT" cancel done-task 2>&1 || true)
assert_contains "cancel 409 shows error" "cannot cancel" "$out"
stop_mock_server

# ── Tests: workers ─────────────────────────────────────────────────────────────

echo ""
echo "=== Workers tests ==="

cat > "$TMPDIR/workers_resp.json" << 'JSON'
{
  "GET /api/workers": {
    "code": 200,
    "body": {
      "worker-1": {
        "status": "idle",
        "tasks_completed": 5,
        "tasks_failed": 1,
        "registered_at": "2026-03-30T08:00:00Z",
        "current_task_id": null
      },
      "worker-2": {
        "status": "busy",
        "tasks_completed": 3,
        "tasks_failed": 0,
        "registered_at": "2026-03-30T09:00:00Z",
        "current_task_id": "task-xyz"
      }
    }
  }
}
JSON

start_mock "$TMPDIR/workers_resp.json"
out=$(CCC_API_URL="http://127.0.0.1:$MOCK_PORT" bash "$CLIENT" workers 2>&1)
assert_contains "workers shows worker-1" "worker-1" "$out"
assert_contains "workers shows worker-2" "worker-2" "$out"
assert_contains "workers shows idle" "idle" "$out"
assert_contains "workers shows busy" "busy" "$out"
assert_contains "workers shows count" "2 worker(s)" "$out"
stop_mock_server

# Empty workers
cat > "$TMPDIR/workers_empty.json" << 'JSON'
{
  "GET /api/workers": {
    "code": 200,
    "body": {}
  }
}
JSON

start_mock "$TMPDIR/workers_empty.json"
out=$(CCC_API_URL="http://127.0.0.1:$MOCK_PORT" bash "$CLIENT" workers 2>&1)
assert_contains "empty workers shows message" "No workers registered" "$out"
stop_mock_server

# ── Tests: tasks ───────────────────────────────────────────────────────────────

echo ""
echo "=== Tasks tests ==="

cat > "$TMPDIR/tasks_resp.json" << 'JSON'
{
  "GET /tasks": {
    "code": 200,
    "body": {
      "tasks": [
        {"id": "t1", "state": "COMPLETED", "created_at": "2026-03-30T10:00:00Z", "text": "first task"},
        {"id": "t2", "state": "PENDING", "created_at": "2026-03-30T11:00:00Z", "text": "second task"}
      ],
      "count": 2
    }
  }
}
JSON

start_mock "$TMPDIR/tasks_resp.json"
out=$(CCC_API_URL="http://127.0.0.1:$MOCK_PORT" bash "$CLIENT" tasks 2>&1)
assert_contains "tasks shows t1" "t1" "$out"
assert_contains "tasks shows t2" "t2" "$out"
assert_contains "tasks shows count" "2 task(s)" "$out"
stop_mock_server

# Empty tasks
cat > "$TMPDIR/tasks_empty.json" << 'JSON'
{
  "GET /tasks": {
    "code": 200,
    "body": {"tasks": [], "count": 0}
  }
}
JSON

start_mock "$TMPDIR/tasks_empty.json"
out=$(CCC_API_URL="http://127.0.0.1:$MOCK_PORT" bash "$CLIENT" tasks 2>&1)
assert_contains "empty tasks shows message" "No tasks found" "$out"
stop_mock_server

# ── Tests: poll (immediate completion) ─────────────────────────────────────────

echo ""
echo "=== Poll tests ==="

cat > "$TMPDIR/poll_done.json" << 'JSON'
{
  "GET /task/poll-test": {
    "code": 200,
    "body": {
      "id": "poll-test",
      "state": "COMPLETED",
      "result": "PR merged",
      "completed_at": "2026-03-30T12:00:00Z"
    }
  }
}
JSON

start_mock "$TMPDIR/poll_done.json"
out=$(CCC_API_URL="http://127.0.0.1:$MOCK_PORT" CCC_POLL_TIMEOUT=5 bash "$CLIENT" poll poll-test 2>&1)
rc=$?
assert_eq "poll completed exits 0" "0" "$rc"
assert_contains "poll shows completed" "Task completed" "$out"
assert_contains "poll shows result" "PR merged" "$out"
stop_mock_server

# Poll with failure
cat > "$TMPDIR/poll_fail.json" << 'JSON'
{
  "GET /task/fail-test": {
    "code": 200,
    "body": {
      "id": "fail-test",
      "state": "FAILED",
      "error": "build broken",
      "completed_at": "2026-03-30T12:00:00Z"
    }
  }
}
JSON

start_mock "$TMPDIR/poll_fail.json"
out=$(CCC_API_URL="http://127.0.0.1:$MOCK_PORT" CCC_POLL_TIMEOUT=5 bash "$CLIENT" poll fail-test 2>&1 || true)
assert_contains "poll failed shows error" "Task failed" "$out"
assert_contains "poll failed shows reason" "build broken" "$out"
stop_mock_server

# ── Tests: auth token passed correctly ─────────────────────────────────────────

echo ""
echo "=== Auth token tests ==="

# The mock server doesn't validate auth, but we verify the client doesn't crash
# when CCC_API_TOKEN is set (the earlier bug was token with spaces breaking curl)
cat > "$TMPDIR/auth_resp.json" << 'JSON'
{
  "GET /api/workers": {
    "code": 200,
    "body": {"worker-1": {"status": "idle", "tasks_completed": 0, "tasks_failed": 0}}
  }
}
JSON

start_mock "$TMPDIR/auth_resp.json"
out=$(CCC_API_URL="http://127.0.0.1:$MOCK_PORT" CCC_API_TOKEN="my-secret-token" bash "$CLIENT" workers 2>&1)
rc=$?
assert_eq "token auth doesn't break curl" "0" "$rc"
assert_contains "token auth returns data" "worker-1" "$out"
stop_mock_server

# ── Summary ────────────────────────────────────────────────────────────────────

echo ""
echo "=============================="
echo "  $PASS passed, $FAIL failed"
echo "=============================="

# Stop any running mock before exit to prevent signal-based exit codes
stop_mock_server
[[ $FAIL -eq 0 ]] || exit 1
exit 0
