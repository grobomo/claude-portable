#!/bin/bash
# Build a golden AMI with Docker, the container image, and all tools pre-installed.
# Cuts instance launch from ~7min to ~1-2min.
#
# Usage: ./scripts/build-ami.sh [--instance-type TYPE] [--region REGION]
#
# What it does:
#   1. Launch a temp EC2 instance
#   2. Install Docker + build the claude-portable container image
#   3. Install Playwright browsers in the container
#   4. Pre-pull all dependencies
#   5. Create AMI from the instance
#   6. Terminate the temp instance
#   7. Print the AMI ID
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REGION="${1:-us-east-2}"
INSTANCE_TYPE="t3.large"
KEY_NAME="claude-portable-key"
AMI_NAME="claude-portable-golden-$(date +%Y%m%d-%H%M)"

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --region) REGION="$2"; shift 2 ;;
    --instance-type) INSTANCE_TYPE="$2"; shift 2 ;;
    *) shift ;;
  esac
done

echo "========================================="
echo "  Building Golden AMI"
echo "========================================="
echo "  Region: $REGION"
echo "  Instance: $INSTANCE_TYPE"
echo "  AMI name: $AMI_NAME"
echo ""

# Load .env for repo URL and GitHub token
[ -f "$SCRIPT_DIR/.env" ] && set -a && source "$SCRIPT_DIR/.env" && set +a
REPO_URL="${REPO_URL:-https://github.com/grobomo/claude-portable.git}"
GH_TOKEN="${GITHUB_TOKEN:-}"

# Get latest Ubuntu 24.04 AMI
BASE_AMI=$(aws ec2 describe-images --owners amazon \
  --filters "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*" \
  --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
  --output text --region "$REGION")
echo "  Base AMI: $BASE_AMI"

