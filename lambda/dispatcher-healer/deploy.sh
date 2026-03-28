#!/bin/bash
# Deploy the dispatcher auto-healer Lambda.
# Subscribes to the SNS topic created by cloudformation/dispatcher.yaml.
#
# Usage:
#   bash deploy.sh <sns-topic-arn>
#
# The SNS topic ARN is in the CloudFormation stack outputs:
#   aws cloudformation describe-stacks --stack-name claude-dispatcher \
#     --query 'Stacks[0].Outputs[?OutputKey==`HeartbeatAlertTopicArn`].OutputValue' \
#     --output text
set -euo pipefail

FUNCTION_NAME="dispatcher-healer"
REGION="${AWS_DEFAULT_REGION:-us-east-2}"
RUNTIME="nodejs20.x"
HANDLER="index.handler"
TIMEOUT=120
MEMORY=128
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

SNS_TOPIC_ARN="${1:-}"
if [ -z "$SNS_TOPIC_ARN" ]; then
  echo "Usage: $0 <sns-topic-arn>"
  echo ""
  echo "Get the ARN from your dispatcher stack:"
  echo "  aws cloudformation describe-stacks --stack-name claude-dispatcher \\"
  echo "    --query 'Stacks[0].Outputs[?OutputKey==\`HeartbeatAlertTopicArn\`].OutputValue' \\"
  echo "    --output text"
  exit 1
fi

DISPATCHER_NAME="${DISPATCHER_NAME:-claude-dispatcher}"
LAUNCH_TEMPLATE_NAME="${LAUNCH_TEMPLATE_NAME:-claude-dispatcher-lt}"

# ── IAM role ──────────────────────────────────────────────────────────────────
ROLE_NAME="dispatcher-healer-lambda-role"
ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query 'Role.Arn' --output text 2>/dev/null || echo "")

if [ -z "$ROLE_ARN" ]; then
  echo "Creating IAM role: $ROLE_NAME"
  ROLE_ARN=$(aws iam create-role \
    --role-name "$ROLE_NAME" \
    --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "lambda.amazonaws.com"},
        "Action": "sts:AssumeRole"
      }]
    }' \
    --query 'Role.Arn' --output text)

  aws iam attach-role-policy --role-name "$ROLE_NAME" \
    --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"

  aws iam put-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-name dispatcher-ec2-heal \
    --policy-document '{
      "Version": "2012-10-17",
      "Statement": [
        {
          "Sid": "DescribeAll",
          "Effect": "Allow",
          "Action": [
            "ec2:DescribeInstances",
            "ec2:DescribeInstanceStatus",
            "ec2:DescribeLaunchTemplates",
            "ec2:DescribeLaunchTemplateVersions"
          ],
          "Resource": "*"
        },
        {
          "Sid": "ManageDispatcher",
          "Effect": "Allow",
          "Action": [
            "ec2:StartInstances",
            "ec2:RunInstances",
            "ec2:CreateTags"
          ],
          "Resource": "*",
          "Condition": {
            "StringEquals": {
              "aws:RequestTag/Project": "claude-portable"
            }
          }
        },
        {
          "Sid": "ManageTaggedDispatcher",
          "Effect": "Allow",
          "Action": [
            "ec2:StartInstances"
          ],
          "Resource": "*",
          "Condition": {
            "StringEquals": {
              "ec2:ResourceTag/Project": "claude-portable",
              "ec2:ResourceTag/Role": "dispatcher"
            }
          }
        }
      ]
    }'

  echo "Waiting for IAM propagation..."
  sleep 10
fi

# ── Package ───────────────────────────────────────────────────────────────────
echo "Packaging Lambda..."
ZIP_PATH="/tmp/dispatcher-healer-lambda.zip"
rm -f "$ZIP_PATH"
(cd "$SCRIPT_DIR" && zip -r "$ZIP_PATH" index.mjs)

# ── Create or update function ─────────────────────────────────────────────────
EXISTS=$(aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" 2>/dev/null && echo "yes" || echo "no")

ENV_VARS="Variables={DISPATCHER_NAME=${DISPATCHER_NAME},LAUNCH_TEMPLATE_NAME=${LAUNCH_TEMPLATE_NAME}}"

if [ "$EXISTS" = "yes" ]; then
  echo "Updating function code..."
  aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --zip-file "fileb://$ZIP_PATH" \
    --region "$REGION" --output text --query 'FunctionArn'

  echo "Updating function configuration..."
  aws lambda update-function-configuration \
    --function-name "$FUNCTION_NAME" \
    --environment "$ENV_VARS" \
    --timeout "$TIMEOUT" \
    --memory-size "$MEMORY" \
    --region "$REGION" --output text --query 'FunctionArn' 2>/dev/null || true
else
  echo "Creating function..."
  FUNC_ARN=$(aws lambda create-function \
    --function-name "$FUNCTION_NAME" \
    --runtime "$RUNTIME" \
    --handler "$HANDLER" \
    --role "$ROLE_ARN" \
    --zip-file "fileb://$ZIP_PATH" \
    --timeout "$TIMEOUT" \
    --memory-size "$MEMORY" \
    --environment "$ENV_VARS" \
    --region "$REGION" \
    --query 'FunctionArn' --output text)

  echo "Function ARN: $FUNC_ARN"
fi

# ── SNS subscription ──────────────────────────────────────────────────────────
FUNC_ARN=$(aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" \
  --query 'Configuration.FunctionArn' --output text)

# Allow SNS to invoke the function
ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)
aws lambda add-permission \
  --function-name "$FUNCTION_NAME" \
  --statement-id "AllowSNSInvoke" \
  --action "lambda:InvokeFunction" \
  --principal "sns.amazonaws.com" \
  --source-arn "$SNS_TOPIC_ARN" \
  --region "$REGION" 2>/dev/null || echo "(permission already exists)"

# Subscribe Lambda to the SNS topic
EXISTING_SUB=$(aws sns list-subscriptions-by-topic \
  --topic-arn "$SNS_TOPIC_ARN" \
  --query "Subscriptions[?Endpoint=='${FUNC_ARN}'].SubscriptionArn" \
  --output text 2>/dev/null || echo "")

if [ -z "$EXISTING_SUB" ] || [ "$EXISTING_SUB" = "None" ]; then
  echo "Subscribing Lambda to SNS topic..."
  aws sns subscribe \
    --topic-arn "$SNS_TOPIC_ARN" \
    --protocol lambda \
    --notification-endpoint "$FUNC_ARN"
else
  echo "Lambda already subscribed to SNS topic."
fi

echo ""
echo "=== Deployed ==="
echo "Function:       $FUNCTION_NAME"
echo "Function ARN:   $FUNC_ARN"
echo "SNS topic:      $SNS_TOPIC_ARN"
echo "Dispatcher:     $DISPATCHER_NAME"
echo "Launch template: $LAUNCH_TEMPLATE_NAME"
