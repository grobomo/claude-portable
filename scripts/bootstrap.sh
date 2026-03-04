#!/bin/bash
set -euo pipefail

echo "=== Claude Portable Bootstrap ==="

# --- Step 1: Fetch secrets from Bitwarden ---
echo "[1/6] Fetching secrets from Bitwarden..."
if [ -n "${BWS_ACCESS_TOKEN:-}" ]; then
  /opt/claude-portable/scripts/inject-secrets.sh
  echo "  Secrets injected from Bitwarden Secrets Manager."
else
  echo "  WARNING: BWS_ACCESS_TOKEN not set. Skipping secret injection."
fi

# --- Step 2: Set up Claude auth ---
echo "[2/6] Setting up Claude authentication..."
CREDS_FILE="$HOME/.claude/.credentials.json"
if [ -f "$CREDS_FILE" ]; then
  echo "  OAuth credentials already present (mounted volume)."
elif [ -n "${CLAUDE_SETUP_TOKEN:-}" ]; then
  # Use setup-token for enterprise auth
  echo "$CLAUDE_SETUP_TOKEN" | claude setup-token 2>/dev/null || true
  echo "  Authenticated via setup-token."
else
  echo "  WARNING: No auth configured. Run 'claude login' or provide CLAUDE_SETUP_TOKEN."
fi

# --- Step 3: Pull config from repos ---
echo "[3/6] Syncing config from repos..."
/opt/claude-portable/scripts/sync-config.sh

# --- Step 4: Rewrite paths for container ---
echo "[4/6] Rewriting paths for container..."
/opt/claude-portable/scripts/rewrite-paths.sh

# --- Step 5: SSH server for file sync ---
echo "[5/6] Starting SSH server..."
if [ -n "${SSH_PUBLIC_KEY:-}" ]; then
  mkdir -p "$HOME/.ssh"
  echo "$SSH_PUBLIC_KEY" >> "$HOME/.ssh/authorized_keys"
  chmod 700 "$HOME/.ssh" && chmod 600 "$HOME/.ssh/authorized_keys"
fi
if [ -f "$HOME/.ssh/authorized_keys" ]; then
  sudo /usr/sbin/sshd
  echo "  SSH server running on port 22."
else
  echo "  No SSH key provided. SSH disabled."
fi

# --- Step 6: Install MCP dependencies ---
echo "[6/6] Installing MCP server dependencies..."
for dir in /opt/mcp/mcp-*/; do
  if [ -f "$dir/package.json" ]; then
    (cd "$dir" && npm install --production --silent 2>/dev/null && \
     [ -f package.json ] && grep -q '"build"' package.json && npm run build --silent 2>/dev/null) || true
  fi
  if [ -f "$dir/requirements.txt" ]; then
    python3 -m pip install --break-system-packages -q -r "$dir/requirements.txt" 2>/dev/null || true
  fi
done

echo ""
echo "=== Claude Portable Ready ==="
echo "  Config:    $HOME/.claude/"
echo "  Workspace: /workspace/"
echo "  MCP:       /opt/mcp/"
echo ""

exec "$@"
