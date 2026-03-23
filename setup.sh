#!/bin/bash
# Claude Portable -- one-command setup and launch.
# Usage: ./setup.sh [--name LABEL] [--api-key] [--region REGION]
#
# Does everything: SSH key, auth detection, .env, launch, wait, connect.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
NAME=""
FORCE_API_KEY=false
FORCE_OAUTH=false
REGION="${AWS_DEFAULT_REGION:-us-east-2}"
INSTANCE_TYPE="t3.large"
KEY_NAME="claude-portable-key"

# --- Parse args ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --name) NAME="$2"; shift 2 ;;
    --api-key) FORCE_API_KEY=true; shift ;;
    --oauth) FORCE_OAUTH=true; shift ;;
    --region) REGION="$2"; shift 2 ;;
    --instance-type) INSTANCE_TYPE="$2"; shift 2 ;;
    --help|-h)
      echo "Usage: ./setup.sh [--name LABEL] [--api-key] [--region REGION]"
      echo ""
      echo "  --name LABEL       Instance name (default: auto-generated)"
      echo "  --api-key          Force API key auth mode"
      echo "  --oauth            Force OAuth auth mode"
      echo "  --region REGION    AWS region (default: us-east-2)"
      echo "  --instance-type T  EC2 type (default: t3.large)"
      exit 0 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

echo "========================================="
echo "  Claude Portable -- One-Command Setup"
echo "========================================="
echo ""

# --- 1. Check prerequisites ---
echo "[1/9] Checking prerequisites..."

if ! command -v aws &>/dev/null; then
  echo "ERROR: AWS CLI not found."
  echo "  Install: https://aws.amazon.com/cli/"
  echo "  Then run: aws configure"
  exit 1
fi

if ! aws sts get-caller-identity &>/dev/null; then
  echo "ERROR: AWS CLI not configured."
  echo "  Run: aws configure"
  echo "  You need: Access Key ID, Secret Access Key, Region"
  exit 1
fi

AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
echo "  AWS account: $AWS_ACCOUNT"
echo "  Region: $REGION"

# Create encrypted state bucket (idempotent)
bash "$SCRIPT_DIR/scripts/state-sync.sh" setup 2>/dev/null || true

if ! command -v git &>/dev/null; then
  echo "ERROR: Git not found. Install: https://git-scm.com/"
  exit 1
fi

echo "  Prerequisites OK."

# --- 2. Create SSH key pair (if needed) ---
echo ""
echo "[2/9] Setting up SSH key pair..."

SSH_KEY=""
# Find existing .pem file
for candidate in "$HOME/.ssh/${KEY_NAME}.pem" "$HOME/archive/.ssh/${KEY_NAME}.pem" "$HOME/.ssh/claude-portable.pem"; do
  if [ -f "$candidate" ]; then
    SSH_KEY="$candidate"
    break
  fi
done

if aws ec2 describe-key-pairs --key-names "$KEY_NAME" --region "$REGION" &>/dev/null; then
  echo "  Key pair '$KEY_NAME' exists in AWS."
  if [ -z "$SSH_KEY" ]; then
    echo "  WARNING: Key pair exists in AWS but no .pem file found locally."
    echo "  Looking in: ~/.ssh/${KEY_NAME}.pem"
    echo "  If you have it elsewhere, set SSH_KEY env var."
    # Try the default anyway
    SSH_KEY="$HOME/.ssh/${KEY_NAME}.pem"
  fi
else
  echo "  Creating key pair '$KEY_NAME'..."
  mkdir -p "$HOME/.ssh"
  SSH_KEY="$HOME/.ssh/${KEY_NAME}.pem"
  aws ec2 create-key-pair \
    --key-name "$KEY_NAME" \
    --region "$REGION" \
    --query 'KeyMaterial' \
    --output text > "$SSH_KEY"
  chmod 600 "$SSH_KEY"
  echo "  Saved to $SSH_KEY"
fi

echo "  SSH key: $SSH_KEY"

# --- 3. Detect auth method ---
echo ""
echo "[3/9] Detecting authentication..."

AUTH_TYPE=""
API_KEY=""
OAUTH_ACCESS=""
OAUTH_REFRESH=""
OAUTH_EXPIRES=""
CREDS_FILE=""

