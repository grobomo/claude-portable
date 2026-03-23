#!/bin/bash
# One-click deploy: launch Claude Portable on AWS EC2 spot instance.
# Usage: ./run.sh [--profile PROFILE] [--region REGION] [--instance-type TYPE]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Defaults
STACK_NAME=""
AWS_PROFILE="${CLAUDE_PORTABLE_AWS_PROFILE:-default}"
AWS_REGION="${CLAUDE_PORTABLE_AWS_REGION:-us-east-2}"
INSTANCE_TYPE="t3.large"
KEY_PAIR="claude-portable-key"
SPOT_MAX_PRICE="0.08"
REPO_URL=""
# Convert to Windows path if running in Git Bash (AWS CLI needs native paths)
if command -v cygpath &>/dev/null; then
  CF_TEMPLATE="$(cygpath -w "$SCRIPT_DIR/cloudformation/claude-portable-spot.yaml")"
else
  CF_TEMPLATE="$SCRIPT_DIR/cloudformation/claude-portable-spot.yaml"
fi

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) AWS_PROFILE="$2"; shift 2 ;;
    --region) AWS_REGION="$2"; shift 2 ;;
    --instance-type) INSTANCE_TYPE="$2"; shift 2 ;;
    --key-pair) KEY_PAIR="$2"; shift 2 ;;
    --repo-url) REPO_URL="$2"; shift 2 ;;
    --name) STACK_NAME="claude-portable-$2"; shift 2 ;;
    --stack-name) STACK_NAME="$2"; shift 2 ;;
    --help|-h)
      cat <<'USAGE'
run.sh -- One-click Claude Portable deploy to AWS EC2 spot

OPTIONS:
  --name LABEL         Short name for this instance (e.g. "dev", "lab1", "recording")
                       Creates stack "claude-portable-LABEL" (default: random suffix)
  --profile NAME       AWS CLI profile (default: $CLAUDE_PORTABLE_AWS_PROFILE or "default")
  --region REGION      AWS region (default: us-east-2)
  --instance-type TYPE EC2 instance type (default: t3.large)
  --key-pair NAME      EC2 key pair name (default: claude-portable-key)
  --repo-url URL       Git clone URL for this repo (required if not set in .env)
  --stack-name NAME    CloudFormation stack name (overrides --name)

REQUIRED SECRETS (set in .env or environment):
  CLAUDE_OAUTH_ACCESS_TOKEN    Claude OAuth access token
  CLAUDE_OAUTH_REFRESH_TOKEN   Claude OAuth refresh token
  GITHUB_TOKEN                 GitHub PAT for private repo cloning

OPTIONAL:
  SSH_PUBLIC_KEY               SSH public key for rsync into container
USAGE
      exit 0 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

# Auto-generate stack name if not specified
if [ -z "$STACK_NAME" ]; then
  STACK_NAME="claude-portable-$(date +%m%d-%H%M)"
fi

# Load .env if present
[ -f "$SCRIPT_DIR/.env" ] && set -a && source "$SCRIPT_DIR/.env" && set +a

# Validate required secrets
MISSING=""
[ -z "${CLAUDE_OAUTH_ACCESS_TOKEN:-}" ] && MISSING="$MISSING CLAUDE_OAUTH_ACCESS_TOKEN"
[ -z "${CLAUDE_OAUTH_REFRESH_TOKEN:-}" ] && MISSING="$MISSING CLAUDE_OAUTH_REFRESH_TOKEN"
[ -z "${GITHUB_TOKEN:-}" ] && MISSING="$MISSING GITHUB_TOKEN"
[ -z "${REPO_URL:-}" ] && MISSING="$MISSING REPO_URL"

if [ -n "$MISSING" ]; then
  echo "ERROR: Missing required variables:$MISSING"
  echo "Set them in .env or pass via environment / --repo-url flag."
  exit 1
fi

# Validate CF template exists
if [ ! -f "$CF_TEMPLATE" ]; then
  echo "ERROR: CloudFormation template not found at $CF_TEMPLATE"
  exit 1
fi

# Check for existing stack
echo "=== Claude Portable Deploy ==="
echo "  Stack:    $STACK_NAME"
echo "  Region:   $AWS_REGION"
echo "  Profile:  $AWS_PROFILE"
echo "  Instance: $INSTANCE_TYPE (spot, max \$$SPOT_MAX_PRICE/hr)"
echo ""

