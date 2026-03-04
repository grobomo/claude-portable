#!/bin/bash
set -euo pipefail

echo "=== Claude Portable Bootstrap ==="

# --- Step 1: Inject secrets (BWS or direct env vars) ---
echo "[1/6] Injecting secrets..."
/opt/claude-portable/scripts/inject-secrets.sh

# --- Step 2: Verify Claude auth + skip onboarding ---
echo "[2/6] Verifying Claude authentication..."
CREDS_FILE="$HOME/.claude/.credentials.json"
if [ -f "$CREDS_FILE" ]; then
  echo "  OAuth credentials present."
elif [ -n "${CLAUDE_SETUP_TOKEN:-}" ]; then
  echo "$CLAUDE_SETUP_TOKEN" | claude setup-token 2>/dev/null || true
  echo "  Authenticated via setup-token."
else
  echo "  WARNING: No auth configured. Set CLAUDE_OAUTH_ACCESS_TOKEN or BWS_ACCESS_TOKEN."
fi

# Mark onboarding complete so Claude doesn't show first-run wizard
mkdir -p "$HOME/.claude"
if [ ! -f "$HOME/.claude/settings.local.json" ]; then
  cat > "$HOME/.claude/settings.local.json" << 'SETTINGS_LOCAL_EOF'
{
  "hasCompletedOnboarding": true,
  "theme": "dark",
  "verbose": false,
  "preferredNotifChannel": "terminal"
}
SETTINGS_LOCAL_EOF
  echo "  Onboarding marked complete."
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

# --- Step 6: Install MCP dependencies + inject tokens ---
echo "[6/6] Installing MCP server dependencies..."
for dir in /opt/mcp/mcp-*/; do
  [ -d "$dir" ] || continue
  svc=$(basename "$dir")
  if [ -f "$dir/package.json" ]; then
    (cd "$dir" && npm install --production --silent 2>/dev/null && \
     [ -f package.json ] && grep -q '"build"' package.json && npm run build --silent 2>/dev/null) || true
  fi
  if [ -f "$dir/requirements.txt" ]; then
    python3 -m pip install --break-system-packages -q -r "$dir/requirements.txt" 2>/dev/null || true
  fi
done

# Write MCP server .env files from direct env vars
if [ -n "${V1_API_TOKEN:-}" ] && [ -d /opt/mcp/mcp-v1-lite ]; then
  echo "V1_API_TOKEN=$V1_API_TOKEN" > /opt/mcp/mcp-v1-lite/.env
  echo "  Wrote mcp-v1-lite/.env"
fi
if [ -n "${CONFLUENCE_API_TOKEN:-}" ] && [ -d /opt/mcp/mcp-wiki-lite ]; then
  echo "CONFLUENCE_API_TOKEN=$CONFLUENCE_API_TOKEN" > /opt/mcp/mcp-wiki-lite/.env
  echo "  Wrote mcp-wiki-lite/.env"
fi
if [ -n "${JIRA_API_TOKEN:-}" ] && [ -d /opt/mcp/mcp-jira-lite ]; then
  echo "JIRA_API_TOKEN=$JIRA_API_TOKEN" > /opt/mcp/mcp-jira-lite/.env
  echo "  Wrote mcp-jira-lite/.env"
fi
if [ -n "${TRELLO_API_TOKEN:-}" ] && [ -d /opt/mcp/mcp-trello-lite ]; then
  echo "TRELLO_API_TOKEN=$TRELLO_API_TOKEN" > /opt/mcp/mcp-trello-lite/.env
  echo "  Wrote mcp-trello-lite/.env"
fi

echo ""
echo "=== Claude Portable Ready ==="
echo "  Config:    $HOME/.claude/"
echo "  Workspace: /workspace/"
echo "  MCP:       /opt/mcp/"
echo ""

exec "$@"
