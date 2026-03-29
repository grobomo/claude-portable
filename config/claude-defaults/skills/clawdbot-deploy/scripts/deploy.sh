#!/bin/bash
# =============================================================================
# Clawdbot Quick Deploy Script
# =============================================================================
# Usage: ./deploy.sh [--profile PROFILE] [--region REGION] [--key-pair NAME]
#
# Deploys the base Clawdbot stack with auto-detected settings:
# - Detects your current public IP for SSH access
# - Uses default AWS profile/region if not specified
# - Prompts for missing required parameters
# =============================================================================

set -e

# -----------------------------------------------------------------------------
# Parse Arguments
# -----------------------------------------------------------------------------
AWS_PROFILE=""
AWS_REGION=""
KEY_PAIR=""
STACK_NAME="clawdbot"

while [[ $# -gt 0 ]]; do
    case $1 in
        --profile)
            AWS_PROFILE="$2"
            shift 2
            ;;
        --region)
            AWS_REGION="$2"
            shift 2
            ;;
        --key-pair)
            KEY_PAIR="$2"
            shift 2
            ;;
        --stack-name)
            STACK_NAME="$2"
            shift 2
            ;;
        --help|-h)
            echo "Clawdbot Quick Deploy"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --profile PROFILE   AWS profile name"
            echo "  --region REGION     AWS region"
            echo "  --key-pair NAME     EC2 key pair name"
            echo "  --stack-name NAME   CloudFormation stack name (default: clawdbot)"
            echo ""
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Build AWS CLI args
AWS_ARGS=""
[ -n "$AWS_PROFILE" ] && AWS_ARGS="$AWS_ARGS --profile $AWS_PROFILE"
[ -n "$AWS_REGION" ] && AWS_ARGS="$AWS_ARGS --region $AWS_REGION"

# -----------------------------------------------------------------------------
# Detect Public IP
# -----------------------------------------------------------------------------
echo ">>> Detecting your public IP..."
PUBLIC_IP=$(curl -s --max-time 5 ifconfig.me || curl -s --max-time 5 icanhazip.com || curl -s --max-time 5 checkip.amazonaws.com)

if [ -z "$PUBLIC_IP" ]; then
    echo "ERROR: Could not detect public IP"
    echo "Please provide your IP manually with: AllowedIP=x.x.x.x/32"
    exit 1
fi

ALLOWED_IP="${PUBLIC_IP}/32"
echo "    Your IP: $ALLOWED_IP"

# -----------------------------------------------------------------------------
# Get Key Pair (if not specified)
# -----------------------------------------------------------------------------
if [ -z "$KEY_PAIR" ]; then
    echo ""
    echo ">>> Available EC2 key pairs:"
    aws ec2 describe-key-pairs $AWS_ARGS --query 'KeyPairs[*].KeyName' --output text | tr '\t' '\n' | nl
    echo ""
    read -p "Enter key pair name: " KEY_PAIR
fi

if [ -z "$KEY_PAIR" ]; then
    echo "ERROR: Key pair is required"
    exit 1
fi

# -----------------------------------------------------------------------------
# Confirm Deployment
# -----------------------------------------------------------------------------
echo ""
echo "========================================"
echo "Clawdbot Deployment Summary"
echo "========================================"
echo "Stack Name:  $STACK_NAME"
echo "Allowed IP:  $ALLOWED_IP"
echo "Key Pair:    $KEY_PAIR"
echo "Profile:     ${AWS_PROFILE:-default}"
echo "Region:      ${AWS_REGION:-default}"
echo "========================================"
echo ""
read -p "Deploy? [y/N] " CONFIRM

if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# -----------------------------------------------------------------------------
# Find Template
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="${SCRIPT_DIR}/../cloudformation/clawdbot-base.yaml"

if [ ! -f "$TEMPLATE" ]; then
    echo "ERROR: Template not found: $TEMPLATE"
    exit 1
fi

# -----------------------------------------------------------------------------
# Deploy Stack
# -----------------------------------------------------------------------------
echo ""
echo ">>> Deploying CloudFormation stack..."
aws cloudformation deploy \
    --template-file "$TEMPLATE" \
    --stack-name "$STACK_NAME" \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides \
        AllowedIP="$ALLOWED_IP" \
        KeyPairName="$KEY_PAIR" \
    $AWS_ARGS

# -----------------------------------------------------------------------------
# Show Outputs
# -----------------------------------------------------------------------------
echo ""
echo ">>> Stack deployed! Getting outputs..."
echo ""

aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
    --output table \
    $AWS_ARGS

# -----------------------------------------------------------------------------
# Start Instance
# -----------------------------------------------------------------------------
echo ""
read -p "Start Clawdbot instance now? [Y/n] " START

if [[ ! "$START" =~ ^[Nn]$ ]]; then
    echo ">>> Starting instance..."
    FUNCTION_NAME="${STACK_NAME}-orchestrator"

    RESULT=$(aws lambda invoke \
        --function-name "$FUNCTION_NAME" \
        --payload '{"action": "start"}' \
        --cli-binary-format raw-in-base64-out \
        /dev/stdout \
        $AWS_ARGS 2>/dev/null)

    echo "$RESULT" | jq . 2>/dev/null || echo "$RESULT"

    # Wait for IP
    echo ""
    echo ">>> Waiting for public IP..."
    for i in {1..30}; do
        RESULT=$(aws lambda invoke \
            --function-name "$FUNCTION_NAME" \
            --payload '{"action": "status"}' \
            --cli-binary-format raw-in-base64-out \
            /dev/stdout \
            $AWS_ARGS 2>/dev/null)

        IP=$(echo "$RESULT" | jq -r '.public_ip // empty' 2>/dev/null)

        if [ -n "$IP" ] && [ "$IP" != "pending" ] && [ "$IP" != "null" ]; then
            echo ""
            echo "========================================"
            echo "Clawdbot is running!"
            echo "========================================"
            echo ""
            echo "SSH Command:"
            echo "  ssh -i ~/.aws/${KEY_PAIR}.pem ec2-user@${IP}"
            echo ""
            echo "Configure Claude (after SSH):"
            echo "  sudo -u clawdbot clawdbot models auth paste-token --provider anthropic"
            echo ""
            echo "Check Status:"
            echo "  sudo -u clawdbot clawdbot status"
            echo ""
            exit 0
        fi

        echo -n "."
        sleep 5
    done

    echo ""
    echo "Instance still starting. Check status with:"
    echo "  aws lambda invoke --function-name $FUNCTION_NAME --payload '{\"action\": \"status\"}' /dev/stdout $AWS_ARGS"
fi
