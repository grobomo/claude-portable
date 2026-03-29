#!/bin/bash
# Install the jumpbox command on PATH
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"

# Find writable bin dir on PATH
BIN_DIR=""
for D in "$HOME/.local/bin" "$HOME/bin"; do
  case ":$PATH:" in
    *":$D:"*)
      mkdir -p "$D" 2>/dev/null && BIN_DIR="$D" && break ;;
  esac
done
if [ -z "$BIN_DIR" ]; then
  BIN_DIR="$HOME/.local/bin"
  mkdir -p "$BIN_DIR"
fi

cp "$SKILL_DIR/jumpbox.sh" "$BIN_DIR/jumpbox"
chmod +x "$BIN_DIR/jumpbox"
echo "Installed: $BIN_DIR/jumpbox"

# Ensure pywinauto is available (for auto-dismissing RDP warnings on Windows)
if python3 -c "import pywinauto" 2>/dev/null; then
  echo "pywinauto: OK"
else
  echo "Installing pywinauto (for RDP auto-connect)..."
  python3 -m pip install pywinauto --quiet 2>/dev/null || echo "  Optional: pip install pywinauto"
fi

# Migrate existing hardcoded jumpbox config
CONFIG_DIR="$HOME/.jumpbox"
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/jumpbox.json" ]; then
  echo ""
  echo "No jumpbox configured yet. To create one:"
  echo "  jumpbox setup"
  echo ""
  echo "Or ask Claude: 'set up a windows jumpbox'"
fi
