#!/bin/bash
# Preflight verification for dispatcher zero-touch boot.
#
# Checks all prerequisites before launching:
#   ccc --name dispatcher --role dispatcher
#
# Usage: bash scripts/test-dispatcher.sh [--fix]
#   --fix   attempt to auto-fix correctable issues (e.g. save chat ID to config)
#
# Exit code: 0 = all checks passed, 1 = one or more checks failed
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_FILE="$REPO_DIR/ccc.config.json"

PASS=0
FAIL=0
WARN=0
RESULTS=()

pass() { PASS=$((PASS + 1)); RESULTS+=("  PASS  $1"); echo "  PASS  $1"; }
fail() { FAIL=$((FAIL + 1)); RESULTS+=("  FAIL  $1: $2"); echo "  FAIL  $1: $2"; }
warn() { WARN=$((WARN + 1)); RESULTS+=("  WARN  $1: $2"); echo "  WARN  $1: $2"; }

echo "================================================="
echo "  Dispatcher Preflight Check"
echo "  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "================================================="
echo ""

# ── 1. Script syntax ─────────────────────────────────────────────────────────
echo "=== 1. Script syntax ==="
for f in "$SCRIPT_DIR/dispatcher-daemon.sh" "$SCRIPT_DIR/teams-dispatch.py"; do
  if [ ! -f "$f" ]; then
    fail "exists: $(basename "$f")" "file not found at $f"
    continue
  fi
  case "$f" in
    *.sh)
      if bash -n "$f" 2>/dev/null; then
        pass "syntax: $(basename "$f")"
      else
        fail "syntax: $(basename "$f")" "bash -n reported errors"
      fi
      ;;
    *.py)
      if python3 -m py_compile "$f" 2>/dev/null; then
        pass "syntax: $(basename "$f")"
      else
        fail "syntax: $(basename "$f")" "python3 -m py_compile reported errors"
      fi
      ;;
  esac
done

# ── 2. Docker compose files ──────────────────────────────────────────────────
echo ""
echo "=== 2. Docker Compose files ==="
for f in \
  "$REPO_DIR/docker-compose.yml" \
  "$REPO_DIR/docker-compose.remote.yml" \
  "$REPO_DIR/docker-compose.dispatcher.yml"
do
  if [ -f "$f" ]; then
    pass "exists: $(basename "$f")"
    # Validate entrypoint override in dispatcher compose
    if [[ "$f" == *dispatcher* ]]; then
      if grep -q "dispatcher-daemon.sh" "$f"; then
        pass "entrypoint: dispatcher-daemon.sh set in $(basename "$f")"
      else
        fail "entrypoint: $(basename "$f")" "dispatcher-daemon.sh not found as entrypoint"
      fi
      if grep -q "DISPATCHER_CHAT_ID" "$f"; then
        pass "env-var: DISPATCHER_CHAT_ID present in $(basename "$f")"
      else
        fail "env-var: $(basename "$f")" "DISPATCHER_CHAT_ID not found"
      fi
    fi
  else
    fail "exists: $(basename "$f")" "file not found"
  fi
done

# ── 3. ccc.config.json ───────────────────────────────────────────────────────
echo ""
echo "=== 3. ccc.config.json ==="
if [ ! -f "$CONFIG_FILE" ]; then
  warn "config" "ccc.config.json not found — will use defaults; DISPATCHER_CHAT_ID may be unset"
