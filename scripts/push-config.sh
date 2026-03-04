#!/bin/bash
# Push config changes from running container back to git repos.
# Run inside container after modifying rules, hooks, etc.
set -euo pipefail

DEFAULTS_DIR="/opt/claude-portable/defaults"
CLAUDE_DIR="$HOME/.claude"

if [ ! -d "$DEFAULTS_DIR/.git" ]; then
  echo "ERROR: Defaults repo not cloned. Run sync-config.sh first."
  exit 1
fi

echo "=== Pushing config changes to repo ==="

# Copy modified files back to repo
[ -f "$CLAUDE_DIR/CLAUDE.md" ] && cp "$CLAUDE_DIR/CLAUDE.md" "$DEFAULTS_DIR/claude-md/CLAUDE.md"

# Sync hooks
if [ -d "$CLAUDE_DIR/hooks" ]; then
  mkdir -p "$DEFAULTS_DIR/hooks"
  for f in "$CLAUDE_DIR/hooks/"*.js; do
    [ -f "$f" ] && cp "$f" "$DEFAULTS_DIR/hooks/"
  done
fi

# Sync rules
if [ -d "$CLAUDE_DIR/rules" ]; then
  mkdir -p "$DEFAULTS_DIR/instructions"
  rsync -a --delete "$CLAUDE_DIR/rules/" "$DEFAULTS_DIR/instructions/" 2>/dev/null || \
    cp -r "$CLAUDE_DIR/rules/"* "$DEFAULTS_DIR/instructions/"
fi

# Commit and push
cd "$DEFAULTS_DIR"
git add -A
if git diff --cached --quiet; then
  echo "No changes to push."
else
  git commit -m "sync: config update from container $(hostname) $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  git push
  echo "Config pushed to remote."
fi
