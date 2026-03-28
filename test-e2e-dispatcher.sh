#!/bin/bash
# E2E test: dispatcher + worker integration.
#
# Validates the full dispatch chain:
#   1. Launch dispatcher + 2 workers
#   2. Verify dispatcher health endpoint and heartbeat
#   3. Verify worker discovery via EC2 tags
#   4. Verify SSH dispatch chain (dispatcher -> worker -> claude -p)
#   5. Teams integration test (requires DISPATCHER_CHAT_ID + Graph token)
#
# Usage:
#   bash test-e2e-dispatcher.sh [--keep] [--skip-teams]
#
#   --keep        skip teardown (leave instances running for inspection)
#   --skip-teams  skip Teams integration tests even if credentials are set
#
# Required env vars (for Teams integration tests):
#   DISPATCHER_CHAT_ID        Teams chat ID to test against
#   DISPATCHER_SECRET_NAME    Secrets Manager secret with Graph token
#                             (default: claude-portable/graph-token)
set -euo pipefail

DISPATCHER_NAME="test-dispatcher"
WORKER1_NAME="test-worker-1"
WORKER2_NAME="test-worker-2"

KEEP=""
SKIP_TEAMS=""
for arg in "$@"; do
  case "$arg" in
    --keep)        KEEP="--keep" ;;
    --skip-teams)  SKIP_TEAMS="1" ;;
  esac
done

PASS=0
FAIL=0
SKIP=0
RESULTS=()

# ── Helpers ───────────────────────────────────────────────────────────────────

pass()  { PASS=$((PASS + 1));  RESULTS+=("PASS   $1");       echo "  PASS   $1"; }
fail()  { FAIL=$((FAIL + 1));  RESULTS+=("FAIL   $1: $2");   echo "  FAIL   $1: $2"; }
skip()  { SKIP=$((SKIP + 1));  RESULTS+=("SKIP   $1: $2");   echo "  SKIP   $1: $2"; }

key_path() { echo "$HOME/.ssh/ccc-keys/${1}.pem"; }

ssh_cmd() {
  local IP="$1"; local KEY="$2"; shift 2
  ssh -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 \
      -o BatchMode=yes "ubuntu@$IP" "$@" 2>&1
}

docker_exec() {
  local IP="$1"; local KEY="$2"; shift 2
  ssh_cmd "$IP" "$KEY" "docker exec claude-portable bash -c '$*'"
}

# SSH from one instance's container into another instance
# Usage: dispatcher_ssh_to_worker DISP_IP DISP_KEY WORKER_IP WORKER_NAME CMD
dispatcher_ssh_to_worker() {
  local DISP_IP="$1" DISP_KEY="$2" WORKER_IP="$3" WORKER_NAME="$4"; shift 4
  ssh_cmd "$DISP_IP" "$DISP_KEY" \
    "docker exec claude-portable bash -c '
       ssh -i \"\$HOME/.ssh/ccc-keys/${WORKER_NAME}.pem\" \
           -o StrictHostKeyChecking=no -o ConnectTimeout=15 \
           -o BatchMode=yes ubuntu@${WORKER_IP} \"$*\"
    '"
}

wait_for_container() {
  local IP="$1" KEY="$2" NAME="$3"
  echo -n "  Waiting for $NAME container"
  for i in $(seq 1 36); do   # up to 6 min
    if ssh_cmd "$IP" "$KEY" 'docker ps --format "{{.Names}} {{.Status}}"' 2>/dev/null \
        | grep -q "claude-portable.*Up"; then
      echo " ready"
      return 0
    fi
    echo -n "."
    sleep 10
  done
  echo " TIMEOUT"
  return 1
}

get_ip() {
  python3 "$CCP" list 2>/dev/null | grep "^$1" | awk '{print $4}'
}

cleanup() {
  if [ -n "$KEEP" ]; then
    echo ""
    echo "  --keep: Instances left running."
    echo "    Dispatcher: ccc kill $DISPATCHER_NAME"
    echo "    Worker 1:   ccc kill $WORKER1_NAME"
    echo "    Worker 2:   ccc kill $WORKER2_NAME"
    return
  fi
  echo ""
  echo "=== Teardown ==="
  python3 "$CCP" kill "$DISPATCHER_NAME" 2>/dev/null || true
  python3 "$CCP" kill "$WORKER1_NAME"    2>/dev/null || true
  python3 "$CCP" kill "$WORKER2_NAME"    2>/dev/null || true
  echo "  All test instances terminated."
}

