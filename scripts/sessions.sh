#!/bin/bash
# sessions: List, view, search, and tail session logs.
set -euo pipefail

SESSION_DIR="/data/sessions"

usage() {
  cat << 'EOF'
sessions -- Manage Claude conversation sessions

COMMANDS:
  list [N]           List recent sessions (default: 20)
  view <id>          View full conversation log for a session
  tail <id> [N]      Show last N lines of a session (default: 50)
  search <pattern>   Search all sessions for a pattern (grep)
  meta <id>          Show session metadata (JSON)
  active             Show currently active sessions
  export <id>        Export session log to /data/exports/<id>.txt
  clean [days]       Delete sessions older than N days (default: 30)
  current            Show current session ID and log path

ENVIRONMENT:
  CLAUDE_SESSION_ID  Current session tracking ID (set on SSH connect)
EOF
}

list_sessions() {
  local limit="${1:-20}"
  echo "Recent sessions (last $limit):"
  echo "-------------------------------------------------------------------"
  printf "%-28s %-20s %-6s %s\n" "SESSION ID" "STARTED" "RUNS" "STATUS"
  echo "-------------------------------------------------------------------"

  # Sort by modification time, newest first
  find "$SESSION_DIR" -maxdepth 1 -mindepth 1 -type d -printf '%T@ %f\n' 2>/dev/null \
    | sort -rn | head -n "$limit" | while read -r _ sid; do
    meta="$SESSION_DIR/$sid/meta.json"
    if [ -f "$meta" ]; then
      python3 -c "
import json, sys
with open('$meta') as f: m = json.load(f)
started = m.get('started', '?')[:19]
runs = m.get('invocations', 0)
active = '  <<< ACTIVE' if '$sid' == '${CLAUDE_SESSION_ID:-}' else ''
print(f'  {m[\"id\"]:<26s} {started:<20s} {runs:<6d}{active}')
" 2>/dev/null
    else
      printf "  %-26s %-20s %-6s\n" "$sid" "?" "?"
    fi
  done
}

view_session() {
  local sid="$1"
  local log="$SESSION_DIR/$sid/conversation.log"
  if [ ! -f "$log" ]; then
    echo "Session not found: $sid"
    echo "Use 'sessions list' to see available sessions."
    exit 1
  fi
  # Use less if available, otherwise cat
  if command -v less &>/dev/null; then
    less -R "$log"
  else
    cat "$log"
  fi
}

tail_session() {
  local sid="$1"
  local lines="${2:-50}"
  local log="$SESSION_DIR/$sid/conversation.log"
  if [ ! -f "$log" ]; then
    echo "Session not found: $sid"
    exit 1
  fi
  tail -n "$lines" "$log"
}

search_sessions() {
  local pattern="$1"
  echo "Searching all sessions for: $pattern"
  echo "-------------------------------------------------------------------"
  grep -rl "$pattern" "$SESSION_DIR"/*/conversation.log 2>/dev/null | while read -r logfile; do
    sid=$(basename "$(dirname "$logfile")")
    echo ""
    echo "=== Session: $sid ==="
    grep -n --color=always "$pattern" "$logfile" | head -10
  done
}

show_meta() {
  local sid="$1"
  local meta="$SESSION_DIR/$sid/meta.json"
  if [ ! -f "$meta" ]; then
    echo "Session not found: $sid"
    exit 1
  fi
  python3 -m json.tool "$meta"
}

show_active() {
  echo "Active sessions:"
  echo "-------------------------------------------------------------------"
  # Check which sessions have been active in the last 5 minutes
  find "$SESSION_DIR" -maxdepth 2 -name "conversation.log" -mmin -5 2>/dev/null | while read -r logfile; do
    sid=$(basename "$(dirname "$logfile")")
    meta="$SESSION_DIR/$sid/meta.json"
    if [ -f "$meta" ]; then
      python3 -c "
import json
with open('$meta') as f: m = json.load(f)
print(f'  {m[\"id\"]}  (last active: {m.get(\"last_active\", \"?\")}, runs: {m.get(\"invocations\", 0)})')
" 2>/dev/null
    fi
  done
}

export_session() {
  local sid="$1"
  local log="$SESSION_DIR/$sid/conversation.log"
  if [ ! -f "$log" ]; then
    echo "Session not found: $sid"
    exit 1
  fi
  mkdir -p /data/exports
  local out="/data/exports/${sid}.txt"
  # Strip ANSI escape codes for clean export
  sed 's/\x1b\[[0-9;]*m//g' "$log" > "$out"
  echo "Exported to: $out ($(wc -l < "$out") lines, $(du -h "$out" | cut -f1))"
}

clean_sessions() {
  local days="${1:-30}"
  echo "Deleting sessions older than $days days..."
  local count=0
  find "$SESSION_DIR" -maxdepth 1 -mindepth 1 -type d -mtime "+$days" 2>/dev/null | while read -r dir; do
    sid=$(basename "$dir")
    rm -rf "$dir"
    echo "  Deleted: $sid"
    count=$((count + 1))
  done
  echo "Cleaned $count sessions."
}

show_current() {
  if [ -z "${CLAUDE_SESSION_ID:-}" ]; then
    echo "No active session. SSH into the container to start one."
  else
    echo "Current session: $CLAUDE_SESSION_ID"
    echo "Log: $SESSION_DIR/$CLAUDE_SESSION_ID/conversation.log"
    if [ -f "$SESSION_DIR/$CLAUDE_SESSION_ID/meta.json" ]; then
      python3 -m json.tool "$SESSION_DIR/$CLAUDE_SESSION_ID/meta.json"
    fi
  fi
}

# --- Main ---
case "${1:-help}" in
  list)    list_sessions "${2:-20}" ;;
  view)    view_session "${2:?Usage: sessions view <id>}" ;;
  tail)    tail_session "${2:?Usage: sessions tail <id> [lines]}" "${3:-50}" ;;
  search)  search_sessions "${2:?Usage: sessions search <pattern>}" ;;
  meta)    show_meta "${2:?Usage: sessions meta <id>}" ;;
  active)  show_active ;;
  export)  export_session "${2:?Usage: sessions export <id>}" ;;
  clean)   clean_sessions "${2:-30}" ;;
  current) show_current ;;
  help|--help|-h) usage ;;
  *)       echo "Unknown command: $1"; usage; exit 1 ;;
esac