EXISTING=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --profile "$AWS_PROFILE" --region "$AWS_REGION" \
  --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "NONE")

if [ "$EXISTING" != "NONE" ]; then
  echo "Stack '$STACK_NAME' already exists (status: $EXISTING)."
  if [[ "$EXISTING" == *COMPLETE* ]] || [[ "$EXISTING" == *IN_PROGRESS* ]]; then
    INSTANCE_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
      --profile "$AWS_PROFILE" --region "$AWS_REGION" \
      --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text 2>/dev/null || echo "")
    if [ -n "$INSTANCE_ID" ]; then
      IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
        --profile "$AWS_PROFILE" --region "$AWS_REGION" \
        --query 'Reservations[0].Instances[0].PublicIpAddress' --output text 2>/dev/null || echo "pending")
      echo ""
      echo "=== Connection Info ==="
      echo "  Instance: $INSTANCE_ID"
      echo "  IP:       $IP"
      echo "  SSH host: ssh -i ~/.ssh/${KEY_PAIR}.pem ubuntu@$IP"
      echo "  SSH ctr:  ssh -p 2222 claude@$IP"
      echo "  Claude:   ssh -t -i ~/.ssh/${KEY_PAIR}.pem ubuntu@$IP 'docker exec -it claude-portable claude'"
    fi
    exit 0
  fi
  # Stack in failed state -- delete and recreate
  echo "Deleting failed stack..."
  aws cloudformation delete-stack --stack-name "$STACK_NAME" \
    --profile "$AWS_PROFILE" --region "$AWS_REGION"
  aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" \
    --profile "$AWS_PROFILE" --region "$AWS_REGION"
  echo "  Deleted."
fi

# Deploy
echo "Creating stack..."
aws cloudformation create-stack \
  --stack-name "$STACK_NAME" \
  --template-body "file://$CF_TEMPLATE" \
  --parameters \
    "ParameterKey=KeyPairName,ParameterValue=$KEY_PAIR" \
    "ParameterKey=InstanceType,ParameterValue=$INSTANCE_TYPE" \
    "ParameterKey=GitHubToken,ParameterValue=$GITHUB_TOKEN" \
    "ParameterKey=OAuthAccessToken,ParameterValue=$CLAUDE_OAUTH_ACCESS_TOKEN" \
    "ParameterKey=OAuthRefreshToken,ParameterValue=$CLAUDE_OAUTH_REFRESH_TOKEN" \
    "ParameterKey=SSHPubKey,ParameterValue=${SSH_PUBLIC_KEY:-}" \
    "ParameterKey=RepoUrl,ParameterValue=$REPO_URL" \
    "ParameterKey=SpotMaxPrice,ParameterValue=$SPOT_MAX_PRICE" \
    "ParameterKey=InstanceName,ParameterValue=$STACK_NAME" \
  --profile "$AWS_PROFILE" --region "$AWS_REGION" \
  --output text > /dev/null

echo "  Waiting for stack creation (2-5 min)..."
aws cloudformation wait stack-create-complete \
  --stack-name "$STACK_NAME" \
  --profile "$AWS_PROFILE" --region "$AWS_REGION"

# Get outputs
INSTANCE_ID=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --profile "$AWS_PROFILE" --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text)
IP=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --profile "$AWS_PROFILE" --region "$AWS_REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='PublicIP'].OutputValue" --output text)

echo ""
echo "=== Stack Created ==="
echo "  Instance: $INSTANCE_ID"
echo "  IP:       $IP"
echo ""
echo "  Container needs ~2 min to build after EC2 starts."
echo "  Check init progress:"
echo "    ssh -i ~/.ssh/${KEY_PAIR}.pem ubuntu@$IP 'tail -f /var/log/claude-portable-init.log'"
echo ""
echo "=== Connection ==="
echo "  SSH host: ssh -i ~/.ssh/${KEY_PAIR}.pem ubuntu@$IP"
echo "  SSH ctr:  ssh -p 2222 claude@$IP"
echo "  Claude:   ssh -t -i ~/.ssh/${KEY_PAIR}.pem ubuntu@$IP 'docker exec -it claude-portable claude'"
echo ""
echo "  Health:   ssh -p 2222 claude@$IP '/opt/claude-portable/scripts/health-check.sh'"
