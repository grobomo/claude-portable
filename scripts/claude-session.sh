#!/bin/bash
# claude-session: Wrap Claude CLI with per-session conversation logging.
# Usage:
#   claude "do something"          -> claude -p "do something" (logged)
#   claude -p "do something"       -> claude -p "do something" (logged)
#   claude                         -> interactive claude (terminal captured)
#
# All prompts and responses are logged to:
#   /data/sessions/$CLAUDE_SESSION_ID/conversation.log
set -euo pipefail

SESSION_DIR="/data/sessions"
SESSION_ID="${CLAUDE_SESSION_ID:-$(date +%Y%m%d-%H%M%S)-$(head -c4 /dev/urandom | xxd -p)}"
SESSION_PATH="$SESSION_DIR/$SESSION_ID"
LOG_FILE="$SESSION_PATH/conversation.log"
META_FILE="$SESSION_PATH/meta.json"

mkdir -p "$SESSION_PATH"

# --- Metadata ---
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
import json
with open('$META_FILE') as f: m = json.load(f)
m['invocations'] = m.get('invocations', 0) + 1
m['last_active'] = '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
with open('$META_FILE', 'w') as f: json.dump(m, f, indent=2)
" 2>/dev/null || true

# --- Determine mode ---
# If first arg doesn't start with "-", treat it as a prompt (auto -p)
PROMPT_MODE=false
PROMPT_TEXT=""

if [ $# -eq 0 ]; then
  # No args = check for resumable sessions, offer --resume by default
  CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
  HAS_SESSIONS=$(find "$CLAUDE_DIR/projects" -name "*.jsonl" -type f 2>/dev/null | head -1)
  if [ -n "$HAS_SESSIONS" ]; then
    set -- --resume
  fi
  PROMPT_MODE=false
elif [ "$1" = "-p" ]; then
  # Explicit -p flag
  PROMPT_MODE=true
  shift
  PROMPT_TEXT="$*"
elif [[ "$1" != -* ]]; then
  # First arg is not a flag = treat as prompt
  PROMPT_MODE=true
  PROMPT_TEXT="$*"
fi

TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [ "$PROMPT_MODE" = true ]; then
  # --- Prompt mode: log prompt, capture response, log response ---
  {
    echo ""
    echo "================================================================"
    echo "  [$TIMESTAMP] Invocation #$(python3 -c "import json; print(json.load(open('$META_FILE')).get('invocations',0))" 2>/dev/null || echo '?')"
    echo "================================================================"
    echo ""
    echo ">>> PROMPT:"
    echo "$PROMPT_TEXT"
    echo ""
  } >> "$LOG_FILE"

  # Run claude -p and capture output
  RESPONSE_FILE="$SESSION_PATH/.response.tmp"
  EXIT_CODE=0
  claude -p "$PROMPT_TEXT" > "$RESPONSE_FILE" 2>&1 || EXIT_CODE=$?

  # Log the response
  {
    echo "<<< RESPONSE:"
    cat "$RESPONSE_FILE"
    echo ""
    echo "[exit=$EXIT_CODE]"
    echo ""
  } >> "$LOG_FILE"

  # Print response to stdout so caller sees it
  cat "$RESPONSE_FILE"
  rm -f "$RESPONSE_FILE"

else
  # --- Interactive mode: capture full terminal I/O ---
  {
    echo ""
    echo "================================================================"
    echo "  [$TIMESTAMP] Interactive session"
    echo "  Args: $*"
    echo "================================================================"
    echo ""
  } >> "$LOG_FILE"

  if [ -t 0 ] && [ -t 1 ]; then
    script -q -f -a "$LOG_FILE" -c "claude $*"
    EXIT_CODE=${PIPESTATUS[0]:-$?}
  else
    claude "$@" 2>&1 | tee -a "$LOG_FILE"
    EXIT_CODE=${PIPESTATUS[0]:-$?}
  fi
fi

# --- End marker ---
{
  echo "[ended $(date -u +%Y-%m-%dT%H:%M:%SZ) exit=$EXIT_CODE]"
  echo ""
} >> "$LOG_FILE"

# Update metadata
python3 -c "
import json
with open('$META_FILE') as f: m = json.load(f)
m['last_ended'] = '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
m['last_exit_code'] = $EXIT_CODE
with open('$META_FILE', 'w') as f: json.dump(m, f, indent=2)
" 2>/dev/null || true

exit $EXIT_CODE
