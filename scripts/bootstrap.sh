#!/bin/bash
set -euo pipefail

echo "=== Claude Portable Bootstrap ==="

# --- Step 1: Inject secrets (BWS or direct env vars) ---
echo "[1/7] Injecting secrets..."
/opt/claude-portable/scripts/inject-secrets.sh

# --- Step 2: Verify Claude auth + skip onboarding ---
echo "[2/7] Verifying Claude authentication..."
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
  echo "  Onboarding marked complete (settings.local.json)."
fi

# Write .claude.json to $HOME/ (NOT $HOME/.claude/) -- Claude Code expects it at ~/
# Without this file at ~/, interactive mode shows the login wizard even with valid OAuth creds.
if [ ! -f "$HOME/.claude.json" ]; then
  cat > "$HOME/.claude.json" << 'CLAUDE_JSON_EOF'
{
  "numStartups": 1,
  "hasCompletedOnboarding": true,
  "autoUpdates": false,
  "hasSeenTasksHint": true,
  "installMethod": "container"
}
CLAUDE_JSON_EOF
  echo "  Wrote $HOME/.claude.json (onboarding bypass)."
fi

# --- Step 3: Authenticate gh CLI and configure git identity ---
echo "[3/7] Setting up gh CLI and git identity..."
if [ -n "${GITHUB_TOKEN:-}" ]; then
  echo "$GITHUB_TOKEN" | gh auth login --with-token 2>/dev/null && \
    echo "  gh CLI authenticated via GITHUB_TOKEN."
  gh auth setup-git 2>/dev/null && \
    echo "  gh auth setup-git complete."
else
  echo "  No GITHUB_TOKEN set. gh CLI not authenticated."
fi

# Set git identity for container commits (safe generic identity)
git config --global user.name "claude-portable"
git config --global user.email "noreply@claude-portable"
echo "  Git identity: claude-portable <noreply@claude-portable>"

# --- Step 4: Pull config from repos ---
echo "[4/7] Syncing config from repos..."
/opt/claude-portable/scripts/sync-config.sh || echo "  WARNING: Config sync had errors (non-fatal)."

# Fix .claude.json location: Claude Code needs it at ~/ but hooks expect it at ~/.claude/ too.
# Canonical location: $HOME/.claude.json. Symlink at $HOME/.claude/.claude.json.
if [ -f "$HOME/.claude/.claude.json" ] && [ ! -L "$HOME/.claude/.claude.json" ]; then
  # sync-config copied it into ~/.claude/ -- move to ~/ and symlink back
  if [ ! -f "$HOME/.claude.json" ]; then
    mv "$HOME/.claude/.claude.json" "$HOME/.claude.json"
  else
    rm "$HOME/.claude/.claude.json"
  fi
fi
if [ -f "$HOME/.claude.json" ] && [ ! -L "$HOME/.claude/.claude.json" ]; then
  ln -sf "$HOME/.claude.json" "$HOME/.claude/.claude.json"
  echo "  Symlinked ~/.claude/.claude.json -> ~/.claude.json"
fi

# --- Step 5: Rewrite paths for container ---
echo "[5/7] Rewriting paths for container..."
/opt/claude-portable/scripts/rewrite-paths.sh

# --- Step 6: SSH server for file sync ---
echo "[6/7] Starting SSH server..."
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

# --- Step 7: Install MCP dependencies + inject tokens ---
echo "[7/7] Installing MCP server dependencies..."
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

# Copy container-native servers.yaml to mcp-manager
if [ -d /opt/mcp/mcp-manager ] && [ -f /opt/claude-portable/config/servers.yaml ]; then
  cp /opt/claude-portable/config/servers.yaml /opt/mcp/mcp-manager/servers.yaml
  echo "  Copied servers.yaml to mcp-manager."
fi

# Write .mcp.json pointing to mcp-manager (must happen after MCP deps install)
if [ -d /opt/mcp/mcp-manager ]; then
  cat > "$HOME/.mcp.json" << 'MCP_JSON_EOF'
{
  "mcpServers": {
    "mcp-manager": {
      "command": "node",
      "args": ["/opt/mcp/mcp-manager/build/index.js"]
    }
  }
}
MCP_JSON_EOF
  echo "  Wrote $HOME/.mcp.json (mcp-manager entry point)."
fi

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

# --- Start browser session (Xvfb + VNC + Chrome) ---
if command -v Xvfb >/dev/null 2>&1; then
  export DISPLAY=:99
  echo "export DISPLAY=:99" >> "$HOME/.bashrc"
  /opt/claude-portable/scripts/browser.sh start 2>/dev/null || {
    # Fallback: just start Xvfb for headless use
    Xvfb :99 -screen 0 1920x1080x24 &>/dev/null &
    echo "  Xvfb running on :99 (headless mode)."
  }
fi