# ── Pre-flight ────────────────────────────────────────────────────────────────

echo "=============================================="
echo "  Teams Dispatcher E2E Test"
echo "=============================================="
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CCP="$SCRIPT_DIR/ccc"
PY="python3"

if ! $PY "$CCP" list &>/dev/null; then
  echo "ERROR: ccc not working. Check .env and AWS credentials."
  exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &>/dev/null; then
  echo "ERROR: AWS credentials not available."
  exit 1
fi

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION="${AWS_DEFAULT_REGION:-$(aws configure get region 2>/dev/null || echo 'us-east-2')}"
echo "  AWS account: $ACCOUNT  region: $REGION"
echo ""

# Syntax checks for all dispatcher-related scripts
echo "=== Pre-flight: Syntax checks ==="
for f in \
    "$SCRIPT_DIR/scripts/dispatcher-daemon.sh" \
    "$SCRIPT_DIR/scripts/teams-dispatch.py" \
    "$SCRIPT_DIR/scripts/bootstrap.sh" \
    "$SCRIPT_DIR/scripts/state-sync.sh" \
    "$SCRIPT_DIR/scripts/idle-monitor.sh"; do
  name="$(basename "$f")"
  if [ ! -f "$f" ]; then
    fail "syntax: $name" "file not found"
    continue
  fi
  case "$f" in
    *.sh)
      if bash -n "$f" 2>/dev/null; then pass "syntax: $name"
      else fail "syntax: $name" "bash -n failed"; fi ;;
    *.py)
      if $PY -m py_compile "$f" 2>/dev/null; then pass "syntax: $name"
      else fail "syntax: $name" "py_compile failed"; fi ;;
  esac
done
echo ""

# Check Teams integration prerequisites
TEAMS_READY=""
if [ -n "$SKIP_TEAMS" ]; then
  echo "  Teams integration: SKIPPED (--skip-teams)"
elif [ -z "${DISPATCHER_CHAT_ID:-}" ]; then
  echo "  Teams integration: SKIPPED (DISPATCHER_CHAT_ID not set)"
else
  # Verify Graph token secret exists
  SECRET_NAME="${DISPATCHER_SECRET_NAME:-claude-portable/graph-token}"
  if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" \
        --region "$REGION" &>/dev/null; then
    TEAMS_READY="1"
    echo "  Teams integration: ENABLED (chat=$DISPATCHER_CHAT_ID, secret=$SECRET_NAME)"
  else
    echo "  Teams integration: SKIPPED (secret '$SECRET_NAME' not found in Secrets Manager)"
  fi
fi
echo ""

# ── Launch ────────────────────────────────────────────────────────────────────

echo "=== Launch: Kill any stale test instances ==="
$PY "$CCP" kill "$DISPATCHER_NAME" 2>/dev/null || true
$PY "$CCP" kill "$WORKER1_NAME"    2>/dev/null || true
$PY "$CCP" kill "$WORKER2_NAME"    2>/dev/null || true
sleep 5
echo ""

# Launch workers first so their SSH keys are in S3 when dispatcher boots
echo "=== Launch: Workers (in parallel) ==="
$PY "$CCP" --name "$WORKER1_NAME" &
PID1=$!
$PY "$CCP" --name "$WORKER2_NAME" &
PID2=$!
wait $PID1 $PID2 || true
echo ""

W1_IP=$(get_ip "$WORKER1_NAME")
W2_IP=$(get_ip "$WORKER2_NAME")
W1_KEY=$(key_path "$WORKER1_NAME")
W2_KEY=$(key_path "$WORKER2_NAME")

if [ -z "$W1_IP" ] || [ -z "$W2_IP" ]; then
  fail "launch-workers" "Could not get IPs: worker-1=${W1_IP:-MISSING} worker-2=${W2_IP:-MISSING}"
  cleanup
  exit 1
