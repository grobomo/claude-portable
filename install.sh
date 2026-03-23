#!/bin/bash
# Claude Portable installer -- sets up everything from scratch.
# Usage: bash install.sh
# Or:    bash <(curl -sL https://raw.githubusercontent.com/grobomo/claude-portable/main/install.sh)
set -euo pipefail

REPO="https://github.com/grobomo/claude-portable.git"
INSTALL_DIR="${CLAUDE_PORTABLE_DIR:-$HOME/claude-portable}"
OS="$(uname -s)"

echo "========================================="
echo "  Claude Portable Installer"
echo "========================================="
echo ""

STEP=0
total_steps() { STEP=$((STEP + 1)); echo "[$STEP] $1"; }

# ── 1. Git ───────────────────────────────────────────────────────────────────

total_steps "Checking git..."
if ! command -v git &>/dev/null; then
  echo "  Installing git..."
  case "$OS" in
    Darwin)  xcode-select --install 2>/dev/null || true ;;
    Linux*)  sudo apt-get update -qq && sudo apt-get install -y -qq git ;;
    MINGW*|MSYS*|CYGWIN*)
      echo "  ERROR: Git not found. Install Git for Windows:"
      echo "    https://git-scm.com/download/win"
      echo "  Then re-run this installer."
      exit 1 ;;
  esac
fi
echo "  git: $(git --version)"

# ── 2. Python ────────────────────────────────────────────────────────────────

total_steps "Checking Python 3..."
PY=""
for cmd in python3 python; do
  if command -v "$cmd" &>/dev/null && "$cmd" -c "import sys; assert sys.version_info >= (3,8)" 2>/dev/null; then
    PY="$cmd"; break
  fi
done
if [ -z "$PY" ]; then
  echo "  Installing Python 3..."
  case "$OS" in
    Darwin)  brew install python3 2>/dev/null || { echo "  Install: https://www.python.org/downloads/"; exit 1; } ;;
    Linux*)  sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-pip ;;
    MINGW*|MSYS*|CYGWIN*)
      echo "  ERROR: Python 3.8+ not found. Install from:"
      echo "    https://www.python.org/downloads/"
      echo "  Check 'Add to PATH' during install. Then re-run."
      exit 1 ;;
  esac
  PY="python3"
fi
echo "  python: $($PY --version)"

# ── 3. AWS CLI ───────────────────────────────────────────────────────────────

total_steps "Checking AWS CLI..."
if ! command -v aws &>/dev/null; then
  echo "  Installing AWS CLI v2..."
  case "$OS" in
    Darwin)
      curl -sL "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o /tmp/AWSCLIV2.pkg
      sudo installer -pkg /tmp/AWSCLIV2.pkg -target /
      rm /tmp/AWSCLIV2.pkg
      ;;
    Linux*)
      curl -sL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscli.zip
      unzip -q /tmp/awscli.zip -d /tmp
      sudo /tmp/aws/install
      rm -rf /tmp/aws /tmp/awscli.zip
      ;;
    MINGW*|MSYS*|CYGWIN*)
      echo "  Downloading AWS CLI installer..."
      curl -sL "https://awscli.amazonaws.com/AWSCLIV2.msi" -o /tmp/AWSCLIV2.msi
      echo "  Running installer (this opens a Windows dialog)..."
      cmd.exe /c "msiexec /i $(cygpath -w /tmp/AWSCLIV2.msi) /qn" 2>/dev/null || \
        start "" "$(cygpath -w /tmp/AWSCLIV2.msi)" 2>/dev/null || \
        { echo "  Run manually: $(cygpath -w /tmp/AWSCLIV2.msi)"; }
      echo "  Waiting for install to complete..."
      sleep 10
      # Refresh PATH
      export PATH="$PATH:/c/Program Files/Amazon/AWSCLIV2"
      ;;
  esac
fi

if ! command -v aws &>/dev/null; then
  echo "  ERROR: AWS CLI still not found after install."
  echo "  Install manually: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
  echo "  Then re-run this installer."
  exit 1
fi
echo "  aws: $(aws --version 2>&1 | head -1)"

# ── 4. AWS credentials ──────────────────────────────────────────────────────

total_steps "Checking AWS credentials..."
if ! aws sts get-caller-identity &>/dev/null; then
  echo ""
  echo "  AWS CLI is not configured. Let's set it up."
  echo ""
  echo "  You need an AWS Access Key. To create one:"
  echo "    1. Go to https://console.aws.amazon.com/iam/"
  echo "    2. Users > your user > Security credentials tab"
  echo "    3. Create access key > Command Line Interface"
  echo "    4. Copy the Access Key ID and Secret Access Key"
  echo ""
  echo "  Or see: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-quickstart.html"
  echo ""

  # Try to run aws configure interactively
  read -p "  Do you have your Access Key ID ready? (y/n) " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    read -p "  AWS Access Key ID: " AWS_AK
    read -sp "  AWS Secret Access Key: " AWS_SK
    echo
    read -p "  Default region [us-east-2]: " AWS_RG
    AWS_RG="${AWS_RG:-us-east-2}"

    mkdir -p "$HOME/.aws"
    cat > "$HOME/.aws/credentials" << CREDEOF
