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
REFRESH_THRESHOLD_HOURS=1  # refresh when less than 1 hour remaining

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

  # Let Claude Code refresh its own token via a lightweight invocation
  if command -v claude &>/dev/null; then
    timeout 30 claude -p "ok" --max-turns 1 &>/dev/null || true

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
      return 0
    fi
  fi

  echo "  WARNING: Self-refresh failed. Token expires in ${REMAINING}h."
  echo "  Reconnect with 'cpp' to push fresh credentials."
}

# Main loop
echo "Credential refresh daemon started (check every ${INTERVAL}min, threshold: ${REFRESH_THRESHOLD_HOURS}h)"
echo "  Refresh method: Claude Code self-refresh (no tokens stored in S3)"

while true; do
  check_and_refresh
  sleep $((INTERVAL * 60))
done