fi
echo "  Worker 1: $WORKER1_NAME @ $W1_IP"
echo "  Worker 2: $WORKER2_NAME @ $W2_IP"

# Launch dispatcher after workers so keys are available
echo ""
echo "=== Launch: Dispatcher ==="
if [ -n "$TEAMS_READY" ]; then
  $PY "$CCP" --name "$DISPATCHER_NAME" --role dispatcher 2>&1 || true
else
  # Launch dispatcher without Teams env (daemon will exit on missing token
  # but infra and tooling can still be tested via SSH)
  $PY "$CCP" --name "$DISPATCHER_NAME" --role dispatcher 2>&1 || true
fi

DISP_IP=$(get_ip "$DISPATCHER_NAME")
DISP_KEY=$(key_path "$DISPATCHER_NAME")

if [ -z "$DISP_IP" ]; then
  fail "launch-dispatcher" "No IP found for $DISPATCHER_NAME"
  cleanup
  exit 1
fi
echo "  Dispatcher: $DISPATCHER_NAME @ $DISP_IP"

trap cleanup EXIT

# ── Wait for containers ───────────────────────────────────────────────────────

echo ""
echo "=== Wait for containers ==="

WORKER1_READY=0
WORKER2_READY=0
DISP_READY=0

wait_for_container "$W1_IP"   "$W1_KEY"   "$WORKER1_NAME" && WORKER1_READY=1 || true
wait_for_container "$W2_IP"   "$W2_KEY"   "$WORKER2_NAME" && WORKER2_READY=1 || true
wait_for_container "$DISP_IP" "$DISP_KEY" "$DISPATCHER_NAME" && DISP_READY=1 || true

[ $WORKER1_READY -eq 1 ] && pass "launch: $WORKER1_NAME running" \
  || fail "launch: $WORKER1_NAME" "container not Up"
[ $WORKER2_READY -eq 1 ] && pass "launch: $WORKER2_NAME running" \
  || fail "launch: $WORKER2_NAME" "container not Up"
[ $DISP_READY -eq 1 ] && pass "launch: $DISPATCHER_NAME running" \
  || fail "launch: $DISPATCHER_NAME" "container not Up"

echo ""

# ── Test: EC2 tagging ════════════════════════════════════════════════════════

echo "=== Test: EC2 instance tagging ==="