# Check 1: keyring (if python + keyring available)
if [ "$FORCE_API_KEY" = false ] && [ "$FORCE_OAUTH" = false ]; then
  API_KEY=$(python3 -c "
import keyring
val = keyring.get_password('claude-code', 'anthropic/API_KEY')
if val: print(val, end='')
" 2>/dev/null || true)
  if [ -n "$API_KEY" ]; then
    AUTH_TYPE="api_key"
    echo "  Found API key in OS credential store."
  fi
fi

# Check 2: ANTHROPIC_API_KEY env var
if [ -z "$AUTH_TYPE" ] && [ "$FORCE_OAUTH" = false ]; then
  if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    API_KEY="$ANTHROPIC_API_KEY"
    AUTH_TYPE="api_key"
    echo "  Found API key in ANTHROPIC_API_KEY env var."
  fi
fi

# Check 3: local Claude credentials file (OAuth)
if [ -z "$AUTH_TYPE" ] && [ "$FORCE_API_KEY" = false ]; then
  for candidate in \
    "$HOME/.claude/.credentials.json" \
    "${USERPROFILE:-}/.claude/.credentials.json" \
    "${APPDATA:-}/../.claude/.credentials.json"; do
    if [ -f "$candidate" ] 2>/dev/null; then
      HAS_OAUTH=$(python3 -c "
import json
d = json.load(open('$candidate'))
if 'claudeAiOauth' in d and d['claudeAiOauth'].get('accessToken'):
    print('yes', end='')
" 2>/dev/null || true)
      if [ "$HAS_OAUTH" = "yes" ]; then
        CREDS_FILE="$candidate"
        AUTH_TYPE="oauth"
        OAUTH_ACCESS=$(python3 -c "import json; print(json.load(open('$CREDS_FILE'))['claudeAiOauth']['accessToken'], end='')")
        OAUTH_REFRESH=$(python3 -c "import json; print(json.load(open('$CREDS_FILE'))['claudeAiOauth']['refreshToken'], end='')")
        OAUTH_EXPIRES=$(python3 -c "import json; print(json.load(open('$CREDS_FILE'))['claudeAiOauth'].get('expiresAt',''), end='')")
        echo "  Found OAuth tokens in $CREDS_FILE"
        break
      fi
    fi
  done
fi

# Check 4: forced API key mode
if [ "$FORCE_API_KEY" = true ] && [ -z "$API_KEY" ]; then
  echo "  --api-key specified but no key found."
  echo "  Set ANTHROPIC_API_KEY env var or store via credential-manager:"
  echo "    python ~/.claude/skills/credential-manager/store_gui.py anthropic/API_KEY"
  exit 1
fi

# Nothing found
if [ -z "$AUTH_TYPE" ]; then
  echo ""
  echo "  No authentication found. Two options:"
  echo ""
  echo "  Option A - API Key (simplest):"
  echo "    1. Go to https://console.anthropic.com/account/keys"
  echo "    2. Create a key"
  echo "    3. Run: export ANTHROPIC_API_KEY=sk-ant-..."
  echo "    4. Re-run this script"
  echo ""
  echo "  Option B - OAuth (Enterprise/Max):"
  echo "    1. Run 'claude' locally to log in"
  echo "    2. Re-run this script (tokens auto-detected)"
  exit 1
fi

echo "  Auth: $AUTH_TYPE"

# --- 4. Write .env ---
echo ""
echo "[4/9] Writing .env..."

GH_TOKEN=$(gh auth token 2>/dev/null || echo "none")

if [ "$AUTH_TYPE" = "api_key" ]; then
  cat > "$SCRIPT_DIR/.env" << ENVEOF
ANTHROPIC_API_KEY=$API_KEY
GITHUB_TOKEN=$GH_TOKEN
REPO_URL=https://github.com/grobomo/claude-portable.git
ENVEOF
else
  cat > "$SCRIPT_DIR/.env" << ENVEOF
CLAUDE_OAUTH_ACCESS_TOKEN=$OAUTH_ACCESS
CLAUDE_OAUTH_REFRESH_TOKEN=$OAUTH_REFRESH
CLAUDE_OAUTH_EXPIRES_AT=$OAUTH_EXPIRES
GITHUB_TOKEN=$GH_TOKEN
REPO_URL=https://github.com/grobomo/claude-portable.git
ENVEOF
fi

chmod 600 "$SCRIPT_DIR/.env" 2>/dev/null || true
echo "  .env written."

# --- 5. Launch instance ---
echo ""
echo "[5/9] Launching EC2 spot instance..."

EXTRA_ARGS=""
[ -n "$NAME" ] && EXTRA_ARGS="--name $NAME"
[ -n "$REGION" ] && EXTRA_ARGS="$EXTRA_ARGS --region $REGION"
[ -n "$INSTANCE_TYPE" ] && EXTRA_ARGS="$EXTRA_ARGS --instance-type $INSTANCE_TYPE"

bash "$SCRIPT_DIR/run.sh" $EXTRA_ARGS

# Get the stack name and IP
if [ -n "$NAME" ]; then
  STACK_NAME="claude-portable-$NAME"
else
  # run.sh auto-generates, find the latest
  STACK_NAME=$(aws cloudformation list-stacks \
    --stack-status-filter CREATE_COMPLETE \
    --region "$REGION" \
    --query "StackSummaries[?starts_with(StackName, 'claude-portable-')] | sort_by(@, &CreationTime) | [-1].StackName" \
    --output text 2>/dev/null || echo "")
fi

IP=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='PublicIP'].OutputValue" --output text 2>/dev/null || echo "")

if [ -z "$IP" ] || [ "$IP" = "None" ]; then
  echo "ERROR: Could not get instance IP. Check: aws cloudformation describe-stack-events --stack-name $STACK_NAME"
  exit 1
fi

echo "  Stack: $STACK_NAME"
echo "  IP: $IP"

# --- 6. Wait for container ---
echo ""
echo "[6/9] Waiting for Docker container to build (~2-3 min)..."

READY=false
for i in $(seq 1 40); do
  STATUS=$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o LogLevel=ERROR -i "$SSH_KEY" ubuntu@$IP \
    "docker ps --filter name=claude-portable --format '{{.Status}}'" 2>/dev/null || echo "")
  if [[ "$STATUS" == Up* ]]; then
    READY=true
    break
  fi
  printf "."
  sleep 10
