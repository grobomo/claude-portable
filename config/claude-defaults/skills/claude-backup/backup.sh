#!/bin/bash
# @hook backup
# @event SessionStart, SessionEnd, PreCompact
# @matcher *
# @async true
# @description Automatically backs up Claude Code configuration on key events.
#   Creates timestamped snapshots of settings.json, CLAUDE.md, hooks/, skills/,
#   and mcp-manager configs. Uses content hashing to skip backups when nothing
#   changed. Keeps last 10 backups and cleans up older ones. Triggered on session
#   start, end, and before context compaction to ensure recovery points exist.

CLAUDE_DIR="$HOME/.claude"
BACKUP_DIR="$CLAUDE_DIR/backups"
LOG_FILE="$BACKUP_DIR/backup.log"
MCP_DIR="$HOME/OneDrive - TrendMicro/Documents/ProjectsCL/MCP/mcp-manager"

CLAUDE_ITEMS=("settings.json" "CLAUDE.md" "hooks" "skills" "config-report.md")
MCP_ITEMS=("servers.yaml" ".env" "capabilities-cache.yaml" "managed-servers")

action="${1:-backup}"
target="$2"
trigger="${TRIGGER:-manual}"

log() {
  mkdir -p "$BACKUP_DIR"
  echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG_FILE"
}

get_hash() {
  cat "$CLAUDE_DIR/settings.json" "$CLAUDE_DIR/CLAUDE.md" "$CLAUDE_DIR/hooks/skill-registry.json" "$MCP_DIR/servers.yaml" 2>/dev/null | md5sum | cut -d' ' -f1
}

case "$action" in
  backup)
    mkdir -p "$BACKUP_DIR"
    log "[$trigger] Checking for changes..."

    current_hash=$(get_hash)
    last_hash=$(cat "$BACKUP_DIR/.last_hash" 2>/dev/null)

    if [ "$last_hash" = "$current_hash" ]; then
      log "[$trigger] Skipped - no changes to settings.json, CLAUDE.md, skill-registry.json, or servers.yaml"
      exit 0
    fi

    name=$(date +"%Y-%m-%d_%H%M%S")
    dest="$BACKUP_DIR/$name"

    log "[$trigger] Creating backup $name..."
    mkdir -p "$dest/mcp-manager"

    for item in "${CLAUDE_ITEMS[@]}"; do
      [ -e "$CLAUDE_DIR/$item" ] && cp -r "$CLAUDE_DIR/$item" "$dest/$item"
    done
    for item in "${MCP_ITEMS[@]}"; do
      [ -e "$MCP_DIR/$item" ] && cp -r "$MCP_DIR/$item" "$dest/mcp-manager/$item"
    done

    echo "$current_hash" > "$BACKUP_DIR/.last_hash"
    log "[$trigger] Backup complete: $name"
    log "[$trigger] Backed up: settings.json, CLAUDE.md, hooks/, skills/, mcp-manager/"
    echo "Created: $name"

    # Cleanup old backups
    old=$(ls -dt "$BACKUP_DIR"/*/ 2>/dev/null | tail -n +11)
    if [ -n "$old" ]; then
      echo "$old" | xargs rm -rf
      log "[$trigger] Cleaned up old backups (keeping last 10)"
    fi
    ;;

  restore)
    src="${target:+$BACKUP_DIR/$target}"
    [ -z "$src" ] && src=$(ls -dt "$BACKUP_DIR"/*/ 2>/dev/null | head -1)

    if [ ! -d "$src" ]; then
      log "[manual] Restore failed - backup not found: $target"
      echo "Not found"
      exit 1
    fi

    backup_name=$(basename "$src")
    log "[manual] Restoring from $backup_name..."

    for item in "${CLAUDE_ITEMS[@]}"; do
      [ -e "$src/$item" ] && cp -r "$src/$item" "$CLAUDE_DIR/$item"
    done
    for item in "${MCP_ITEMS[@]}"; do
      [ -e "$src/mcp-manager/$item" ] && cp -r "$src/mcp-manager/$item" "$MCP_DIR/$item"
    done

    log "[manual] Restore complete from $backup_name"
    echo "Restored: $backup_name"
    ;;

  list)
    ls -1t "$BACKUP_DIR" 2>/dev/null | grep -E "^[0-9]"
    ;;
esac