[default]
aws_access_key_id = $AWS_AK
aws_secret_access_key = $AWS_SK
CREDEOF
    chmod 600 "$HOME/.aws/credentials"

    cat > "$HOME/.aws/config" << CONFEOF
[default]
region = $AWS_RG
output = json
CONFEOF

    if aws sts get-caller-identity &>/dev/null; then
      ACCT=$(aws sts get-caller-identity --query Account --output text)
      echo "  Authenticated. Account: $ACCT"
    else
      echo "  ERROR: Credentials invalid. Check your keys and try again."
      exit 1
    fi
  else
    echo ""
    echo "  Run 'aws configure' when you're ready, then re-run this installer."
    exit 1
  fi
else
  ACCT=$(aws sts get-caller-identity --query Account --output text)
  echo "  Authenticated. Account: $ACCT"
fi

# ── 5. Clone repo ───────────────────────────────────────────────────────────

total_steps "Setting up claude-portable..."
if [ ! -d "$INSTALL_DIR" ]; then
  git clone "$REPO" "$INSTALL_DIR"
  echo "  Cloned to $INSTALL_DIR"
else
  echo "  Already exists at $INSTALL_DIR"
  cd "$INSTALL_DIR" && git pull --quiet 2>/dev/null || true
fi

# ── 6. Python deps ──────────────────────────────────────────────────────────

total_steps "Installing Python dependencies..."
$PY -m pip install keyring --quiet 2>/dev/null || true
echo "  Done."

# ── 7. Shell alias ──────────────────────────────────────────────────────────

ALIAS_NAME=$($PY -c "
import json, os
d = os.path.join(os.path.expanduser('~'), 'claude-portable', 'cpp.config.json')
print(json.load(open(d)).get('alias', 'cpp'))
" 2>/dev/null || echo "cpp")
total_steps "Adding '$ALIAS_NAME' to shell..."
CPP_PATH="$INSTALL_DIR/cpp"
ALIAS_LINE="alias $ALIAS_NAME='$PY \"$CPP_PATH\"'"

ADDED=false
for RC in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.bash_profile"; do
  if [ -f "$RC" ]; then
    # Remove any old Claude Portable alias (handles renames like cpp -> ccp)
    sed -i '/# Claude Portable/d; /alias.*=.*python3.*claude-portable.*cpp/d' "$RC" 2>/dev/null || true
    if grep -q "alias $ALIAS_NAME=" "$RC" 2>/dev/null; then
      echo "  Already in $(basename $RC)"
    else
      printf '\n# Claude Portable\n%s\n' "$ALIAS_LINE" >> "$RC"
      echo "  Added to $(basename $RC)"
    fi
    ADDED=true
  fi
done

# PowerShell profile (Windows)
if [ -n "${USERPROFILE:-}" ]; then
  PS_PROFILE="${USERPROFILE}/Documents/PowerShell/Microsoft.PowerShell_profile.ps1"
  mkdir -p "$(dirname "$PS_PROFILE")" 2>/dev/null || true
  WIN_PATH="$(cygpath -w "$CPP_PATH" 2>/dev/null || echo "$CPP_PATH")"
  PS_LINE="function $ALIAS_NAME { python3 \"$WIN_PATH\" \$args }"
  # Remove old Claude Portable function (handles renames)
  sed -i '/# Claude Portable/d; /function.*python3.*claude-portable.*cpp/d' "$PS_PROFILE" 2>/dev/null || true
  if grep -q "function $ALIAS_NAME" "$PS_PROFILE" 2>/dev/null; then
    echo "  Already in PowerShell profile"
  else
    printf '\n# Claude Portable\n%s\n' "$PS_LINE" >> "$PS_PROFILE"
    echo "  Added to PowerShell profile"
  fi
  ADDED=true
fi

if [ "$ADDED" = false ]; then
  echo "  No shell profile found. Add manually:"
  echo "    $ALIAS_LINE"
fi

# ── Done ─────────────────────────────────────────────────────────────────────

echo ""
echo "========================================="
echo "  Installed!"
echo "========================================="
echo ""
echo "  Restart your shell (or: source ~/.bashrc)"
echo "  Then run: $ALIAS_NAME"
echo ""
echo "  First launch takes ~5-7 min (builds container on EC2)."
echo "  After that, stopped instances resume in ~30 sec."
echo ""