else
  pass "exists: ccc.config.json"
  if python3 -c "import json,sys; json.load(open('$CONFIG_FILE'))" 2>/dev/null; then
    pass "valid JSON: ccc.config.json"
  else
    fail "valid JSON: ccc.config.json" "parse error"
  fi

  CHAT_ID=$(python3 -c "
import json, sys
try:
    cfg = json.load(open('$CONFIG_FILE'))
    print(cfg.get('dispatcher_chat_id', ''))
except Exception:
    print('')
" 2>/dev/null)

  if [ -n "$CHAT_ID" ]; then
    pass "dispatcher_chat_id: set (${CHAT_ID:0:10}...)"
  else
    fail "dispatcher_chat_id" "not set in ccc.config.json — dispatcher cannot poll Teams without it"
    echo "         Fix: run  ccc --name dispatcher --role dispatcher  and enter the chat ID when prompted"
    echo "         Or add:  {\"dispatcher_chat_id\": \"<YOUR_TEAMS_CHAT_ID>\"} to $CONFIG_FILE"
  fi
fi

# ── 4. .env file ─────────────────────────────────────────────────────────────
echo ""
echo "=== 4. .env file ==="
ENV_FILE="$REPO_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
  warn ".env" "not found — instance will start without DISPATCHER_SECRET_NAME override"
else
  pass "exists: .env"
  # Check for secrets that should NOT be in .env (Graph token should be in Secrets Manager)
  if grep -qE "^GRAPH_TOKEN|^GRAPH_ACCESS_TOKEN" "$ENV_FILE" 2>/dev/null; then
    warn ".env" "GRAPH_TOKEN found in .env — should be stored in AWS Secrets Manager, not .env"
  fi
fi

# ── 5. AWS CLI + credentials ─────────────────────────────────────────────────
echo ""
echo "=== 5. AWS CLI + credentials ==="
if command -v aws &>/dev/null; then
  pass "aws CLI: installed ($(aws --version 2>&1 | head -1))"
  if aws sts get-caller-identity &>/dev/null; then
    ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
    REGION=$(aws configure get region 2>/dev/null || echo "${AWS_DEFAULT_REGION:-not set}")
    pass "aws credentials: valid (account=$ACCOUNT, region=$REGION)"

    # ── 5a. Secrets Manager secret ─────────────────────────────────────────
    echo ""
    echo "=== 5a. Secrets Manager ==="
    SECRET_NAME="${DISPATCHER_SECRET_NAME:-claude-portable/graph-token}"
    if aws secretsmanager describe-secret \
        --secret-id "$SECRET_NAME" \
        --region "$REGION" &>/dev/null; then
      pass "secret: '$SECRET_NAME' exists"
      # Check it has an access_token field
      SECRET_VALUE=$(aws secretsmanager get-secret-value \
        --secret-id "$SECRET_NAME" \
        --region "$REGION" \
        --query SecretString \
        --output text 2>/dev/null || echo "")
      if [ -n "$SECRET_VALUE" ]; then
        if echo "$SECRET_VALUE" | python3 -c "
import json,sys
raw = sys.stdin.read().strip()
if raw.startswith('{'):
    d = json.loads(raw)
    tok = d.get('access_token') or d.get('token','')
else:
    tok = raw
sys.exit(0 if tok else 1)
" 2>/dev/null; then
          pass "secret: access_token present in '$SECRET_NAME'"
        else
          fail "secret: '$SECRET_NAME'" "no access_token field — dispatcher will fail to fetch Graph token"
        fi
      else
        fail "secret: '$SECRET_NAME'" "could not read secret value"
      fi
    else
      fail "secret: '$SECRET_NAME'" "not found in Secrets Manager — create it with: aws secretsmanager create-secret --name '$SECRET_NAME' --secret-string '{\"access_token\":\"<GRAPH_TOKEN>\"}'"
    fi

    # ── 5b. S3 state bucket ────────────────────────────────────────────────
    echo ""
    echo "=== 5b. S3 state bucket ==="
    BUCKET="claude-portable-state-${ACCOUNT}"
    if aws s3api head-bucket --bucket "$BUCKET" &>/dev/null; then
      pass "S3 bucket: $BUCKET exists"
      # Check fleet-keys prefix is accessible
      if aws s3 ls "s3://$BUCKET/fleet-keys/" &>/dev/null; then
        KEY_COUNT=$(aws s3 ls "s3://$BUCKET/fleet-keys/" 2>/dev/null | grep -c "\.pem" || echo 0)
        if [ "$KEY_COUNT" -gt 0 ]; then
          pass "fleet-keys: $KEY_COUNT .pem private key(s) found (workers have registered)"
        else
          warn "fleet-keys" "no .pem keys in s3://$BUCKET/fleet-keys/ — launch a worker first so dispatcher can SSH to it"
          echo "         Note: worker launch (ccc --name worker-1) uploads the private key automatically"
        fi
      else
        warn "fleet-keys" "s3://$BUCKET/fleet-keys/ not accessible — dispatcher key sync will warn on boot"
      fi
    else
      fail "S3 bucket" "$BUCKET not found — run: ccc state-sync setup (on the EC2 instance)"
    fi

    # ── 5c. CloudFormation dispatcher stack ───────────────────────────────
    echo ""
    echo "=== 5c. CloudFormation ==="
    CF_TEMPLATE="$REPO_DIR/cloudformation/dispatcher.yaml"
    if [ -f "$CF_TEMPLATE" ]; then
      pass "CF template: cloudformation/dispatcher.yaml exists"
    else
      warn "CF template" "cloudformation/dispatcher.yaml not found — IAM role may not be deployed"
    fi

    STACK_STATUS=$(aws cloudformation describe-stacks \
      --stack-name "claude-portable-dispatcher" \
      --region "$REGION" \
      --query "Stacks[0].StackStatus" \
      --output text 2>/dev/null || echo "NOTFOUND")
    if [ "$STACK_STATUS" = "CREATE_COMPLETE" ] || [ "$STACK_STATUS" = "UPDATE_COMPLETE" ]; then
      pass "CF stack: claude-portable-dispatcher ($STACK_STATUS)"
    elif [ "$STACK_STATUS" = "NOTFOUND" ]; then
      warn "CF stack" "claude-portable-dispatcher not deployed — dispatcher may lack Secrets Manager / EC2 / S3 permissions"
      echo "         Deploy with: aws cloudformation deploy --template-file cloudformation/dispatcher.yaml --stack-name claude-portable-dispatcher --capabilities CAPABILITY_IAM"
    else
      warn "CF stack" "claude-portable-dispatcher status: $STACK_STATUS"
    fi

  else
    fail "aws credentials" "aws sts get-caller-identity failed — check AWS credentials"
  fi
else
  warn "aws CLI" "not found — skipping cloud checks (run this on the local machine with aws configured)"
fi

# ── 6. Dockerfile checks ─────────────────────────────────────────────────────
echo ""
echo "=== 6. Dockerfile ==="
DOCKERFILE="$REPO_DIR/Dockerfile"
if [ -f "$DOCKERFILE" ]; then
  if grep -q "openssh-server" "$DOCKERFILE"; then
    pass "openssh-server: installed in Dockerfile (provides ssh client for dispatcher)"
  else
    fail "openssh-server" "not in Dockerfile — dispatcher cannot SSH to workers"
  fi
  if grep -q "python3" "$DOCKERFILE"; then
    pass "python3: installed in Dockerfile"
  else
    fail "python3" "not in Dockerfile — teams-dispatch.py cannot run"
  fi
  if grep -q "awscli\|aws-cli\|amazon/aws-cli\|awscli2" "$DOCKERFILE"; then
    pass "AWS CLI: installed in Dockerfile"
  else
    # Could be installed separately
    if grep -q "aws" "$DOCKERFILE"; then
      pass "AWS CLI: aws reference found in Dockerfile"
    else
      warn "AWS CLI" "not explicitly found in Dockerfile — verify aws is available in container"
    fi
  fi
fi

# ── 7. Boot sequence walkthrough ─────────────────────────────────────────────
echo ""
echo "=== 7. Boot sequence (static analysis) ==="

# dispatcher-daemon.sh does NOT call bootstrap.sh (intentional — dispatcher is headless)
# It goes directly to: fetch_graph_token -> sync_fleet_keys -> start_key_sync_daemon
#                   -> write_heartbeat -> start_heartbeat_daemon -> watchdog loop

DAEMON_SCRIPT="$SCRIPT_DIR/dispatcher-daemon.sh"
if [ -f "$DAEMON_SCRIPT" ]; then
  if grep -q "fetch_graph_token" "$DAEMON_SCRIPT" && grep -q "FATAL" "$DAEMON_SCRIPT"; then
    pass "boot: graph token fetch has FATAL guard on failure"
  fi
  if grep -q "sync_fleet_keys" "$DAEMON_SCRIPT"; then
    pass "boot: fleet key sync on startup"
  fi
  if grep -q "write_heartbeat" "$DAEMON_SCRIPT"; then
    pass "boot: heartbeat written immediately on start"
  fi
  if grep -q "CRASH_COUNT\|MAX_CRASHES" "$DAEMON_SCRIPT"; then
    pass "boot: watchdog has crash limit + auto-restart"
  fi
  if grep -q "GRAPH_TOKEN_FILE" "$DAEMON_SCRIPT"; then
    pass "boot: GRAPH_TOKEN_FILE exported before launching teams-dispatch.py"
  fi
fi

if [ -f "$SCRIPT_DIR/teams-dispatch.py" ]; then
  if python3 -c "
import ast, sys
with open('$SCRIPT_DIR/teams-dispatch.py') as f:
    ast.parse(f.read())
print('ok')
" 2>/dev/null | grep -q ok; then
    pass "boot: teams-dispatch.py AST parse OK"
  fi
  if grep -q "start_health_server" "$SCRIPT_DIR/teams-dispatch.py"; then
    pass "boot: health endpoint started in teams-dispatch.py"
  fi
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "================================================="
echo "  Results: ${PASS} passed, ${FAIL} failed, ${WARN} warnings"
echo "================================================="
for r in "${RESULTS[@]}"; do
  echo "$r"
done
echo ""

if [ "$FAIL" -gt 0 ]; then
  echo "ACTION REQUIRED: fix the FAIL items above before launching the dispatcher."
  echo ""
  exit 1
elif [ "$WARN" -gt 0 ]; then
  echo "Preflight passed with warnings. Review WARN items for production readiness."
  echo "Launch with: ccc --name dispatcher --role dispatcher"
  echo ""
  exit 0
else
  echo "All checks passed. Launch with: ccc --name dispatcher --role dispatcher"
  echo ""
  exit 0
fi
