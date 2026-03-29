#!/bin/bash
# =============================================================================
# Clawdbot Graceful Shutdown Script
# =============================================================================
# Called before EC2 termination to sync state to S3.
# Triggered by:
# - Spot interruption handler (2-minute warning)
# - Orchestrator Lambda stop action
# - Manual systemctl stop
# =============================================================================

set -e

echo "========================================"
echo "Clawdbot Graceful Shutdown"
echo "$(date)"
echo "========================================"

# Get bucket from environment or SSM
STATE_BUCKET="${STATE_BUCKET:-}"
if [ -z "$STATE_BUCKET" ]; then
    # Try to get from SSM
    STATE_BUCKET=$(aws ssm get-parameter --name /clawdbot/config --query 'Parameter.Value' --output text 2>/dev/null | jq -r '.bucket' || echo "")
fi

if [ -z "$STATE_BUCKET" ]; then
    echo "WARNING: Could not determine STATE_BUCKET, skipping S3 sync"
    exit 0
fi

echo ">>> Syncing Clawdbot config to s3://${STATE_BUCKET}/config/..."
sudo -u clawdbot aws s3 sync /home/clawdbot/.clawdbot/ "s3://${STATE_BUCKET}/config/" --quiet || true

echo ">>> Syncing local share to s3://${STATE_BUCKET}/local-share/..."
sudo -u clawdbot aws s3 sync /home/clawdbot/.local/share/ "s3://${STATE_BUCKET}/local-share/" --quiet || true

echo ">>> Stopping Clawdbot service..."
systemctl stop clawdbot || true

echo "========================================"
echo "Shutdown Complete"
echo "$(date)"
echo "========================================"
