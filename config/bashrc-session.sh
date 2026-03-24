# Claude Portable session setup -- sourced by .bashrc on login.
# Generates a unique session ID per SSH connection and wires up aliases.

SESSION_DIR="/data/sessions"

# Generate session ID if not already set (one per SSH connection)
if [ -z "${CLAUDE_SESSION_ID:-}" ]; then
  export CLAUDE_SESSION_ID="$(date +%Y%m%d-%H%M%S)-$(head -c4 /dev/urandom | od -An -tx1 | tr -d ' \n')"
fi

export SESSION_DIR

# Create session dir and initial metadata
mkdir -p "$SESSION_DIR/$CLAUDE_SESSION_ID"
if [ ! -f "$SESSION_DIR/$CLAUDE_SESSION_ID/meta.json" ]; then
  cat > "$SESSION_DIR/$CLAUDE_SESSION_ID/meta.json" << METAEOF
{
  "id": "$CLAUDE_SESSION_ID",
  "started": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "hostname": "$(hostname)",
  "ssh_client": "${SSH_CLIENT:-local}",
  "user": "$(whoami)",
  "invocations": 0
}
METAEOF
fi

# Alias claude to the session wrapper
alias claude='/opt/claude-portable/scripts/claude-session.sh'

# Add sessions manager, state-sync, and browser to PATH
alias sessions='/opt/claude-portable/scripts/sessions.sh'
alias state-sync='/opt/claude-portable/scripts/state-sync.sh'
alias browser='/opt/claude-portable/scripts/browser.sh'

# Push state to S3 on disconnect
trap 'state-sync push &>/dev/null || true' EXIT

# Show session info on connect
echo ""
echo "=== Claude Portable ==="
echo "  Session:  $CLAUDE_SESSION_ID"
echo "  Instance: ${CLAUDE_PORTABLE_ID:-$(hostname)}"
echo "  Logs:     $SESSION_DIR/$CLAUDE_SESSION_ID/"
echo ""

# Ensure claude is in PATH (npm global bin)
export PATH="$PATH:/usr/local/share/npm-global/bin"

# Auto-launch Claude on SSH login (interactive shells only)
if [[ $- == *i* ]] && [ -z "${CLAUDE_AUTOSTART_DONE:-}" ]; then
  export CLAUDE_AUTOSTART_DONE=1
  /opt/claude-portable/scripts/claude-session.sh
fi
