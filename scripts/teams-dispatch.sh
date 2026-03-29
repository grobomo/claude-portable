#!/bin/bash
# Teams -> CCC dispatch: polls a Teams chat for @claude mentions,
# dispatches prompts to available ccc instances, replies with results.
#
# Runs locally on the laptop (needs Graph API token + ccc launcher).
#
# Usage:
#   teams-dispatch.sh [poll-interval-seconds]
#
# Environment:
#   TEAMS_CHAT_ID        Teams chat ID to monitor (required)
#   TEAMS_TRIGGER         Trigger keyword (default: @claude)
#   CCC_INSTANCE_NAME    Preferred instance name (optional, auto-selects if unset)
#   CCC_PROJECT          Working directory on instance (default: /workspace)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CCC_DIR="$(dirname "$SCRIPT_DIR")"
TEAMS_CHAT_PY="${TEAMS_CHAT_PY:-teams_chat.py}"
MSGRAPH_LIB="${MSGRAPH_LIB:-msgraph-lib}"

POLL_INTERVAL="${1:-30}"
CHAT_ID="${TEAMS_CHAT_ID:?Set TEAMS_CHAT_ID to the Teams chat ID}"
TRIGGER="${TEAMS_TRIGGER:-@claude}"
INSTANCE_NAME="${CCC_INSTANCE_NAME:-}"
PROJECT="${CCC_PROJECT:-/workspace}"

# Track processed messages to avoid re-dispatching
PROCESSED_FILE="/tmp/teams-dispatch-processed.json"
[ -f "$PROCESSED_FILE" ] || echo '[]' > "$PROCESSED_FILE"

echo "=== Teams -> CCC Dispatch ==="
echo "  Chat ID:   ${CHAT_ID:0:30}..."
echo "  Trigger:   $TRIGGER"
echo "  Poll:      every ${POLL_INTERVAL}s"
echo "  Instance:  ${INSTANCE_NAME:-auto}"
echo ""

# --- Read new messages and find @claude mentions ---
check_messages() {
  python3 -c "
import sys, json, re, os
sys.path.insert(0, '$MSGRAPH_LIB')
from token_manager import graph_get

chat_id = '$CHAT_ID'
trigger = '${TRIGGER}'.lower()
processed_file = '$PROCESSED_FILE'

# Load processed message IDs
with open(processed_file) as f:
    processed = set(json.load(f))

# Fetch last 10 messages
data = graph_get(f'/me/chats/{chat_id}/messages', params={'\$top': 10, '\$orderby': 'createdDateTime desc'})
msgs = data.get('value', [])

new_prompts = []
for m in msgs:
    mid = m.get('id', '')
    if mid in processed:
        continue

    body_html = m.get('body', {}).get('content', '')
    # Strip HTML
    body_text = re.sub(r'<[^>]+>', '', body_html).strip()

    if trigger not in body_text.lower():
        continue

    # Extract prompt: everything after the trigger keyword
    idx = body_text.lower().index(trigger)
    prompt = body_text[idx + len(trigger):].strip()
    if not prompt:
        continue

    sender = '(unknown)'
    fr = m.get('from', {})
    if fr and fr.get('user'):
        sender = fr['user'].get('displayName', '(unknown)')

    new_prompts.append({
        'id': mid,
        'sender': sender,
        'prompt': prompt,
        'timestamp': m.get('createdDateTime', '')[:19]
    })

# Mark all fetched messages as processed (even non-trigger ones, to avoid re-scanning)
for m in msgs:
    processed.add(m.get('id', ''))

with open(processed_file, 'w') as f:
    json.dump(list(processed)[-500:], f)  # Keep last 500 IDs

# Output new prompts as JSON
if new_prompts:
    print(json.dumps(new_prompts))
else:
    print('[]')
" 2>/dev/null
}

# --- Send prompt to a ccc instance ---
dispatch_to_ccc() {
  local prompt="$1"
  local sender="$2"

  echo "  Dispatching to ccc..."

  # Find a running instance
  local instance_flag=""
  if [ -n "$INSTANCE_NAME" ]; then
    instance_flag="-n $INSTANCE_NAME"
  fi

  # Use ccc offload to send the prompt
  local full_prompt="You received this request from ${sender} in Teams chat. Do the work, create branches and PRs as needed. When done, write a SHORT summary (2-3 sentences) of what you did to /tmp/teams-result.txt

Request: ${prompt}"

  python3 "$CCC_DIR/ccc" offload $instance_flag -w "$PROJECT" "$full_prompt" 2>&1 | tail -5
  return $?
}

# --- Reply in Teams (all messages prefixed so people know it's Claude, not Joel) ---
BOT_TAG="[Claude Bot]"

reply_in_teams() {
  local message="$1"
  python3 "$TEAMS_CHAT_PY" send "$CHAT_ID" "${BOT_TAG} ${message}" 2>/dev/null
}

# --- Check for completed results ---
check_result() {
  local ip="$1"
  local ssh_key="$2"

  ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o LogLevel=ERROR \
    -i "$ssh_key" "ubuntu@${ip}" \
    "docker exec claude-portable cat /tmp/teams-result.txt 2>/dev/null" 2>/dev/null || echo ""
}

# --- Main poll loop ---
echo "[+] Starting poll loop..."
PENDING_SENDER=""
PENDING_PROMPT=""

while true; do
  # Check for new @claude messages
  PROMPTS=$(check_messages 2>/dev/null || echo "[]")

  if [ "$PROMPTS" != "[]" ] && [ -n "$PROMPTS" ]; then
    # Process each new prompt
    echo "$PROMPTS" | python3 -c "
import sys, json
prompts = json.load(sys.stdin)
for p in prompts:
    print(f\"{p['sender']}|||{p['prompt']}|||{p['timestamp']}\")
" | while IFS='|||' read -r sender prompt timestamp; do
      echo ""
      echo "[$(date +%H:%M:%S)] New @claude from ${sender}: ${prompt:0:80}"

      # Acknowledge in Teams
      reply_in_teams "On it, ${sender}. Dispatching to cloud Claude..." 2>/dev/null || true

      # Dispatch
      if dispatch_to_ccc "$prompt" "$sender"; then
        echo "  Dispatched successfully."
      else
        echo "  WARNING: Dispatch failed."
        reply_in_teams "Sorry ${sender}, couldn't reach a cloud instance. Try again?" 2>/dev/null || true
      fi
    done
  fi

  sleep "$POLL_INTERVAL"
done