# Find security group
SG_ID=$(aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=ccc-sg" \
  --query 'SecurityGroups[0].GroupId' --output text --region "$REGION" 2>/dev/null || echo "")

if [ -z "$SG_ID" ] || [ "$SG_ID" = "None" ]; then
  # Use any SG with SSH access
  SG_ID=$(aws ec2 describe-security-groups \
    --filters "Name=ip-permission.from-port,Values=22" \
    --query 'SecurityGroups[0].GroupId' --output text --region "$REGION" 2>/dev/null || echo "")
fi

if [ -z "$SG_ID" ] || [ "$SG_ID" = "None" ]; then
  echo "ERROR: No security group with SSH access found. Run 'ccc' first to create one."
  exit 1
fi

# Launch temp instance
echo ""
echo "[1/6] Launching temp instance..."
INSTANCE_ID=$(aws ec2 run-instances \
  --image-id "$BASE_AMI" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":50,"VolumeType":"gp3"}}]' \
  --tag-specifications "[{\"ResourceType\":\"instance\",\"Tags\":[{\"Key\":\"Name\",\"Value\":\"ami-builder-temp\"},{\"Key\":\"Project\",\"Value\":\"claude-portable\"}]}]" \
  --query 'Instances[0].InstanceId' --output text --region "$REGION")
echo "  Instance: $INSTANCE_ID"

echo "  Waiting for running..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"

IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text --region "$REGION")
echo "  IP: $IP"

# Find SSH key
SSH_KEY=""
for candidate in "$HOME/.ssh/${KEY_NAME}.pem" "$HOME/archive/.ssh/claude-portable.pem" "$HOME/archive/.ssh/${KEY_NAME}.pem"; do
  if [ -f "$candidate" ]; then SSH_KEY="$candidate"; break; fi
done

if [ -z "$SSH_KEY" ]; then
  echo "ERROR: SSH key not found."
  exit 1
fi

# Wait for SSH
echo "  Waiting for SSH..."
for i in $(seq 1 30); do
  ssh -o StrictHostKeyChecking=no -o ConnectTimeout=3 -o LogLevel=ERROR \
    -i "$SSH_KEY" ubuntu@$IP "echo ok" 2>/dev/null && break
  sleep 5
done

# Build everything on the instance
echo ""
echo "[2/6] Installing Docker..."
ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR -i "$SSH_KEY" ubuntu@$IP << 'DOCKER_INSTALL'
set -ex
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl git
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update -y
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker ubuntu
DOCKER_INSTALL

echo ""
echo "[3/6] Cloning repo and building container..."

# Set up git credentials for private repos
if [ -n "$GH_TOKEN" ]; then
  ssh -i "$SSH_KEY" ubuntu@$IP "git config --global credential.helper store && printf 'https://x-access-token:${GH_TOKEN}@github.com\n' > ~/.git-credentials"
fi

ssh -i "$SSH_KEY" ubuntu@$IP << CLONE_BUILD
set -ex
cd /opt
sudo git clone ${REPO_URL} claude-portable
cd claude-portable
sudo docker compose -f docker-compose.yml -f docker-compose.remote.yml build
CLONE_BUILD

echo ""
echo "[4/6] Installing Playwright browsers and Python deps in container..."
ssh -i "$SSH_KEY" ubuntu@$IP << 'INSTALL_EXTRAS'
set -ex
cd /opt/claude-portable

# Start container briefly to install extras
sudo docker compose -f docker-compose.yml -f docker-compose.remote.yml up -d
sleep 5

# Install Playwright + browsers
sudo docker exec claude-portable bash -c '
  pip install --break-system-packages playwright requests beautifulsoup4 lxml httpx aiohttp
  playwright install --with-deps chromium
'

# Install additional Node.js tools
sudo docker exec claude-portable bash -c '
  npm install -g typescript ts-node prettier eslint
'

# Warm up npm cache with common packages
sudo docker exec claude-portable bash -c '
  cd /tmp && npm init -y && npm install puppeteer cheerio axios node-fetch 2>/dev/null || true
  rm -rf /tmp/package* /tmp/node_modules
'

# Stop container (will be started fresh on real launch)
sudo docker compose -f docker-compose.yml -f docker-compose.remote.yml down

# Commit the container state so extras persist across docker compose up
CONTAINER_ID=$(sudo docker ps -a --filter name=claude-portable --format "{{.ID}}" | head -1)
if [ -n "$CONTAINER_ID" ]; then
  sudo docker commit "$CONTAINER_ID" claude-portable:latest
  echo "Container committed with all extras."
fi
INSTALL_EXTRAS

echo ""
echo "[5/7] Collecting AMI manifest..."
MANIFEST=$(ssh -i "$SSH_KEY" ubuntu@$IP << 'MANIFEST_EOF'
cat << MJSON
{
  "built": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "base_ami": "$(curl -s http://169.254.169.254/latest/meta-data/ami-id 2>/dev/null || echo "unknown")",
  "instance_type": "$(curl -s http://169.254.169.254/latest/meta-data/instance-type 2>/dev/null || echo "unknown")",
  "os": "$(lsb_release -ds 2>/dev/null || cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '"')",
  "kernel": "$(uname -r)",
  "docker": "$(sudo docker --version 2>/dev/null | head -1)",
  "docker_compose": "$(sudo docker compose version 2>/dev/null | head -1)",
  "node": "$(sudo docker exec claude-portable node --version 2>/dev/null || echo "unknown")",
  "npm": "$(sudo docker exec claude-portable npm --version 2>/dev/null || echo "unknown")",
  "claude_code": "$(sudo docker exec claude-portable claude --version 2>/dev/null || echo "unknown")",
  "python": "$(sudo docker exec claude-portable python3 --version 2>/dev/null || echo "unknown")",
  "chrome": "$(sudo docker exec claude-portable google-chrome --version 2>/dev/null || echo "unknown")",
  "playwright": "$(sudo docker exec claude-portable python3 -c 'import playwright; print(playwright.__version__)' 2>/dev/null || echo "unknown")",
  "aws_cli": "$(sudo docker exec claude-portable aws --version 2>/dev/null || echo "unknown")",
  "gh_cli": "$(sudo docker exec claude-portable gh --version 2>/dev/null | head -1 || echo "unknown")",
  "global_npm_packages": $(sudo docker exec claude-portable bash -c 'npm list -g --depth=0 --json 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin).get(\"dependencies\",{}); print(json.dumps({k:v.get(\"version\",\"?\") for k,v in d.items()}))"' 2>/dev/null || echo '{}'),
  "pip_packages": $(sudo docker exec claude-portable bash -c 'pip list --format=json 2>/dev/null | python3 -c "import json,sys; print(json.dumps({p[\"name\"]:p[\"version\"] for p in json.load(sys.stdin)}))"' 2>/dev/null || echo '{}'),
  "disk_usage": "$(sudo docker exec claude-portable bash -c 'du -sh / 2>/dev/null | cut -f1' || echo "unknown")",
  "playwright_browsers": $(sudo docker exec claude-portable bash -c 'playwright install --dry-run 2>/dev/null | python3 -c "import sys; print(\"[\" + \",\".join([\"\\\"\" + l.strip() + \"\\\"\" for l in sys.stdin if l.strip()]) + \"]\")"' 2>/dev/null || echo '["unknown"]')
}
MJSON
MANIFEST_EOF
)

echo "  Manifest collected."

# Save manifest locally (git-tracked)
MANIFEST_DIR="$SCRIPT_DIR/ami-manifests"
mkdir -p "$MANIFEST_DIR"
MANIFEST_FILE="$MANIFEST_DIR/$AMI_NAME.json"
echo "$MANIFEST" | python3 -c "import json,sys; json.dump(json.load(sys.stdin), open('$MANIFEST_FILE','w'), indent=2)" 2>/dev/null || echo "$MANIFEST" > "$MANIFEST_FILE"

# Also save as "latest.json" for quick reference
cp "$MANIFEST_FILE" "$MANIFEST_DIR/latest.json"
echo "  Saved to $MANIFEST_FILE"

# Upload to S3 state bucket
STATE_BUCKET="claude-portable-state-$(aws sts get-caller-identity --query Account --output text --region "$REGION")"
if aws s3 ls "s3://$STATE_BUCKET" --region "$REGION" &>/dev/null; then
  echo "$MANIFEST" | aws s3 cp - "s3://$STATE_BUCKET/ami-manifests/$AMI_NAME.json" --region "$REGION" --sse AES256 --quiet
  echo "$MANIFEST" | aws s3 cp - "s3://$STATE_BUCKET/ami-manifests/latest.json" --region "$REGION" --sse AES256 --quiet
  echo "  Uploaded to S3."
fi

echo ""
echo "[6/8] Cleaning up for AMI..."
ssh -i "$SSH_KEY" ubuntu@$IP << 'CLEANUP'
set -ex
# Remove git credentials
rm -f ~/.git-credentials
git config --global --unset credential.helper 2>/dev/null || true

# Remove SSH host keys (regenerated on new instance)
sudo rm -f /etc/ssh/ssh_host_*

# Remove temp files
sudo rm -rf /tmp/* /var/tmp/*
sudo apt-get clean
sudo rm -rf /var/lib/apt/lists/*

# Remove .env (secrets -- will be written fresh on each launch)
sudo rm -f /opt/claude-portable/.env

echo "Cleanup done."
CLEANUP

echo ""
echo "[7/8] Creating AMI..."
AMI_ID=$(aws ec2 create-image \
  --instance-id "$INSTANCE_ID" \
  --name "$AMI_NAME" \
  --description "Claude Portable golden image: Docker + container + Chrome + Playwright + Node tools" \
  --tag-specifications "[{\"ResourceType\":\"image\",\"Tags\":[{\"Key\":\"Name\",\"Value\":\"$AMI_NAME\"},{\"Key\":\"Project\",\"Value\":\"claude-portable\"}]}]" \
  --query 'ImageId' --output text --region "$REGION")

echo "  AMI: $AMI_ID"
echo "  Waiting for AMI to be available (5-10 min)..."
aws ec2 wait image-available --image-ids "$AMI_ID" --region "$REGION"
echo "  AMI ready!"

# Terminate temp instance
echo "  Terminating build instance..."
aws ec2 terminate-instances --instance-ids "$INSTANCE_ID" --region "$REGION" > /dev/null

# Update config with new AMI
CONFIG_FILE="$SCRIPT_DIR/ccc.config.json"
if [ -f "$CONFIG_FILE" ]; then
  python3 -c "
import json
with open('$CONFIG_FILE') as f: cfg = json.load(f)
cfg['golden_ami'] = '$AMI_ID'
cfg['golden_ami_built'] = '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
with open('$CONFIG_FILE', 'w') as f: json.dump(cfg, f, indent=2)
print('  Updated ccc.config.json with golden_ami=$AMI_ID')
"
fi

# Commit manifest + config to git
echo ""
echo "[8/8] Committing manifest to git..."
cd "$SCRIPT_DIR"
if [ -d .git ]; then
  git add ami-manifests/ ccc.config.json 2>/dev/null || true
  git commit -m "ami: $AMI_NAME ($AMI_ID)

Built: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Claude Code: $(echo "$MANIFEST" | python3 -c "import json,sys; print(json.load(sys.stdin).get('claude_code','?'))" 2>/dev/null || echo "?")
Node: $(echo "$MANIFEST" | python3 -c "import json,sys; print(json.load(sys.stdin).get('node','?'))" 2>/dev/null || echo "?")
Chrome: $(echo "$MANIFEST" | python3 -c "import json,sys; print(json.load(sys.stdin).get('chrome','?'))" 2>/dev/null || echo "?")
Playwright: $(echo "$MANIFEST" | python3 -c "import json,sys; print(json.load(sys.stdin).get('playwright','?'))" 2>/dev/null || echo "?")" 2>/dev/null || echo "  (not a git repo or no changes)"
fi

echo ""
echo "========================================="
echo "  Golden AMI: $AMI_ID"
echo "  Name: $AMI_NAME"
echo "========================================="
echo ""
echo "  Includes:"
echo "    - Docker CE + docker-compose"
echo "    - claude-portable container (pre-built)"
echo "    - Google Chrome + Xvfb"
echo "    - Playwright + Chromium"
echo "    - Node.js 20 + TypeScript + Prettier + ESLint"
echo "    - Python 3 + requests + beautifulsoup4 + httpx"
echo "    - AWS CLI v2 + GitHub CLI + Bitwarden CLI"
echo ""
echo "  Launch time: ~1-2 min (vs ~7 min from scratch)"
echo ""
echo "  Use: ccc will auto-detect the golden AMI from ccc.config.json"