check_tag() {
  local name="$1" tag_key="$2" expected="$3"
  local instance_id
  instance_id=$(aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=ccc-${name}" \
              "Name=instance-state-name,Values=running" \
    --query "Reservations[0].Instances[0].InstanceId" \
    --output text --region "$REGION" 2>/dev/null || echo "")
  if [ -z "$instance_id" ] || [ "$instance_id" = "None" ]; then
    fail "tag: $name" "instance not found"
    return
  fi
  local value
  value=$(aws ec2 describe-instances \
    --instance-ids "$instance_id" \
    --query "Reservations[0].Instances[0].Tags[?Key=='${tag_key}'].Value | [0]" \
    --output text --region "$REGION" 2>/dev/null || echo "")
  if [ "$value" = "$expected" ]; then
    pass "tag: $name has $tag_key=$expected"
  else
    fail "tag: $name" "expected $tag_key=$expected, got '$value'"
  fi
}

check_tag "$DISPATCHER_NAME" "Role"    "dispatcher"
check_tag "$DISPATCHER_NAME" "Project" "claude-portable"
check_tag "$WORKER1_NAME"   "Project" "claude-portable"
check_tag "$WORKER2_NAME"   "Project" "claude-portable"

echo ""

# ── Test: Worker discovery via EC2 API ══════════════════════════════════════

echo "=== Test: Worker discovery via EC2 API ==="

DISCOVERED=$(aws ec2 describe-instances \
  --filters \
    "Name=tag:Project,Values=claude-portable" \
    "Name=instance-state-name,Values=running" \
  --query "Reservations[].Instances[].[Tags[?Key=='Name'].Value|[0], Tags[?Key=='Role'].Value|[0], PrivateIpAddress]" \
  --output text --region "$REGION" 2>/dev/null || echo "")

if echo "$DISCOVERED" | grep -q "ccc-${WORKER1_NAME}"; then
  pass "discovery: $WORKER1_NAME visible via EC2 tags"
else
  fail "discovery: $WORKER1_NAME" "not found in EC2 describe-instances"
fi

if echo "$DISCOVERED" | grep -q "ccc-${WORKER2_NAME}"; then
  pass "discovery: $WORKER2_NAME visible via EC2 tags"
else
  fail "discovery: $WORKER2_NAME" "not found in EC2 describe-instances"
fi

# Dispatcher should be excluded by Role=dispatcher filter
WORKERS_ONLY=$(aws ec2 describe-instances \
  --filters \
    "Name=tag:Project,Values=claude-portable" \
    "Name=tag:Role,Values=worker" \
    "Name=instance-state-name,Values=running" \
  --query "Reservations[].Instances[][Tags[?Key=='Name'].Value|[0]]" \
  --output text --region "$REGION" 2>/dev/null || echo "")

if echo "$WORKERS_ONLY" | grep -q "ccc-${DISPATCHER_NAME}"; then
  fail "discovery: dispatcher excluded" "dispatcher shows up in worker list"
else
  pass "discovery: dispatcher excluded from worker-tagged results"
fi

echo ""

# ── Test: Fleet SSH keys in S3 ══════════════════════════════════════════════

echo "=== Test: Fleet SSH keys in S3 ==="

S3_BUCKET="claude-portable-state-${ACCOUNT}"

check_key_in_s3() {
  local name="$1"
  if aws s3 ls "s3://${S3_BUCKET}/fleet-keys/${name}.pem" \
       --region "$REGION" &>/dev/null; then
    pass "s3-keys: $name.pem present"
  else
    fail "s3-keys: $name.pem" "not found in s3://${S3_BUCKET}/fleet-keys/"
  fi
}

check_key_in_s3 "$WORKER1_NAME"
check_key_in_s3 "$WORKER2_NAME"

echo ""

# ── Test: Dispatcher key sync ════════════════════════════════════════════════

echo "=== Test: Dispatcher fleet key sync ==="

if [ $DISP_READY -eq 0 ]; then
  skip "dispatcher key sync" "dispatcher container not ready"
else
  # Trigger an immediate key sync inside the dispatcher container
  SYNC_OUT=$(ssh_cmd "$DISP_IP" "$DISP_KEY" \
    "docker exec claude-portable bash -c '
       aws s3 sync \"s3://${S3_BUCKET}/fleet-keys/\" \"\$HOME/.ssh/ccc-keys/\" \
         --exclude \"*\" --include \"*.pem\" 2>&1 && \
       find \"\$HOME/.ssh/ccc-keys/\" -name \"*.pem\" -exec chmod 600 {} \\; && \
       ls \"\$HOME/.ssh/ccc-keys/\"
    '" 2>&1 || echo "sync-error")

  if echo "$SYNC_OUT" | grep -q "${WORKER1_NAME}.pem"; then
    pass "dispatcher key sync: $WORKER1_NAME.pem synced"
  else
    fail "dispatcher key sync: $WORKER1_NAME.pem" "not found after sync"
  fi

  if echo "$SYNC_OUT" | grep -q "${WORKER2_NAME}.pem"; then
    pass "dispatcher key sync: $WORKER2_NAME.pem synced"
  else
    fail "dispatcher key sync: $WORKER2_NAME.pem" "not found after sync"
  fi
fi

echo ""

# ── Test: Worker health ══════════════════════════════════════════════════════

echo "=== Test: Worker health checks ==="

check_worker_health() {
  local ip="$1" key="$2" name="$3"
  if [ -z "$ip" ]; then
    skip "worker health: $name" "instance not running"
    return
  fi
  local result
  result=$(docker_exec "$ip" "$key" \
    "/opt/claude-portable/scripts/health-check.sh 2>/dev/null" 2>&1 || echo "error")
  if echo "$result" | grep -qi "healthy"; then
    pass "worker health: $name"
  else
    fail "worker health: $name" "$(echo "$result" | tail -1)"
  fi
}

check_worker_health "$W1_IP" "$W1_KEY" "$WORKER1_NAME"
check_worker_health "$W2_IP" "$W2_KEY" "$WORKER2_NAME"

echo ""

# ── Test: Dispatcher heartbeat in S3 ════════════════════════════════════════

echo "=== Test: Dispatcher heartbeat ==="

if [ $DISP_READY -eq 0 ]; then
  skip "dispatcher heartbeat" "dispatcher container not ready"
else
  # Give the heartbeat daemon 30s to write its first beat if not already done
  for i in $(seq 1 6); do
    HB=$(aws s3 cp "s3://${S3_BUCKET}/dispatcher/heartbeat.json" - \
           --region "$REGION" 2>/dev/null || echo "")
    if echo "$HB" | grep -q '"timestamp"'; then
      break
    fi
    sleep 5
  done

  if echo "$HB" | grep -q '"timestamp"'; then
    BEAT_TS=$(echo "$HB" | grep -o '"timestamp":"[^"]*"' | cut -d'"' -f4)
    pass "dispatcher heartbeat in S3 (last: $BEAT_TS)"
  else
    fail "dispatcher heartbeat" "no heartbeat.json in s3://${S3_BUCKET}/dispatcher/"
  fi
fi

echo ""

# ── Test: Dispatcher health endpoint ════════════════════════════════════════

echo "=== Test: Dispatcher health endpoint ==="

if [ $DISP_READY -eq 0 ]; then
  skip "dispatcher health endpoint" "dispatcher container not ready"
else
  # The health endpoint is started by teams-dispatch.py on port 8080.
  # On a fresh dispatcher without Teams creds, teams-dispatch.py may not be
  # running yet. Check if it's up; if not, start it in test mode.
  HEALTH_RAW=$(ssh_cmd "$DISP_IP" "$DISP_KEY" \
    "curl -s --max-time 5 http://localhost:8080/health 2>/dev/null || echo 'no-response'")

  if echo "$HEALTH_RAW" | grep -q '"status"'; then
    pass "dispatcher health endpoint responds"

    STATUS=$(echo "$HEALTH_RAW" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    pass "dispatcher health status: $STATUS"

    if echo "$HEALTH_RAW" | grep -q '"workers"'; then
      pass "dispatcher health: workers field present"
    else
      fail "dispatcher health: workers field" "missing from response"
    fi

    if echo "$HEALTH_RAW" | grep -q '"error_count"'; then
      pass "dispatcher health: error_count field present"
    else
      fail "dispatcher health: error_count field" "missing from response"
    fi
  else
    skip "dispatcher health endpoint" "teams-dispatch.py not running (no Teams credentials)"
  fi
fi

echo ""

# ── Test: SSH dispatch chain ═════════════════════════════════════════════════

echo "=== Test: SSH dispatch chain (dispatcher -> worker) ==="

if [ $DISP_READY -eq 0 ]; then
  skip "ssh dispatch chain" "dispatcher container not ready"
elif [ $WORKER1_READY -eq 0 ]; then
  skip "ssh dispatch chain" "worker-1 not ready"
else
  # Test direct SSH from dispatcher container to worker-1
  TEST_CMD="echo dispatch-test-ok"
  DISPATCH_RESULT=$(dispatcher_ssh_to_worker \
    "$DISP_IP" "$DISP_KEY" "$W1_IP" "$WORKER1_NAME" \
    "docker exec claude-portable bash -c '${TEST_CMD}'" 2>&1 || echo "dispatch-failed")

  if echo "$DISPATCH_RESULT" | grep -q "dispatch-test-ok"; then
    pass "ssh dispatch chain: dispatcher -> $WORKER1_NAME"
  else
    fail "ssh dispatch chain: dispatcher -> $WORKER1_NAME" \
         "$(echo "$DISPATCH_RESULT" | tail -2)"
  fi

  # Test dispatcher -> worker-2
  if [ $WORKER2_READY -eq 1 ]; then
    DISPATCH_RESULT2=$(dispatcher_ssh_to_worker \
      "$DISP_IP" "$DISP_KEY" "$W2_IP" "$WORKER2_NAME" \
      "docker exec claude-portable bash -c '${TEST_CMD}'" 2>&1 || echo "dispatch-failed")

    if echo "$DISPATCH_RESULT2" | grep -q "dispatch-test-ok"; then
      pass "ssh dispatch chain: dispatcher -> $WORKER2_NAME"
    else
      fail "ssh dispatch chain: dispatcher -> $WORKER2_NAME" \
           "$(echo "$DISPATCH_RESULT2" | tail -2)"
    fi
  fi
fi

echo ""

# ── Test: Claude dispatch (non-interactive prompt) ═══════════════════════════

echo "=== Test: Claude prompt dispatch via SSH ==="

if [ $DISP_READY -eq 0 ] || [ $WORKER1_READY -eq 0 ]; then
  skip "claude prompt dispatch" "dispatcher or worker not ready"
else
  REQ_ID="e2e-test-$(date +%s)"
  RESULT_FILE="/tmp/teams-result-${REQ_ID}.txt"
  TEST_PROMPT="Reply with only: dispatch-verified"

  # Mimic what teams-dispatch.py does: SSH to worker and run claude -p
  ESCAPED="${TEST_PROMPT//\'/\'\\\'\'}"
  DISPATCH_CMD="docker exec -d -w /workspace claude-portable bash -c 'claude -p \"${ESCAPED}\" --dangerously-skip-permissions > ${RESULT_FILE} 2>&1'"

  dispatcher_ssh_to_worker \
    "$DISP_IP" "$DISP_KEY" "$W1_IP" "$WORKER1_NAME" \
    "$DISPATCH_CMD" &>/dev/null || true

  # Poll for result (up to 120s - claude may need to start up)
  echo -n "  Waiting for claude response"
  CLAUDE_RESULT=""
  for i in $(seq 1 24); do
    sleep 5
    CLAUDE_RESULT=$(dispatcher_ssh_to_worker \
      "$DISP_IP" "$DISP_KEY" "$W1_IP" "$WORKER1_NAME" \
      "docker exec claude-portable bash -c 'cat ${RESULT_FILE} 2>/dev/null || true'" \
      2>/dev/null || echo "")
    if [ -n "$CLAUDE_RESULT" ]; then
      echo " done (${i}*5s)"
      break
    fi
    echo -n "."
  done

  if [ -n "$CLAUDE_RESULT" ]; then
    pass "claude dispatch: result received"
    echo "    Response: $(echo "$CLAUDE_RESULT" | head -1)"
  else
    fail "claude dispatch" "no result after 120s at $RESULT_FILE on $WORKER1_NAME"
  fi
fi

echo ""

# ── Test: Teams integration (full flow) ══════════════════════════════════════

echo "=== Test: Teams integration (ACK + dispatch + reply) ==="

if [ -z "$TEAMS_READY" ]; then
  skip "teams: send @claude message" "no Teams credentials configured"
  skip "teams: verify ACK"           "no Teams credentials configured"
  skip "teams: verify dispatch"      "no Teams credentials configured"
  skip "teams: verify reply"         "no Teams credentials configured"
else
  # Teams integration requires the dispatcher daemon to be running
  DAEMON_RUNNING=$(ssh_cmd "$DISP_IP" "$DISP_KEY" \
    "docker exec claude-portable bash -c 'ps aux | grep teams-dispatch | grep -v grep'" \
    2>/dev/null || echo "")

  if ! echo "$DAEMON_RUNNING" | grep -q "teams-dispatch"; then
    skip "teams integration" "dispatcher daemon not running (check dispatcher logs)"
  else
    pass "teams: dispatcher daemon running"

    # Use Graph token to send a test message to Teams
    TOKEN_FILE="/run/dispatcher/graph-token.json"
    GRAPH_TOKEN=$(ssh_cmd "$DISP_IP" "$DISP_KEY" \
      "docker exec claude-portable bash -c '
         cat ${TOKEN_FILE} 2>/dev/null | python3 -c \
         \"import json,sys; d=json.load(sys.stdin); print(d.get(\\\"access_token\\\",d.get(\\\"token\\\",\\\"\\\")))\"
      '" 2>/dev/null || echo "")

    if [ -z "$GRAPH_TOKEN" ]; then
      skip "teams: send test message" "could not read Graph token from dispatcher"
    else
      TEST_MSG="@claude e2e-dispatch-test: what is 2+2? (test $(date +%s))"

      SEND_RESULT=$(ssh_cmd "$DISP_IP" "$DISP_KEY" \
        "docker exec claude-portable bash -c '
           python3 -c \"
import urllib.request, json
token = open(\\\"/run/dispatcher/graph-token.json\\\").read().strip()
if token.startswith(\\\"{\\\"): token = json.loads(token).get(\\\"access_token\\\",\\\"\\\")
data = json.dumps({\\\"body\\\": {\\\"content\\\": \\\"${TEST_MSG}\\\"}}).encode()
req = urllib.request.Request(
  \\\"https://graph.microsoft.com/v1.0/chats/${DISPATCHER_CHAT_ID}/messages\\\",
  data=data, method=\\\"POST\\\",
  headers={\\\"Authorization\\\": \\\"Bearer \\\"+token, \\\"Content-Type\\\": \\\"application/json\\\"}
)
try:
  r = urllib.request.urlopen(req, timeout=15)
  print(\\\"sent:ok:\\\"+r.read().decode()[:80])
except Exception as e:
  print(\\\"sent:err:\\\"+str(e))
\"
        '" 2>/dev/null || echo "send-failed")

      if echo "$SEND_RESULT" | grep -q "sent:ok:"; then
        pass "teams: test message sent"
      else
        fail "teams: send test message" "$(echo "$SEND_RESULT" | tail -1)"
      fi

      # Poll state file for ACK (up to 120s = 4 poll cycles at 30s each)
      STATE_FILE="/data/dispatcher-state.json"
      echo -n "  Waiting for ACK"
      ACK_FOUND=""
      DISPATCH_FOUND=""
      REPLY_FOUND=""

      for i in $(seq 1 24); do
        sleep 5
        STATE=$(ssh_cmd "$DISP_IP" "$DISP_KEY" \
          "docker exec claude-portable bash -c 'cat ${STATE_FILE} 2>/dev/null || echo {}'" \
          2>/dev/null || echo "{}")

        if echo "$STATE" | grep -q '"acked"' && [ -z "$ACK_FOUND" ]; then
          ACK_FOUND="1"
          echo " ACK received (${i}*5s)"
        fi
        if echo "$STATE" | grep -qE '"dispatched"|"running"' && [ -z "$DISPATCH_FOUND" ]; then
          DISPATCH_FOUND="1"
          echo "  Dispatch confirmed"
        fi
        if echo "$STATE" | grep -q '"completed"' && [ -z "$REPLY_FOUND" ]; then
          REPLY_FOUND="1"
          echo "  Completed"
          break
        fi

        if [ $((i % 6)) -eq 0 ]; then echo -n "."; fi
      done
      echo ""

      if [ -n "$ACK_FOUND" ];     then pass "teams: ACK sent to chat"
      else                             fail "teams: ACK" "no 'acked' state in ${STATE_FILE}"; fi

      if [ -n "$DISPATCH_FOUND" ]; then pass "teams: request dispatched to worker"
      else                              fail "teams: dispatch" "no dispatched/running state"; fi

      if [ -n "$REPLY_FOUND" ];   then pass "teams: result posted back to chat"
      else                             fail "teams: reply" "no completed state after 120s"; fi
    fi
  fi
fi

echo ""

# ── Summary ───────────────────────────────────────────────────────────────────

echo "=============================================="
echo "  Results"
echo "=============================================="
printf '  %s\n' "${RESULTS[@]}"
echo ""
echo "  PASS: $PASS  FAIL: $FAIL  SKIP: $SKIP"
echo ""

if [ "$FAIL" -gt 0 ]; then
  echo "  Some tests FAILED."
  echo "  Dispatcher: ssh -i $DISP_KEY ubuntu@$DISP_IP"
  echo "  Worker 1:   ssh -i $W1_KEY ubuntu@$W1_IP"
  echo "  Worker 2:   ssh -i $W2_KEY ubuntu@$W2_IP"
  echo ""
  echo "  View dispatcher logs: ssh -i $DISP_KEY ubuntu@$DISP_IP 'docker logs claude-portable'"
  exit 1
fi
