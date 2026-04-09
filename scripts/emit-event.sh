#!/bin/bash
# emit-event.sh -- Structured event emission for CCC worker telemetry.
# Source this file, then call emit_event from any script.
#
# Usage:
#   source /opt/claude-portable/scripts/emit-event.sh
#   emit_event "task.started" "picked up task 5"
#
# Environment (set by caller):
#   INSTANCE_ID         Worker identifier (default: hostname)
#   CURRENT_TASK_ID     Active task (e.g. "task-5")
#   CURRENT_STAGE       Active pipeline stage (e.g. "IMPLEMENT")
#   CLAUDE_EVENT_LOG    Event log path (default: /data/events.jsonl)

CLAUDE_EVENT_LOG="${CLAUDE_EVENT_LOG:-}"
_EMIT_EVENT_MAX_SIZE=$((10 * 1024 * 1024))  # 10MB rotation threshold

# emit_event <event-type> [detail-string]
#
# Appends a single JSONL line to the event log.
# No-op if CLAUDE_EVENT_LOG is not set (local dev -- nobody reads the file).
# On workers, bootstrap.sh sets CLAUDE_EVENT_LOG=/data/events.jsonl.
emit_event() {
  [ -n "$CLAUDE_EVENT_LOG" ] || return 0
  local event_type="${1:?emit_event requires an event type}"
  local detail="${2:-}"
  local ts worker_id task_id stage

  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  worker_id="${INSTANCE_ID:-${CLAUDE_PORTABLE_ID:-$(hostname 2>/dev/null || echo unknown)}}"
  task_id="${CURRENT_TASK_ID:-}"
  stage="${CURRENT_STAGE:-}"

  # Escape double quotes and backslashes in detail string for valid JSON
  detail="${detail//\\/\\\\}"
  detail="${detail//\"/\\\"}"
  # Strip newlines -- JSONL must be single-line
  detail="${detail//$'\n'/ }"
  detail="${detail//$'\r'/}"

  local line
  line=$(printf '{"ts":"%s","event":"%s","source":"continuous-claude","worker_id":"%s","task_id":"%s","stage":"%s","detail":"%s"}' \
    "$ts" "$event_type" "$worker_id" "$task_id" "$stage" "$detail")

  # Rotate if over threshold
  _emit_event_maybe_rotate

  # Append (fail silently if path is unwritable)
  printf '%s\n' "$line" >> "$CLAUDE_EVENT_LOG" 2>/dev/null
}

# _emit_event_maybe_rotate
# Rotates the event log if it exceeds the size threshold.
# Keeps at most 2 files: events.jsonl (current) + events.jsonl.1 (previous).
_emit_event_maybe_rotate() {
  [ -f "$CLAUDE_EVENT_LOG" ] || return 0

  local size
  size=$(stat -c%s "$CLAUDE_EVENT_LOG" 2>/dev/null || stat -f%z "$CLAUDE_EVENT_LOG" 2>/dev/null || echo 0)

  if [ "$size" -ge "$_EMIT_EVENT_MAX_SIZE" ] 2>/dev/null; then
    rm -f "${CLAUDE_EVENT_LOG}.2" 2>/dev/null
    [ -f "${CLAUDE_EVENT_LOG}.1" ] && mv "${CLAUDE_EVENT_LOG}.1" "${CLAUDE_EVENT_LOG}.2" 2>/dev/null
    mv "$CLAUDE_EVENT_LOG" "${CLAUDE_EVENT_LOG}.1" 2>/dev/null
    # Signal rotation for S3 sync
    touch "${CLAUDE_EVENT_LOG}.rotated" 2>/dev/null
  fi
}