done
echo ""

if [ "$READY" = false ]; then
  echo "  Container not ready after 6 min. Check manually:"
  echo "    ssh -i $SSH_KEY ubuntu@$IP 'tail -20 /var/log/claude-portable-init.log'"
  exit 1
fi

echo "  Container is running!"

# --- 7. Push fresh credentials ---
echo ""
echo "[7/9] Pushing credentials to container..."

if [ "$AUTH_TYPE" = "oauth" ] && [ -n "$CREDS_FILE" ]; then
  # Push full credentials JSON for OAuth
  CREDS_CONTENT=$(cat "$CREDS_FILE")
  ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR -i "$SSH_KEY" ubuntu@$IP \
    "docker exec claude-portable bash -c 'cat > /home/claude/.claude/.credentials.json << CREDEOF
$CREDS_CONTENT
CREDEOF'"
  echo "  OAuth credentials pushed."
elif [ "$AUTH_TYPE" = "api_key" ]; then
  ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR -i "$SSH_KEY" ubuntu@$IP \
    "docker exec claude-portable bash -c 'echo export ANTHROPIC_API_KEY=$API_KEY >> /home/claude/.bashrc'"
  echo "  API key configured in container."
fi

# --- 8. Set trusted directories ---
echo ""
echo "[8/9] Configuring container..."

ssh -o LogLevel=ERROR -i "$SSH_KEY" ubuntu@$IP 'docker exec -u root claude-portable python3 -c "
import json
p = \"/home/claude/.claude/settings.local.json\"
try: d = json.load(open(p))
except: d = {}
d[\"trustedDirectories\"] = [\"/workspace\", \"/home/claude\", \"/tmp\"]
d[\"hasCompletedOnboarding\"] = True
json.dump(d, open(p, \"w\"), indent=2)
"' 2>/dev/null
echo "  Trusted directories set."

# --- 9. Connect ---
echo ""
echo "[9/9] Ready!"
echo ""
echo "========================================="
echo "  Claude Portable is running!"
echo "========================================="
echo ""
echo "  Instance:  $STACK_NAME"
echo "  IP:        $IP"
echo "  Auth:      $AUTH_TYPE"
echo ""
echo "  Connect:"
echo "    ssh -i $SSH_KEY ubuntu@$IP -t 'docker exec -it claude-portable claude'"
echo ""
echo "  Manage:"
echo "    ./list.sh              # list instances"
echo "    ./terminate.sh --all   # shut down"
echo "    ./push.sh --all        # push updates"
echo ""

# Try to open a terminal tab
if command -v wt.exe &>/dev/null; then
  DISPLAY_NAME="${NAME:-cloud}"
  wt.exe -w 0 new-tab --title "$DISPLAY_NAME ($IP)" ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" ubuntu@$IP -t "docker exec -it claude-portable claude"
  echo "  Terminal tab opened!"
elif command -v osascript &>/dev/null; then
  osascript -e "tell application \"Terminal\" to do script \"ssh -o StrictHostKeyChecking=no -i $SSH_KEY ubuntu@$IP -t 'docker exec -it claude-portable claude'\""
  echo "  Terminal window opened!"
else
  echo "  Run the connect command above to start."
fi
