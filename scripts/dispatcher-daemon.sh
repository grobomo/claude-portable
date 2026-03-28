#!/bin/bash
# Dispatcher daemon -- runs on a dedicated dispatcher instance.
# Fetches Graph token from AWS Secrets Manager, syncs fleet SSH keys from S3,
# and runs teams-dispatch.py with a watchdog loop (auto-restarts on crash).
#
# Usage:
#   dispatcher-daemon.sh [chat-id] [trigger] [interval]
#
# Environment:
#   DISPATCHER_SECRET_NAME    Secrets Manager secret name for Graph token
#                             (default: claude-portable/graph-token)
#   DISPATCHER_CHAT_ID        Teams chat ID to monitor (or pass as $1)
#   DISPATCHER_TRIGGER        Trigger keyword (default: @claude)
#   DISPATCHER_POLL_INTERVAL  Poll interval in seconds (default: 30)
#   DISPATCHER_RESTART_DELAY  Seconds to wait before restart on crash (default: 10)
#   DISPATCHER_KEY_SYNC_INTERVAL  Fleet key sync interval in seconds (default: 300)
set -euo pipefail

# ── Config ───────────────────────────────────────────────────────────────────

CHAT_ID="${1:-${DISPATCHER_CHAT_ID:-}}"
TRIGGER="${2:-${DISPATCHER_TRIGGER:-@claude}}"
POLL_INTERVAL="${3:-${DISPATCHER_POLL_INTERVAL:-30}}"

SECRET_NAME="${DISPATCHER_SECRET_NAME:-claude-portable/graph-token}"
RESTART_DELAY="${DISPATCHER_RESTART_DELAY:-10}"
KEY_SYNC_INTERVAL="${DISPATCHER_KEY_SYNC_INTERVAL:-300}"

LOG_FILE="/data/dispatcher.log"
TOKEN_FILE="/run/dispatcher/graph-token.json"
KEY_DIR="${HOME}/.ssh/ccc-keys"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DISPATCH_SCRIPT="${SCRIPT_DIR}/teams-dispatch.py"
STATE_FILE="/data/dispatcher-state.json"
PID_FILE="/run/dispatcher/daemon.pid"

# ── Preflight ─────────────────────────────────────────────────────────────────

if [ -z "$CHAT_ID" ]; then
  echo "ERROR: Teams chat ID required. Set DISPATCHER_CHAT_ID or pass as first argument."
  exit 1
fi

if [ ! -f "$DISPATCH_SCRIPT" ]; then
  echo "ERROR: teams-dispatch.py not found at $DISPATCH_SCRIPT"
  exit 1
fi

mkdir -p "$(dirname "$TOKEN_FILE")" "$KEY_DIR" "$(dirname "$PID_FILE")"
chmod 700 "$(dirname "$TOKEN_FILE")"

# Redirect all output to log file (tee to stdout for docker logs)
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== Dispatcher Daemon ==="
echo "  Chat ID:       ${CHAT_ID:0:35}..."
echo "  Trigger:       $TRIGGER"
echo "  Poll interval: ${POLL_INTERVAL}s"
echo "  Secret name:   $SECRET_NAME"
echo "  Log file:      $LOG_FILE"
echo "  Started:       $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

echo $$ > "$PID_FILE"

# ── AWS helpers ───────────────────────────────────────────────────────────────

get_aws_account() {
  aws sts get-caller-identity --query Account --output text 2>/dev/null || echo ""
}

get_region() {
  # Try instance metadata first (running on EC2), fall back to AWS CLI default
  TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" --connect-timeout 2 2>/dev/null || echo "")
  if [ -n "$TOKEN" ]; then
    curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
      http://169.254.169.254/latest/meta-data/placement/region \
      --connect-timeout 2 2>/dev/null || echo "${AWS_DEFAULT_REGION:-us-east-2}"
  else
    echo "${AWS_DEFAULT_REGION:-us-east-2}"
  fi
}

REGION="$(get_region)"
echo "  AWS region:    $REGION"

# ── Graph token management ────────────────────────────────────────────────────

fetch_graph_token() {
  echo "[$(date -u +%H:%M:%S)] Fetching Graph token from Secrets Manager (${SECRET_NAME})..."

  local secret
  secret=$(aws secretsmanager get-secret-value \
    --secret-id "$SECRET_NAME" \
    --region "$REGION" \
    --query SecretString \
    --output text 2>&1) || {
    echo "  ERROR: Failed to fetch secret '${SECRET_NAME}': $secret"
    return 1
  }

  # Write token to file (teams-dispatch.py reads it via GRAPH_TOKEN_FILE env var)
  echo "$secret" > "$TOKEN_FILE"
  chmod 600 "$TOKEN_FILE"
  echo "  Graph token written to $TOKEN_FILE"
}

