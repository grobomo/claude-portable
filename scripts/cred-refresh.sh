#!/bin/bash
# Background credential refresher.
# Checks if token is about to expire and pulls fresh one from S3.
# Runs as a background daemon inside the container.
#
# Usage: cred-refresh.sh [check_interval_minutes]
#
# Paired with local-side: cpp uploads fresh tokens to S3 periodically.
set -euo pipefail

INTERVAL="${1:-15}"  # check every 15 minutes
CREDS_FILE="${HOME}/.claude/.credentials.json"
REGION="${AWS_DEFAULT_REGION:-us-east-2}"
BUCKET=""
REFRESH_THRESHOLD_HOURS=1  # refresh when less than 1 hour remaining

get_bucket() {
  ACCT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")
  [ -n "$ACCT" ] && echo "claude-portable-state-$ACCT" || echo ""
}

check_and_refresh() {
  [ -f "$CREDS_FILE" ] || return 0

  # Check time remaining
  REMAINING=$(python3 -c "
import json, time
try:
    d = json.load(open('$CREDS_FILE'))
    exp = d.get('claudeAiOauth', {}).get('expiresAt', 0) / 1000
    remaining = (exp - time.time()) / 3600
    print(f'{remaining:.2f}')
except:
    print('999')
" 2>/dev/null)

  # If more than threshold remaining, skip
  if python3 -c "exit(0 if float('$REMAINING') > $REFRESH_THRESHOLD_HOURS else 1)" 2>/dev/null; then
    return 0
  fi

  echo "[$(date -u +%H:%M:%S)] Token expires in ${REMAINING}h, refreshing..."

  # Try 1: Let Claude Code refresh its own token
  if command -v claude &>/dev/null; then
    # Run a no-op to trigger internal refresh
    timeout 30 claude -p "echo ok" --max-turns 1 &>/dev/null || true

    # Check if it updated
    NEW_REMAINING=$(python3 -c "
import json, time
try:
    d = json.load(open('$CREDS_FILE'))
    exp = d.get('claudeAiOauth', {}).get('expiresAt', 0) / 1000
    print(f'{(exp - time.time()) / 3600:.2f}')
except:
    print('0')
" 2>/dev/null)

    if python3 -c "exit(0 if float('$NEW_REMAINING') > float('$REMAINING') else 1)" 2>/dev/null; then
      echo "  Self-refreshed. New expiry: ${NEW_REMAINING}h"
      # Push updated creds to S3 for other instances
      [ -n "$BUCKET" ] && aws s3 cp "$CREDS_FILE" "s3://$BUCKET/shared-creds/credentials.json" \
        --region "$REGION" --sse AES256 --quiet 2>/dev/null || true
      return 0
    fi
  fi

  # Try 2: Pull fresh creds from S3 (uploaded by local machine or another instance)
  if [ -n "$BUCKET" ]; then
    REMOTE_CREDS=$(aws s3 cp "s3://$BUCKET/shared-creds/credentials.json" - \
      --region "$REGION" 2>/dev/null || echo "")
    if [ -n "$REMOTE_CREDS" ]; then
      REMOTE_EXP=$(echo "$REMOTE_CREDS" | python3 -c "
import json, sys, time
try:
    d = json.load(sys.stdin)
    exp = d.get('claudeAiOauth', {}).get('expiresAt', 0) / 1000
    print(f'{(exp - time.time()) / 3600:.2f}')
except:
    print('0')
" 2>/dev/null)

      if python3 -c "exit(0 if float('$REMOTE_EXP') > float('$REMAINING') else 1)" 2>/dev/null; then
        echo "$REMOTE_CREDS" > "$CREDS_FILE"
        chmod 600 "$CREDS_FILE"
        echo "  Pulled fresh creds from S3. New expiry: ${REMOTE_EXP}h"
        return 0
      fi
    fi
  fi

  echo "  WARNING: Could not refresh. Token expires in ${REMAINING}h."
}

# Main loop
BUCKET=$(get_bucket)
echo "Credential refresh daemon started (check every ${INTERVAL}min, threshold: ${REFRESH_THRESHOLD_HOURS}h)"
[ -n "$BUCKET" ] && echo "  S3 bucket: $BUCKET" || echo "  S3: not available (no AWS creds)"

while true; do
  check_and_refresh
  sleep $((INTERVAL * 60))
done
