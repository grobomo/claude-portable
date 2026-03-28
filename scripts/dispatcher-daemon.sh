#!/bin/bash
# Dispatcher daemon -- runs on a dedicated dispatcher instance.
# Watches TODO.md on main for unchecked tasks and manages EC2 worker fleet.
# No Teams polling -- that is handled by the chatbot instance.
#
# Usage:
#   dispatcher-daemon.sh
#
# Environment:
#   TODO_POLL_INTERVAL        Seconds between git polls (default: 60)
#   DISPATCHER_REPO_DIR       Path to claude-portable repo (default: /workspace/claude-portable)
#   DISPATCHER_MAX_WORKERS    Max concurrent workers (default: 5)
#   DISPATCHER_HEALTH_PORT    Health endpoint port (default: 8080)
#   DISPATCHER_RESTART_DELAY  Seconds before restart on crash (default: 10)
#   DISPATCHER_KEY_SYNC_INTERVAL  Fleet key sync interval in seconds (default: 300)
set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────

POLL_INTERVAL="${TODO_POLL_INTERVAL:-60}"
REPO_DIR="${DISPATCHER_REPO_DIR:-/workspace/claude-portable}"
MAX_WORKERS="${DISPATCHER_MAX_WORKERS:-5}"
HEALTH_PORT="${DISPATCHER_HEALTH_PORT:-8080}"
RESTART_DELAY="${DISPATCHER_RESTART_DELAY:-10}"
KEY_SYNC_INTERVAL="${DISPATCHER_KEY_SYNC_INTERVAL:-300}"

LOG_FILE="/data/dispatcher.log"
KEY_DIR="${HOME}/.ssh/ccc-keys"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DISPATCH_SCRIPT="${SCRIPT_DIR}/git-dispatch.py"
PID_FILE="/data/dispatcher/daemon.pid"

# ── Preflight ──────────────────────────────────────────────────────────────────

if [ ! -f "$DISPATCH_SCRIPT" ]; then
  echo "ERROR: git-dispatch.py not found at $DISPATCH_SCRIPT"
  exit 1
fi

mkdir -p "$(dirname "$PID_FILE")" "$KEY_DIR"

# Redirect all output to log file (tee to stdout for docker logs)
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== Dispatcher Daemon ==="
echo "  Repo:          $REPO_DIR"
echo "  Poll interval: ${POLL_INTERVAL}s"
echo "  Max workers:   $MAX_WORKERS"
echo "  Health port:   $HEALTH_PORT"
echo "  Log file:      $LOG_FILE"
echo "  Started:       $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

echo $$ > "$PID_FILE"

# ── AWS helpers ────────────────────────────────────────────────────────────────

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

start_key_sync_daemon() {
  (
    while true; do
      sleep "$KEY_SYNC_INTERVAL"
      sync_fleet_keys 2>&1 || true
    done
  ) &
  echo "  Key sync daemon started (PID $!, interval: ${KEY_SYNC_INTERVAL}s)"
}

# ── Dispatcher heartbeat ───────────────────────────────────────────────────────
# Writes a timestamp to S3 and publishes a CloudWatch custom metric every 60s.

HEARTBEAT_INTERVAL="${DISPATCHER_HEARTBEAT_INTERVAL:-60}"
HEARTBEAT_METRIC_NS="ClaudePortable/Dispatcher"
HEARTBEAT_METRIC_NAME="Heartbeat"

write_heartbeat() {
  local account
  account="$(get_aws_account)"
  if [ -z "$account" ]; then
    echo "  [heartbeat] WARNING: Could not determine AWS account ID. Skipping."
    return 0
  fi

  local bucket="claude-portable-state-${account}"
  local instance_name="${DISPATCHER_INSTANCE_NAME:-claude-dispatcher}"
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  # Write heartbeat JSON to S3
  local payload="{\"timestamp\":\"${ts}\",\"instance\":\"${instance_name}\",\"pid\":$$}"
  if echo "$payload" | aws s3 cp - \
      "s3://${bucket}/dispatcher/heartbeat.json" \
      --region "$REGION" \
      --content-type "application/json" 2>/dev/null; then
    : # success
  else
    echo "  [heartbeat] WARNING: S3 write failed"
  fi

  # Publish custom CloudWatch metric (value=1 = alive)
  if aws cloudwatch put-metric-data \
      --namespace "$HEARTBEAT_METRIC_NS" \
      --metric-name "$HEARTBEAT_METRIC_NAME" \
      --value 1 \
      --unit Count \
      --dimensions "Name=InstanceName,Value=${instance_name}" \
      --region "$REGION" 2>/dev/null; then
    : # success
  else
    echo "  [heartbeat] WARNING: CloudWatch metric publish failed"
  fi
}

start_heartbeat_daemon() {
  (
    while true; do
      write_heartbeat 2>&1 || true
      sleep "$HEARTBEAT_INTERVAL"
    done
  ) &
  echo "  Heartbeat daemon started (PID $!, interval: ${HEARTBEAT_INTERVAL}s)"
}

# ── Main watchdog loop ─────────────────────────────────────────────────────────

run_dispatch() {
  python3 "$DISPATCH_SCRIPT" \
    --repo-dir "$REPO_DIR" \
    --interval "$POLL_INTERVAL" \
    --max-workers "$MAX_WORKERS"
}

# ── Startup ────────────────────────────────────────────────────────────────────

# Initial key sync on startup
sync_fleet_keys || true

# Periodic key sync in background
start_key_sync_daemon

# Heartbeat to S3 + CloudWatch (every 60s)
write_heartbeat || true   # write immediately on start
start_heartbeat_daemon

# ── Watchdog ──────────────────────────────────────────────────────────────────

CRASH_COUNT=0
MAX_CRASHES=10
CRASH_WINDOW=300  # seconds -- reset crash count if process runs longer than this

echo ""
echo "[+] Starting git-dispatch.py watchdog (max crashes: ${MAX_CRASHES}, restart delay: ${RESTART_DELAY}s)..."
echo ""

while true; do
  START_TS=$(date +%s)

  echo "[$(date -u +%H:%M:%S)] Starting git-dispatch.py (attempt $((CRASH_COUNT + 1)))..."

  DISPATCH_EXIT=0
  run_dispatch || DISPATCH_EXIT=$?

  END_TS=$(date +%s)
  RUNTIME=$((END_TS - START_TS))

  if [ "$RUNTIME" -gt "$CRASH_WINDOW" ]; then
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

  echo "[$(date -u +%H:%M:%S)] Restarting in ${RESTART_DELAY}s..."
  sleep "$RESTART_DELAY"
done
