#!/bin/bash
# =============================================================================
# Clawdbot Hook Setup Script
# =============================================================================
# Configures Claude Code to connect to a remote Clawdbot gateway.
#
# Usage: ./setup-hook.sh <gateway-url> [token]
#
# Example:
#   ./setup-hook.sh ws://18.221.133.29:18789
#   ./setup-hook.sh wss://clawdbot.example.com my-secret-token
# =============================================================================

set -e

GATEWAY_URL="${1:-}"
GATEWAY_TOKEN="${2:-}"

if [ -z "$GATEWAY_URL" ]; then
    echo "Usage: $0 <gateway-url> [token]"
    echo ""
    echo "Example:"
    echo "  $0 ws://18.221.133.29:18789"
    echo "  $0 wss://clawdbot.example.com my-secret-token"
    exit 1
fi

# Determine script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_SCRIPT="${SCRIPT_DIR}/../hooks/clawdbot-gateway-hook.py"

# Ensure hook script exists
if [ ! -f "$HOOK_SCRIPT" ]; then
    echo "ERROR: Hook script not found: $HOOK_SCRIPT"
    exit 1
fi

# Make hook executable
chmod +x "$HOOK_SCRIPT"

# Create/update environment file for hook
ENV_FILE="$HOME/.clawdbot-env"
cat > "$ENV_FILE" << EOF
export CLAWDBOT_GATEWAY_URL="${GATEWAY_URL}"
export CLAWDBOT_GATEWAY_TOKEN="${GATEWAY_TOKEN}"
EOF

echo "Created environment file: $ENV_FILE"

# Detect Claude settings file location
if [ -f "$HOME/.claude/settings.json" ]; then
    SETTINGS_FILE="$HOME/.claude/settings.json"
elif [ -f "$HOME/.config/claude/settings.json" ]; then
    SETTINGS_FILE="$HOME/.config/claude/settings.json"
else
    SETTINGS_FILE="$HOME/.claude/settings.json"
    mkdir -p "$(dirname "$SETTINGS_FILE")"
    echo '{}' > "$SETTINGS_FILE"
fi

echo "Settings file: $SETTINGS_FILE"

# Create wrapper script that sources env before running hook
WRAPPER_SCRIPT="$HOME/.claude/hooks/clawdbot-hook-wrapper.sh"
mkdir -p "$(dirname "$WRAPPER_SCRIPT")"

cat > "$WRAPPER_SCRIPT" << EOF
#!/bin/bash
source "$ENV_FILE"
python3 "$HOOK_SCRIPT"
EOF
chmod +x "$WRAPPER_SCRIPT"

echo "Created wrapper: $WRAPPER_SCRIPT"

# Check if jq is available for JSON manipulation
if command -v jq &> /dev/null; then
    # Use jq to add hook to settings
    HOOK_CONFIG=$(cat << EOFHOOK
{
  "matcher": "*",
  "hooks": [
    {
      "type": "command",
      "command": "$WRAPPER_SCRIPT"
    }
  ]
}
EOFHOOK
)

    # Add hook to UserPromptSubmit array
    UPDATED=$(jq --argjson hook "$HOOK_CONFIG" '
        .hooks.UserPromptSubmit = ((.hooks.UserPromptSubmit // []) + [$hook] | unique_by(.hooks[0].command))
    ' "$SETTINGS_FILE")

    echo "$UPDATED" > "$SETTINGS_FILE"
    echo "Updated Claude settings with Clawdbot hook"
else
    echo ""
    echo "WARNING: jq not found. Please manually add this to $SETTINGS_FILE:"
    echo ""
    cat << EOFMANUAL
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "$WRAPPER_SCRIPT"
          }
        ]
      }
    ]
  }
}
EOFMANUAL
fi

echo ""
echo "========================================"
echo "Clawdbot Hook Setup Complete"
echo "========================================"
echo ""
echo "Gateway URL: $GATEWAY_URL"
echo "Token: ${GATEWAY_TOKEN:-(none)}"
echo ""
echo "The hook will inject Clawdbot context when you mention:"
echo "  clawdbot, gateway, remote claude, bot, signal, message"
echo ""
echo "Restart Claude Code to apply changes."
echo ""
