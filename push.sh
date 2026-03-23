#!/bin/bash
# Push file updates to all running Claude Portable instances.
# Usage:
#   ./push.sh scripts/msg.sh              Push a file to all instances
#   ./push.sh scripts/msg.sh --name test1 Push to specific instance
#   ./push.sh --all                       Push all scripts/* to all instances
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SSH_KEY="${CLAUDE_PORTABLE_SSH_KEY:-$(cygpath -u "$USERPROFILE/archive/.ssh/claude-portable.pem" 2>/dev/null || echo "$HOME/archive/.ssh/claude-portable.pem")}"
AWS_PROFILE="${CLAUDE_PORTABLE_AWS_PROFILE:-default}"
AWS_REGION="${CLAUDE_PORTABLE_AWS_REGION:-us-east-2}"
TARGET_STACK=""
PUSH_ALL=false
FILES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name) TARGET_STACK="claude-portable-$2"; shift 2 ;;
    --all) PUSH_ALL=true; shift ;;
    --key) SSH_KEY="$2"; shift 2 ;;
    --help|-h)
      echo "Usage: ./push.sh [FILE...] [--name LABEL] [--all]"
      echo "  FILE              File(s) relative to project root to push"
      echo "  --all             Push all scripts/* and config/*"
      echo "  --name LABEL      Target specific instance (default: all running)"
      exit 0 ;;
    *) FILES+=("$1"); shift ;;
  esac
done

# Find running instances
get_instances() {
  local filter=""
  if [ -n "$TARGET_STACK" ]; then
    filter="$TARGET_STACK"
  else
    filter="claude-portable-"
  fi

  STACKS=$(aws cloudformation list-stacks \
    --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
    --profile "$AWS_PROFILE" --region "$AWS_REGION" \
    --query "StackSummaries[?starts_with(StackName, '$filter')].StackName" \
    --output text 2>/dev/null)

  for STACK in $STACKS; do
    INSTANCE_ID=$(aws cloudformation describe-stacks --stack-name "$STACK" \
      --profile "$AWS_PROFILE" --region "$AWS_REGION" \
      --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text 2>/dev/null || echo "")
    if [ -n "$INSTANCE_ID" ] && [ "$INSTANCE_ID" != "None" ]; then
      IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
        --profile "$AWS_PROFILE" --region "$AWS_REGION" \
        --query 'Reservations[0].Instances[0].PublicIpAddress' --output text 2>/dev/null || echo "")
      NAME=$(echo "$STACK" | sed 's/claude-portable-//')
      if [ -n "$IP" ] && [ "$IP" != "None" ]; then
        echo "$NAME:$IP"
      fi
    fi
  done
}

push_file() {
  local FILE="$1" IP="$2" NAME="$3"
  local LOCAL_PATH="$SCRIPT_DIR/$FILE"

  if [ ! -f "$LOCAL_PATH" ]; then
    echo "  SKIP $FILE (not found)"
    return
  fi

  # Determine container destination
  local DEST=""
  case "$FILE" in
    scripts/msg.sh)   DEST="/usr/local/bin/msg" ;;
    scripts/*.sh)     DEST="/opt/claude-portable/scripts/$(basename "$FILE")" ;;
    config/*)         DEST="/opt/claude-portable/config/$(basename "$FILE")" ;;
    *)                DEST="/workspace/$(basename "$FILE")" ;;
  esac

  scp -o StrictHostKeyChecking=no -o LogLevel=ERROR -i "$SSH_KEY" \
    "$LOCAL_PATH" ubuntu@$IP:/tmp/_push_$(basename "$FILE")
  ssh -o StrictHostKeyChecking=no -o LogLevel=ERROR -i "$SSH_KEY" ubuntu@$IP \
    "sed -i 's/\r$//' /tmp/_push_$(basename "$FILE") && \
     docker cp /tmp/_push_$(basename "$FILE") claude-portable:$DEST && \
     docker exec -u root claude-portable chown claude:claude $DEST && \
     docker exec -u root claude-portable chmod +x $DEST 2>/dev/null; \
     rm /tmp/_push_$(basename "$FILE")"
  echo "  $FILE -> $DEST"
}

echo "=== Claude Portable Push ==="

INSTANCES=$(get_instances)
if [ -z "$INSTANCES" ]; then
  echo "No running instances found."
  exit 1
fi

# Determine files to push
if [ "$PUSH_ALL" = true ]; then
  FILES=()
  for f in "$SCRIPT_DIR"/scripts/*.sh; do
    FILES+=("scripts/$(basename "$f")")
  done
  for f in "$SCRIPT_DIR"/config/*; do
    FILES+=("config/$(basename "$f")")
  done
fi

if [ ${#FILES[@]} -eq 0 ]; then
  echo "No files specified. Use --all or list files to push."
  exit 1
fi

for INST in $INSTANCES; do
  NAME="${INST%%:*}"
  IP="${INST##*:}"
  echo ""
  echo "[$NAME] $IP"
  for FILE in "${FILES[@]}"; do
    push_file "$FILE" "$IP" "$NAME"
  done
done

echo ""
echo "Done. Pushed ${#FILES[@]} file(s) to $(echo "$INSTANCES" | wc -w) instance(s)."
