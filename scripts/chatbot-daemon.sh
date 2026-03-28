#!/bin/bash
# chatbot-daemon.sh — Fetch Graph token and run teams-chat-bridge.py with watchdog.
# Runs inside the chatbot container (CHATBOT_MODE=true).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="/data/chatbot"
TOKEN_FILE="$LOG_DIR/graph-token.json"
SECRET_NAME="${CHATBOT_TEAMS_SECRET_NAME:-claude-portable/graph-token}"
CHAT_ID="${CHATBOT_TEAMS_CHAT_ID:-}"
TRIGGER="${CHATBOT_TEAMS_TRIGGER:-@claude}"
POLL_INTERVAL="${CHATBOT_TEAMS_POLL_INTERVAL:-30}"
WORKSPACE="${CHATBOT_TODO_REPO_DIR:-/workspace/claude-portable}"

mkdir -p "$LOG_DIR"

echo "=== Chatbot Daemon ==="
echo "  Secret:    $SECRET_NAME"
echo "  Token:     $TOKEN_FILE"
echo "  Chat:      ${CHAT_ID:+(set)}"
echo "  Trigger:   $TRIGGER"
echo "  Poll:      every ${POLL_INTERVAL}s"
echo "  Workspace: $WORKSPACE"
echo ""

# ── Step 1: Fetch Graph token from Secrets Manager ───────────────────────────
fetch_graph_token() {
  local region
  region=$(curl -sf -X PUT "http://169.254.169.254/latest/api/token" \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" \
    --connect-timeout 2 2>/dev/null || true)

  if [ -n "$region" ]; then
    region=$(curl -sf -H "X-aws-ec2-metadata-token: $region" \
      "http://169.254.169.254/latest/meta-data/placement/region" \
      --connect-timeout 2 2>/dev/null || echo "${AWS_DEFAULT_REGION:-us-east-2}")
  else
    region="${AWS_DEFAULT_REGION:-us-east-2}"
  fi

  echo "  Fetching Graph token from Secrets Manager ($region)..."
  local raw
  raw=$(aws secretsmanager get-secret-value \
    --region "$region" \
    --secret-id "$SECRET_NAME" \
    --query SecretString \
    --output text 2>&1) || {
    echo "  ERROR: Failed to fetch Graph token: $raw"
    return 1
  }

  echo "$raw" > "$TOKEN_FILE"
  chmod 600 "$TOKEN_FILE"
  echo "  Graph token written to $TOKEN_FILE"
}

if ! fetch_graph_token; then
  echo "  WARNING: Could not fetch Graph token. Teams polling will not start."
  echo "  Container will stay running for SSH/web-chat access."
  exec sleep infinity
fi

# ── Step 2: Validate required config ─────────────────────────────────────────
if [ -z "$CHAT_ID" ]; then
  echo "  WARNING: CHATBOT_TEAMS_CHAT_ID is not set. Teams polling disabled."
  echo "  Container will stay running for SSH/web-chat access."
  exec sleep infinity
fi

export GRAPH_TOKEN_FILE="$TOKEN_FILE"

# ── Step 3: Token refresh daemon (every 50min) ───────────────────────────────
refresh_token_loop() {
  while true; do
    sleep 3000  # 50 minutes
    echo "  [$(date -u +%H:%M:%S)] Refreshing Graph token..."
    fetch_graph_token 2>/dev/null || echo "  WARNING: Token refresh failed (will retry)"
  done
}
refresh_token_loop >> "$LOG_DIR/token-refresh.log" 2>&1 &
echo "  Token refresh daemon started (every 50min)"

# ── Step 4: Run teams-chat-bridge.py with watchdog ───────────────────────────
BRIDGE_SCRIPT="$SCRIPT_DIR/teams-chat-bridge.py"
if [ ! -f "$BRIDGE_SCRIPT" ]; then
  # Try the installed path
  BRIDGE_SCRIPT="/opt/claude-portable/scripts/teams-chat-bridge.py"
fi

if [ ! -f "$BRIDGE_SCRIPT" ]; then
  echo "  ERROR: teams-chat-bridge.py not found"
  exec sleep infinity
fi

echo ""
echo "[+] Starting Teams chat bridge (chatbot mode)..."
echo "    Log: $LOG_DIR/teams-chat-bridge.log"
echo ""

CRASH_COUNT=0
MAX_RAPID_CRASHES=10
RAPID_CRASH_WINDOW=60

while true; do
  START_TS=$(date +%s)

  python3 "$BRIDGE_SCRIPT" \
    --chat-id "$CHAT_ID" \
    --trigger "$TRIGGER" \
    --interval "$POLL_INTERVAL" \
    --workspace "$WORKSPACE" \
    >> "$LOG_DIR/teams-chat-bridge.log" 2>&1

  EXIT_CODE=$?
  END_TS=$(date +%s)
  ELAPSED=$(( END_TS - START_TS ))

  echo "  [$(date -u +%H:%M:%S)] teams-chat-bridge.py exited (code=$EXIT_CODE, ran ${ELAPSED}s)"

  if [ $ELAPSED -lt $RAPID_CRASH_WINDOW ]; then
    CRASH_COUNT=$(( CRASH_COUNT + 1 ))
    if [ $CRASH_COUNT -ge $MAX_RAPID_CRASHES ]; then
      echo "  ERROR: Too many rapid crashes ($CRASH_COUNT in ${RAPID_CRASH_WINDOW}s). Stopping."
      echo "  Check: $LOG_DIR/teams-chat-bridge.log"
      exit 1
    fi
    echo "  Rapid crash #$CRASH_COUNT — waiting 10s before restart..."
    sleep 10
  else
    CRASH_COUNT=0
    echo "  Restarting teams-chat-bridge.py..."
    sleep 2
  fi
done
