# Claude Portable session setup -- sourced by .bashrc on login.
# Generates a unique session ID per SSH connection and wires up aliases.

SESSION_DIR="/data/sessions"

# Generate session ID if not already set (one per SSH connection)
if [ -z "${CLAUDE_SESSION_ID:-}" ]; then
  export CLAUDE_SESSION_ID="$(date +%Y%m%d-%H%M%S)-$(head -c4 /dev/urandom | xxd -p)"
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

# Add sessions manager to PATH
alias sessions='/opt/claude-portable/scripts/sessions.sh'

# Show session info on connect
echo ""
echo "=== Claude Portable ==="
echo "  Session:  $CLAUDE_SESSION_ID"
echo "  Logs:     $SESSION_DIR/$CLAUDE_SESSION_ID/"
echo "  Commands: claude [-p \"prompt\"] | sessions list | sessions search <pat>"
echo ""