# ── Fleet SSH key sync ─────────────────────────────────────────────────────────

sync_fleet_keys() {
  local account
  account="$(get_aws_account)"
  if [ -z "$account" ]; then
    echo "  WARNING: Could not determine AWS account ID. Skipping key sync."
    return 0
  fi

  local bucket="claude-portable-state-${account}"
  local s3_prefix="s3://${bucket}/fleet-keys/"

  echo "[$(date -u +%H:%M:%S)] Syncing fleet SSH keys from ${s3_prefix}..."

  # Sync all .pem keys from S3 fleet-keys/ to local ~/.ssh/ccc-keys/
  local sync_output
  sync_output=$(aws s3 sync "$s3_prefix" "$KEY_DIR/" \
    --region "$REGION" \
    --exclude "*" --include "*.pem" 2>&1) || {
    echo "  WARNING: Key sync failed: $sync_output"
    return 0
  }

  # Fix permissions on any new key files
  find "$KEY_DIR" -name "*.pem" -exec chmod 600 {} \;

  local key_count
  key_count=$(find "$KEY_DIR" -name "*.pem" | wc -l)
  echo "  Fleet keys synced: ${key_count} key(s) in ${KEY_DIR}"
}

# ── Background key sync loop ──────────────────────────────────────────────────

start_key_sync_daemon() {
  (
    while true; do
      sleep "$KEY_SYNC_INTERVAL"
      sync_fleet_keys 2>&1 || true
    done
  ) &
  echo "  Key sync daemon started (PID $!, interval: ${KEY_SYNC_INTERVAL}s)"
}

# ── Main watchdog loop ────────────────────────────────────────────────────────

run_dispatch() {
  # Build the PYTHONPATH to pick up graph helpers from the token file
  export GRAPH_TOKEN_FILE="$TOKEN_FILE"

  # Pass state file path to avoid /tmp collisions
  export TEAMS_DISPATCH_STATE_FILE="$STATE_FILE"

  python3 "$DISPATCH_SCRIPT" \
    --chat-id "$CHAT_ID" \
    --trigger "$TRIGGER" \
    --interval "$POLL_INTERVAL"
}

# ── Startup ───────────────────────────────────────────────────────────────────

# Fetch token on startup (required before launching dispatch)
if ! fetch_graph_token; then
  echo "FATAL: Cannot start without Graph token. Check secret '${SECRET_NAME}' in Secrets Manager."
  exit 1
fi

# Initial key sync on startup
sync_fleet_keys || true

# Periodic key sync in background
start_key_sync_daemon

# ── Watchdog ─────────────────────────────────────────────────────────────────

CRASH_COUNT=0
MAX_CRASHES=10
CRASH_WINDOW=300  # seconds -- reset crash count if process runs longer than this

echo ""
echo "[+] Starting dispatch watchdog (max crashes: ${MAX_CRASHES}, restart delay: ${RESTART_DELAY}s)..."
echo ""

while true; do
  START_TS=$(date +%s)

  echo "[$(date -u +%H:%M:%S)] Starting teams-dispatch.py (attempt $((CRASH_COUNT + 1)))..."

  # Run the dispatcher; capture exit code without aborting the watchdog
  DISPATCH_EXIT=0
  run_dispatch || DISPATCH_EXIT=$?

  END_TS=$(date +%s)
  RUNTIME=$((END_TS - START_TS))

  if [ "$RUNTIME" -gt "$CRASH_WINDOW" ]; then
    # Process ran for a while -- reset crash counter
    CRASH_COUNT=0
    echo "[$(date -u +%H:%M:%S)] Dispatcher ran ${RUNTIME}s before stopping. Resetting crash counter."
  else
    CRASH_COUNT=$((CRASH_COUNT + 1))
    echo "[$(date -u +%H:%M:%S)] Dispatcher exited after ${RUNTIME}s (exit ${DISPATCH_EXIT}). Crash #${CRASH_COUNT}/${MAX_CRASHES}."
  fi

  if [ "$CRASH_COUNT" -ge "$MAX_CRASHES" ]; then
    echo "[$(date -u +%H:%M:%S)] FATAL: $MAX_CRASHES rapid crashes. Stopping daemon."
    exit 1
  fi

  # Refresh token before restart (it may have expired)
  echo "[$(date -u +%H:%M:%S)] Refreshing Graph token before restart..."
  fetch_graph_token || echo "  WARNING: Token refresh failed. Continuing with cached token."

  echo "[$(date -u +%H:%M:%S)] Restarting in ${RESTART_DELAY}s..."
  sleep "$RESTART_DELAY"
done
