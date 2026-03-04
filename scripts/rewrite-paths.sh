#!/bin/bash
# Rewrite Windows paths to Linux container paths in all config files.
set -euo pipefail

CLAUDE_DIR="$HOME/.claude"

# Rewrite a single file: replace Windows paths with container paths
rewrite_file() {
  local file="$1"
  [ -f "$file" ] || return 0

  sed -i \
    -e 's|C:/Users/joelg/.claude|'"$HOME"'/.claude|g' \
    -e 's|C:\\Users\\joelg\\.claude|'"$HOME"'/.claude|g' \
    -e 's|/c/Users/joelg/.claude|'"$HOME"'/.claude|g' \
    -e 's|C:/Users/joelg/OneDrive - TrendMicro/Documents/ProjectsCL/MCP|/opt/mcp|g' \
    -e 's|/c/Users/joelg/OneDrive - TrendMicro/Documents/ProjectsCL/MCP|/opt/mcp|g' \
    -e 's|ProjectsCL/MCP|/opt/mcp|g' \
    "$file" 2>/dev/null || true
}

# Rewrite settings.json
rewrite_file "$CLAUDE_DIR/settings.json"

# Rewrite hook .js files
if [ -d "$CLAUDE_DIR/hooks" ]; then
  for f in "$CLAUDE_DIR/hooks/"*.js; do
    [ -f "$f" ] && rewrite_file "$f"
  done
fi

# Rewrite servers.yaml files
if [ -d /opt/mcp ]; then
  find /opt/mcp -name "servers.yaml" -exec bash -c 'rewrite_file "$1"' _ {} \; 2>/dev/null || true
fi

# Generate container .mcp.json
MCP_MANAGER_PATH="/opt/mcp/mcp-manager"
MCP_JSON="$CLAUDE_DIR/.mcp.json"
SERVERS="${CLAUDE_PORTABLE_SERVERS:-wiki-lite,v1-lite,jira-lite,trello-lite}"

# Build servers JSON array
SERVERS_JSON=$(python3 -c "
import json, sys
names = [s.strip() for s in '$SERVERS'.split(',') if s.strip()]
print(json.dumps(names))
")

if [ -d "$MCP_MANAGER_PATH" ]; then
  if [ -f "$MCP_MANAGER_PATH/build/index.js" ]; then
    ENTRY="$MCP_MANAGER_PATH/build/index.js"
    cat > "$MCP_JSON" <<MCPEOF
{
  "mcpServers": {
    "mcp-manager": {
      "command": "node",
      "args": ["$ENTRY"],
      "env": {},
      "servers": $SERVERS_JSON
    }
  }
}
MCPEOF
    echo "  Generated $MCP_JSON (node)"
  elif [ -f "$MCP_MANAGER_PATH/server.py" ]; then
    cat > "$MCP_JSON" <<MCPEOF
{
  "mcpServers": {
    "mcp-manager": {
      "command": "python3",
      "args": ["$MCP_MANAGER_PATH/server.py"],
      "env": {},
      "servers": $SERVERS_JSON
    }
  }
}
MCPEOF
    echo "  Generated $MCP_JSON (python)"
  fi
else
  echo "  mcp-manager not found, skipping .mcp.json"
fi

echo "  Path rewriting complete."
