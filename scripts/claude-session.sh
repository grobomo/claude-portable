#!/bin/bash
# claude-session: Wrap Claude CLI with per-session conversation logging.
# Each invocation appends to the current session's log file.
# Sessions are identified by CLAUDE_SESSION_ID (auto-generated on SSH connect).
set -euo pipefail

SESSION_DIR="/data/sessions"
SESSION_ID="${CLAUDE_SESSION_ID:-$(date +%Y%m%d-%H%M%S)-$(head -c4 /dev/urandom | xxd -p)}"
SESSION_PATH="$SESSION_DIR/$SESSION_ID"
LOG_FILE="$SESSION_PATH/conversation.log"
META_FILE="$SESSION_PATH/meta.json"

mkdir -p "$SESSION_PATH"

# Write or update metadata
if [ ! -f "$META_FILE" ]; then
  cat > "$META_FILE" << METAEOF
{
  "id": "$SESSION_ID",
  "started": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "hostname": "$(hostname)",
  "ssh_client": "${SSH_CLIENT:-local}",
  "user": "$(whoami)",
  "invocations": 0
}
METAEOF
fi

# Increment invocation count
python3 -c "
import json, sys
with open('$META_FILE') as f: m = json.load(f)
m['invocations'] = m.get('invocations', 0) + 1
m['last_active'] = '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
with open('$META_FILE', 'w') as f: json.dump(m, f, indent=2)
" 2>/dev/null || true

# Log separator
{
  echo ""
  echo "================================================================"
  echo "  Session: $SESSION_ID"
  echo "  Time:    $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "  Args:    $*"
  echo "================================================================"
  echo ""
} >> "$LOG_FILE"

# Run Claude with script to capture full terminal I/O
# script -q suppresses "Script started" messages
# -f flushes after each write so logs are real-time
if [ -t 0 ] && [ -t 1 ]; then
  # Interactive mode -- use script to capture terminal
  script -q -f -a "$LOG_FILE" -c "claude $*"
  EXIT_CODE=${PIPESTATUS[0]:-$?}
else
  # Non-interactive (piped) -- tee stdout and stderr
  claude "$@" 2>&1 | tee -a "$LOG_FILE"
  EXIT_CODE=${PIPESTATUS[0]:-$?}
fi

# Log end marker
{
  echo ""
  echo "[session $SESSION_ID ended at $(date -u +%Y-%m-%dT%H:%M:%SZ) exit=$EXIT_CODE]"
  echo ""
} >> "$LOG_FILE"

# Update metadata with end time
python3 -c "
import json
with open('$META_FILE') as f: m = json.load(f)
m['last_ended'] = '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
m['last_exit_code'] = $EXIT_CODE
with open('$META_FILE', 'w') as f: json.dump(m, f, indent=2)
" 2>/dev/null || true

exit $EXIT_CODE
