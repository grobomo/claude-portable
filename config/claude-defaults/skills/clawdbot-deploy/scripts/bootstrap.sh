#!/bin/bash
# =============================================================================
# Clawdbot EC2 Bootstrap Script
# =============================================================================
# This script is embedded in EC2 userdata by the orchestrator Lambda.
# It runs on every instance launch to:
# 1. Install Node.js and Clawdbot
# 2. Sync config from S3
# 3. Install any enabled addons
# 4. Start Clawdbot gateway service
#
# Logs: /var/log/clawdbot-bootstrap.log
# =============================================================================

set -ex

# Log everything
exec > >(tee /var/log/clawdbot-bootstrap.log) 2>&1

echo "========================================"
echo "Clawdbot Bootstrap Starting"
echo "$(date)"
echo "========================================"

# -----------------------------------------------------------------------------
# Configuration (passed via environment or defaults)
# -----------------------------------------------------------------------------
STATE_BUCKET="${STATE_BUCKET:-}"
STACK_NAME="${STACK_NAME:-clawdbot}"

if [ -z "$STATE_BUCKET" ]; then
    echo "ERROR: STATE_BUCKET not set"
    exit 1
fi

# -----------------------------------------------------------------------------
# Install System Dependencies
# -----------------------------------------------------------------------------
echo ">>> Installing system packages..."
dnf update -y --quiet
dnf install -y nodejs git jq awscli

# Verify Node.js version (need 18+)
NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo ">>> Node.js too old, installing v22..."
    curl -fsSL https://rpm.nodesource.com/setup_22.x | bash -
    dnf install -y nodejs
fi

# -----------------------------------------------------------------------------
# Create Clawdbot User
# -----------------------------------------------------------------------------
echo ">>> Creating clawdbot user..."
id clawdbot &>/dev/null || useradd -m -s /bin/bash clawdbot

# -----------------------------------------------------------------------------
# Install Clawdbot
# -----------------------------------------------------------------------------
echo ">>> Installing Clawdbot..."
npm install -g clawdbot@latest

# Create directories
mkdir -p /home/clawdbot/.clawdbot
mkdir -p /home/clawdbot/.local/share

# -----------------------------------------------------------------------------
# Sync Config from S3
# -----------------------------------------------------------------------------
echo ">>> Syncing config from S3..."
aws s3 sync "s3://${STATE_BUCKET}/config/" /home/clawdbot/.clawdbot/ --quiet || true

# Ensure proper ownership
chown -R clawdbot:clawdbot /home/clawdbot

# -----------------------------------------------------------------------------
# Install Addons
# -----------------------------------------------------------------------------
echo ">>> Checking for addons..."

# List addon manifests in S3
ADDONS=$(aws s3 ls "s3://${STATE_BUCKET}/addons/" --recursive | grep 'manifest.json' | awk '{print $4}' | xargs -I{} dirname {} | xargs -I{} basename {})

for addon in $ADDONS; do
    echo ">>> Installing addon: $addon"

    # Download install script
    aws s3 cp "s3://${STATE_BUCKET}/addons/${addon}/install.sh" "/tmp/${addon}-install.sh" --quiet
    chmod +x "/tmp/${addon}-install.sh"

    # Run install script
    STATE_BUCKET="$STATE_BUCKET" bash "/tmp/${addon}-install.sh"

    echo ">>> Addon $addon installed"
done

# -----------------------------------------------------------------------------
# Create Systemd Service
# -----------------------------------------------------------------------------
echo ">>> Creating systemd service..."
cat > /etc/systemd/system/clawdbot.service << EOFSERVICE
[Unit]
Description=Clawdbot Gateway
After=network.target

[Service]
Type=simple
User=clawdbot
WorkingDirectory=/home/clawdbot
ExecStart=/usr/bin/clawdbot gateway start
ExecStopPost=/bin/bash -c 'aws s3 sync /home/clawdbot/.clawdbot/ s3://${STATE_BUCKET}/config/ --quiet'
Restart=always
RestartSec=10
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
EOFSERVICE

# -----------------------------------------------------------------------------
# Create S3 Sync Cron
# -----------------------------------------------------------------------------
echo ">>> Setting up S3 sync cron..."
cat > /etc/cron.d/clawdbot-sync << EOFCRON
# Sync Clawdbot state to S3 every 5 minutes
*/5 * * * * clawdbot aws s3 sync /home/clawdbot/.clawdbot/ s3://${STATE_BUCKET}/config/ --quiet 2>/dev/null
EOFCRON

# -----------------------------------------------------------------------------
# Spot Interruption Handler
# -----------------------------------------------------------------------------
echo ">>> Setting up Spot interruption handler..."
cat > /usr/local/bin/clawdbot-shutdown.sh << 'EOFSHUTDOWN'
#!/bin/bash
echo "$(date) - Graceful shutdown initiated"
echo "Syncing state to S3..."
sudo -u clawdbot aws s3 sync /home/clawdbot/.clawdbot/ s3://${STATE_BUCKET}/config/ --quiet
sudo -u clawdbot aws s3 sync /home/clawdbot/.local/share/ s3://${STATE_BUCKET}/local-share/ --quiet
systemctl stop clawdbot
echo "$(date) - Shutdown complete"
EOFSHUTDOWN
chmod +x /usr/local/bin/clawdbot-shutdown.sh

cat > /etc/systemd/system/spot-interruption-handler.service << 'EOFSPOT'
[Unit]
Description=EC2 Spot Interruption Handler
After=network.target

[Service]
Type=simple
ExecStart=/bin/bash -c 'while true; do if curl -s -f -m 2 http://169.254.169.254/latest/meta-data/spot/instance-action > /dev/null 2>&1; then /usr/local/bin/clawdbot-shutdown.sh; sleep 120; fi; sleep 5; done'
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOFSPOT

# -----------------------------------------------------------------------------
# Start Services
# -----------------------------------------------------------------------------
echo ">>> Starting services..."
systemctl daemon-reload
systemctl enable clawdbot spot-interruption-handler
systemctl start spot-interruption-handler
systemctl start clawdbot

# -----------------------------------------------------------------------------
# Health Check
# -----------------------------------------------------------------------------
echo ">>> Waiting for Clawdbot to start..."
sleep 10

if systemctl is-active --quiet clawdbot; then
    echo ">>> Clawdbot is running"
else
    echo ">>> WARNING: Clawdbot may not have started correctly"
    journalctl -u clawdbot --no-pager -n 50
fi

echo "========================================"
echo "Clawdbot Bootstrap Complete"
echo "$(date)"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. SSH to this instance"
echo "2. Run: sudo -u clawdbot clawdbot models auth paste-token --provider anthropic"
echo "3. Paste your Claude setup token"
echo ""