# --- Ensure session dirs exist on persistent volume ---
mkdir -p /data/sessions /data/exports
echo "  Session logs: /data/sessions/"

# --- Start web-chat server (mobile phone access) ---
if [ -f /opt/claude-portable/scripts/web-chat.js ]; then
  echo "[+] Starting web-chat server on port ${CLAUDE_WEB_PORT:-8888}..."
  export NODE_PATH=/opt/claude-portable/node_modules
  nohup node /opt/claude-portable/scripts/web-chat.js \
    >> /data/web-chat.log 2>&1 &
  echo "  web-chat PID: $!"
  # Wait briefly and show the access token
  sleep 1
  if [ -f /data/web-chat-token ]; then
    echo "  web-chat token: $(cat /data/web-chat-token)"
  fi
fi

# --- Pull conversation state from S3 (if bucket exists) ---
if command -v aws >/dev/null 2>&1 && aws sts get-caller-identity &>/dev/null; then
  if [ -x /usr/local/bin/state-sync ] || [ -x /opt/claude-portable/scripts/state-sync.sh ]; then
    SYNC_CMD="${CLAUDE_DIR:+CLAUDE_CONFIG_DIR=$CLAUDE_DIR} "
    SYNC_CMD="CLAUDE_PORTABLE_ID=${CLAUDE_PORTABLE_ID:-$(hostname)}"
    echo "[+] Pulling conversation state from S3..."
    /opt/claude-portable/scripts/state-sync.sh pull 2>/dev/null || \
      /usr/local/bin/state-sync pull 2>/dev/null || \
      echo "  No state bucket found (run state-sync setup first)."
    # Start auto-sync in background
    echo "[+] Starting auto-sync (every 60s)..."
    nohup /opt/claude-portable/scripts/state-sync.sh auto 60 &>/dev/null &
    echo "  Auto-sync PID: $!"

    # Start credential refresh daemon
    echo "[+] Starting credential refresh daemon (every 15min)..."
    nohup /opt/claude-portable/scripts/cred-refresh.sh 15 &>/dev/null &
    echo "  Cred-refresh PID: $!"
  fi
fi

# --- Start idle monitor (auto-shutdown on inactivity) ---
if [ "${CLAUDE_PORTABLE_MODE:-}" = "remote" ]; then
  IDLE_TIMEOUT="${CLAUDE_PORTABLE_IDLE_TIMEOUT:-30}"
  echo "[+] Starting idle monitor (${IDLE_TIMEOUT}min timeout)..."
  nohup /opt/claude-portable/scripts/idle-monitor.sh "$IDLE_TIMEOUT" \
    >> /data/idle-monitor.log 2>&1 &
  echo "  Idle monitor PID: $!"
fi

# --- Start continuous-claude runner (autonomous task loop) ---
if [ "${CONTINUOUS_CLAUDE_ENABLED:-false}" = "true" ] && [ -n "${CONTINUOUS_CLAUDE_REPO:-}" ]; then
  CC_BRANCH="${CONTINUOUS_CLAUDE_BRANCH:-main}"
  CC_WORKDIR="/workspace/continuous-claude"
  CC_SCRIPT="/opt/claude-portable/scripts/continuous-claude.sh"

  if [ -x "$CC_SCRIPT" ]; then
    echo "[+] Starting continuous-claude runner..."
    echo "  Repo:   $CONTINUOUS_CLAUDE_REPO"
    echo "  Branch: $CC_BRANCH"
    echo "  Log:    /data/continuous-claude.log"
    nohup "$CC_SCRIPT" "$CONTINUOUS_CLAUDE_REPO" "$CC_BRANCH" "$CC_WORKDIR" \
      >> /data/continuous-claude.log 2>&1 &
    echo "  continuous-claude PID: $!"
  else
    echo "  WARNING: continuous-claude.sh not found or not executable at $CC_SCRIPT"
  fi
fi

# --- Trap EXIT to push state before container stops ---
cleanup() {
  echo "[!] Container stopping -- pushing final state to S3..."
  /opt/claude-portable/scripts/state-sync.sh push 2>/dev/null || true
  echo "  Final sync done."
}
if command -v aws >/dev/null 2>&1 && aws sts get-caller-identity &>/dev/null; then
  trap cleanup EXIT TERM INT
fi

echo ""
echo "=== Claude Portable Ready ==="
echo "  Config:    $HOME/.claude/"
echo "  Workspace: /workspace/"
echo "  MCP:       /opt/mcp/"
echo "  Sessions:  /data/sessions/"
if [ "${CLAUDE_PORTABLE_MODE:-}" = "remote" ]; then
  echo "  Idle:      ${CLAUDE_PORTABLE_IDLE_TIMEOUT:-30}min auto-shutdown"
  echo "  S3 sync:   every 60s (session logs + conversation state)"
fi
echo "  Use 'sessions list' to view past conversations."
echo ""

exec "$@"
