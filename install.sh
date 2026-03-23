#!/bin/bash
# Install cpp globally -- adds alias to shell profile.
# Usage: bash install.sh  (or: bash <(curl -sL https://raw.githubusercontent.com/grobomo/claude-portable/main/install.sh))
set -euo pipefail

REPO="https://github.com/grobomo/claude-portable.git"
INSTALL_DIR="${CLAUDE_PORTABLE_DIR:-$HOME/claude-portable}"

echo "=== Claude Portable Installer ==="
echo ""

# Clone if not present
if [ ! -d "$INSTALL_DIR" ]; then
  echo "[1/3] Cloning repo..."
  git clone "$REPO" "$INSTALL_DIR"
else
  echo "[1/3] Repo exists at $INSTALL_DIR"
fi

# Install keyring
echo "[2/3] Installing Python dependencies..."
pip install keyring --quiet 2>/dev/null || pip3 install keyring --quiet 2>/dev/null || true

# Read alias name from config (default: cpp)
ALIAS_NAME=$(python3 -c "import json; print(json.load(open('$INSTALL_DIR/cpp.config.json')).get('alias','cpp'))" 2>/dev/null || echo "cpp")
echo "[3/3] Adding '$ALIAS_NAME' alias..."
CPP_PATH="$INSTALL_DIR/cpp"
ALIAS_LINE="alias $ALIAS_NAME='python3 \"$CPP_PATH\"'"

ADDED=false
for RC in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.bash_profile"; do
  if [ -f "$RC" ]; then
    if grep -q "alias $ALIAS_NAME=" "$RC" 2>/dev/null; then
      echo "  Already in $RC"
    else
      echo "" >> "$RC"
      echo "# Claude Portable" >> "$RC"
      echo "$ALIAS_LINE" >> "$RC"
      echo "  Added to $RC"
    fi
    ADDED=true
  fi
done

# PowerShell profile (Windows)
PS_PROFILE="${USERPROFILE:-$HOME}/Documents/PowerShell/Microsoft.PowerShell_profile.ps1"
if [ -n "${USERPROFILE:-}" ]; then
  mkdir -p "$(dirname "$PS_PROFILE")" 2>/dev/null || true
  PS_LINE="function $ALIAS_NAME { python3 \"$(cygpath -w "$CPP_PATH" 2>/dev/null || echo "$CPP_PATH")\" \$args }"
  if [ -f "$PS_PROFILE" ] && grep -q "function $ALIAS_NAME" "$PS_PROFILE" 2>/dev/null; then
    echo "  Already in PowerShell profile"
  else
    echo "" >> "$PS_PROFILE"
    echo "# Claude Portable" >> "$PS_PROFILE"
    echo "$PS_LINE" >> "$PS_PROFILE"
    echo "  Added to $PS_PROFILE"
  fi
  ADDED=true
fi

if [ "$ADDED" = false ]; then
  echo "  No shell profile found. Add manually:"
  echo "    $ALIAS_LINE"
fi

echo ""
echo "=== Installed ==="
echo "  Restart your shell or run: source ~/.bashrc"
echo "  Then: cpp"
echo ""
