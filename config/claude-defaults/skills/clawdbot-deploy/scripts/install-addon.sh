#!/bin/bash
# =============================================================================
# Clawdbot Addon Installer
# =============================================================================
# Usage: ./install-addon.sh <addon-name>
#
# Installs a Clawdbot addon on a running EC2 instance.
# Downloads and executes the addon's install script from S3.
# =============================================================================

set -e

ADDON_NAME="${1:-}"

if [ -z "$ADDON_NAME" ]; then
    echo "Usage: $0 <addon-name>"
    echo ""
    echo "Available addons:"
    echo "  signal  - Signal messaging integration"
    echo "  teams   - Microsoft Teams integration (not yet implemented)"
    exit 1
fi

# Get bucket from SSM
STATE_BUCKET=$(aws ssm get-parameter --name /clawdbot/config --query 'Parameter.Value' --output text | jq -r '.bucket')

if [ -z "$STATE_BUCKET" ]; then
    echo "ERROR: Could not determine STATE_BUCKET from SSM"
    exit 1
fi

echo "========================================"
echo "Installing Addon: $ADDON_NAME"
echo "========================================"

# Check if addon exists
if ! aws s3 ls "s3://${STATE_BUCKET}/addons/${ADDON_NAME}/manifest.json" &>/dev/null; then
    echo "ERROR: Addon '$ADDON_NAME' not found in S3"
    echo "Make sure you've deployed the addon CloudFormation stack first."
    exit 1
fi

# Download and show manifest
echo ">>> Addon manifest:"
aws s3 cp "s3://${STATE_BUCKET}/addons/${ADDON_NAME}/manifest.json" - | jq .

# Download install script
INSTALL_SCRIPT="/tmp/${ADDON_NAME}-install.sh"
echo ">>> Downloading install script..."
aws s3 cp "s3://${STATE_BUCKET}/addons/${ADDON_NAME}/install.sh" "$INSTALL_SCRIPT"
chmod +x "$INSTALL_SCRIPT"

# Run install script
echo ">>> Running install script..."
STATE_BUCKET="$STATE_BUCKET" bash "$INSTALL_SCRIPT"

# Cleanup
rm -f "$INSTALL_SCRIPT"

echo "========================================"
echo "Addon '$ADDON_NAME' Installed"
echo "========================================"
