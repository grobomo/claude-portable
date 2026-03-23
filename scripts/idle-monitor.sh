#!/bin/bash
# Idle monitor -- stops the EC2 instance when Claude is inactive.
# Runs inside the container, checks for active Claude processes.
# If idle for IDLE_TIMEOUT minutes, pushes state to S3 and stops the instance.
#
# Usage: idle-monitor.sh [timeout_minutes]
set -euo pipefail

IDLE_TIMEOUT="${1:-${CLAUDE_PORTABLE_IDLE_TIMEOUT:-30}}"
CHECK_INTERVAL=60  # seconds between checks
IDLE_COUNT=0
IDLE_MAX=$((IDLE_TIMEOUT * 60 / CHECK_INTERVAL))

echo "Idle monitor started: will stop instance after ${IDLE_TIMEOUT}min of inactivity."
echo "  Check interval: ${CHECK_INTERVAL}s, checks needed: ${IDLE_MAX}"

while true; do
  # Check if any Claude process is running (the CLI, not our scripts)
  CLAUDE_PROCS=$(pgrep -f "node.*claude" 2>/dev/null | wc -l || echo "0")
  # Also check for active SSH sessions (someone connected)
  SSH_SESSIONS=$(who 2>/dev/null | wc -l || echo "0")
  # Check if any interactive bash is running (docker exec)
  INTERACTIVE=$(pgrep -f "bash -l" 2>/dev/null | grep -v $$ | wc -l || echo "0")

  ACTIVE=$((CLAUDE_PROCS + SSH_SESSIONS + INTERACTIVE))

  if [ "$ACTIVE" -gt 0 ]; then
    if [ "$IDLE_COUNT" -gt 0 ]; then
      echo "  Activity detected (procs=$CLAUDE_PROCS, ssh=$SSH_SESSIONS). Resetting idle counter."
    fi
    IDLE_COUNT=0
  else
    IDLE_COUNT=$((IDLE_COUNT + 1))
    ELAPSED=$((IDLE_COUNT * CHECK_INTERVAL / 60))
    echo "  Idle: ${ELAPSED}/${IDLE_TIMEOUT}min"
  fi

  if [ "$IDLE_COUNT" -ge "$IDLE_MAX" ]; then
    echo "  Instance idle for ${IDLE_TIMEOUT}min. Shutting down..."

    # Push state to S3 before stopping
    /opt/claude-portable/scripts/state-sync.sh push 2>/dev/null || true

    # Get instance ID from EC2 metadata and stop ourselves
    TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
      -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" 2>/dev/null || echo "")
    if [ -n "$TOKEN" ]; then
      INSTANCE_ID=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
        http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null || echo "")
      REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
        http://169.254.169.254/latest/meta-data/placement/region 2>/dev/null || echo "us-east-2")
      if [ -n "$INSTANCE_ID" ]; then
        echo "  Stopping instance $INSTANCE_ID..."
        aws ec2 stop-instances --instance-ids "$INSTANCE_ID" --region "$REGION" 2>/dev/null || true
      fi
    fi

    # Fallback: if metadata not available (e.g. inside container), use sudo shutdown
    sudo shutdown -h now 2>/dev/null || true
    exit 0
  fi

  sleep "$CHECK_INTERVAL"
done
