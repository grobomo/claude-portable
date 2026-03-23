#!/bin/bash
# List all running Claude Portable instances across all CF stacks.
# Usage: ./list.sh [--profile PROFILE] [--region REGION]
set -euo pipefail

AWS_PROFILE="${CLAUDE_PORTABLE_AWS_PROFILE:-default}"
AWS_REGION="${CLAUDE_PORTABLE_AWS_REGION:-us-east-2}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) AWS_PROFILE="$2"; shift 2 ;;
    --region) AWS_REGION="$2"; shift 2 ;;
    *) shift ;;
  esac
done

echo "=== Claude Portable Instances (${AWS_REGION}) ==="
echo ""

# Find all stacks with claude-portable prefix
STACKS=$(aws cloudformation list-stacks \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE CREATE_IN_PROGRESS \
  --profile "$AWS_PROFILE" --region "$AWS_REGION" \
  --query "StackSummaries[?starts_with(StackName, 'claude-portable')].StackName" \
  --output text 2>/dev/null)

if [ -z "$STACKS" ]; then
  echo "  No instances running."
  exit 0
fi

printf "%-30s %-20s %-16s %-12s %s\n" "STACK" "INSTANCE" "IP" "TYPE" "STATUS"
printf "%-30s %-20s %-16s %-12s %s\n" "-----" "--------" "--" "----" "------"

for STACK in $STACKS; do
  INSTANCE_ID=$(aws cloudformation describe-stacks --stack-name "$STACK" \
    --profile "$AWS_PROFILE" --region "$AWS_REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text 2>/dev/null || echo "")

  if [ -n "$INSTANCE_ID" ] && [ "$INSTANCE_ID" != "None" ]; then
    INFO=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
      --profile "$AWS_PROFILE" --region "$AWS_REGION" \
      --query 'Reservations[0].Instances[0].[PublicIpAddress,InstanceType,State.Name]' \
      --output text 2>/dev/null || echo "- - -")
    IP=$(echo "$INFO" | awk '{print $1}')
    TYPE=$(echo "$INFO" | awk '{print $2}')
    STATE=$(echo "$INFO" | awk '{print $3}')
    printf "%-30s %-20s %-16s %-12s %s\n" "$STACK" "$INSTANCE_ID" "$IP" "$TYPE" "$STATE"
  else
    printf "%-30s %-20s %-16s %-12s %s\n" "$STACK" "-" "-" "-" "provisioning"
  fi
done

echo ""
echo "Connect: ssh -p 2222 claude@<IP>"
