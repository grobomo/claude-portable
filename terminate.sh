#!/bin/bash
# Terminate a Claude Portable instance by stack name or --all.
# Usage: ./terminate.sh <stack-name|--name LABEL|--all>
set -euo pipefail

AWS_PROFILE="${CLAUDE_PORTABLE_AWS_PROFILE:-default}"
AWS_REGION="${CLAUDE_PORTABLE_AWS_REGION:-us-east-2}"
TARGET=""
ALL=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) AWS_PROFILE="$2"; shift 2 ;;
    --region) AWS_REGION="$2"; shift 2 ;;
    --name) TARGET="claude-portable-$2"; shift 2 ;;
    --all) ALL=true; shift ;;
    --help|-h)
      echo "Usage: ./terminate.sh [--name LABEL | --all | STACK_NAME]"
      echo "  --name LABEL   Terminate claude-portable-LABEL"
      echo "  --all          Terminate ALL claude-portable stacks"
      echo "  STACK_NAME     Terminate specific stack by full name"
      exit 0 ;;
    *) TARGET="$1"; shift ;;
  esac
done

if [ "$ALL" = true ]; then
  STACKS=$(aws cloudformation list-stacks \
    --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE CREATE_IN_PROGRESS \
    --profile "$AWS_PROFILE" --region "$AWS_REGION" \
    --query "StackSummaries[?starts_with(StackName, 'claude-portable')].StackName" \
    --output text 2>/dev/null)

  if [ -z "$STACKS" ]; then
    echo "No claude-portable stacks found."
    exit 0
  fi

  echo "Terminating ALL claude-portable stacks:"
  for STACK in $STACKS; do
    echo "  Deleting $STACK..."
    aws cloudformation delete-stack --stack-name "$STACK" \
      --profile "$AWS_PROFILE" --region "$AWS_REGION"
  done
  echo "Done. Stacks deleting in background."
elif [ -n "$TARGET" ]; then
  echo "Deleting stack: $TARGET"
  aws cloudformation delete-stack --stack-name "$TARGET" \
    --profile "$AWS_PROFILE" --region "$AWS_REGION"
  echo "Done. Stack deleting in background."
else
  echo "Usage: ./terminate.sh [--name LABEL | --all | STACK_NAME]"
  exit 1
fi
