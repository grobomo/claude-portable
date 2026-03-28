#!/bin/bash
# Deploy the web-chat Lambda function.
# Creates or updates the function + function URL.
#
# Usage: bash deploy.sh [--token <auth-token>]
set -euo pipefail

FUNCTION_NAME="web-chat-api"
REGION="${AWS_DEFAULT_REGION:-us-east-2}"
RUNTIME="nodejs20.x"
HANDLER="index.handler"
TIMEOUT=300
MEMORY=256
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Parse args
TOKEN="${1:-}"
if [ "$TOKEN" = "--token" ]; then
  TOKEN="${2:?Usage: deploy.sh --token <token>}"
elif [ -z "$TOKEN" ]; then
  # Auto-generate
  TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(16))")
  echo "Generated token: $TOKEN"
fi

# Find or create IAM role
ROLE_NAME="web-chat-lambda-role"
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

  aws iam put-role-policy --role-name "$ROLE_NAME" \
    --policy-name ec2-describe \
    --policy-document '{
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Action": ["ec2:DescribeInstances"],
        "Resource": "*"
      }]
    }'

  echo "Waiting for IAM propagation..."
  sleep 10
fi

# Package
echo "Packaging..."
ZIP_PATH="/tmp/web-chat-lambda.zip"
rm -f "$ZIP_PATH"
if command -v zip &>/dev/null; then
  (cd "$SCRIPT_DIR" && zip -r "$ZIP_PATH" index.mjs ui.mjs)
else
  powershell.exe -Command "Compress-Archive -Path '$SCRIPT_DIR\\index.mjs','$SCRIPT_DIR\\ui.mjs' -DestinationPath '$(cygpath -w "$ZIP_PATH")' -Force"
fi

# Create or update
EXISTS=$(aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" 2>/dev/null && echo "yes" || echo "no")

if [ "$EXISTS" = "yes" ]; then
  echo "Updating function..."
  aws lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --zip-file "fileb://$ZIP_PATH" \
    --region "$REGION" --output text --query 'FunctionArn'

  aws lambda update-function-configuration \
    --function-name "$FUNCTION_NAME" \
    --environment "Variables={API_TOKEN=$TOKEN}" \
    --timeout "$TIMEOUT" \
    --memory-size "$MEMORY" \
    --region "$REGION" --output text --query 'FunctionArn' 2>/dev/null || true
else
  echo "Creating function..."
  aws lambda create-function \
    --function-name "$FUNCTION_NAME" \
    --runtime "$RUNTIME" \
    --handler "$HANDLER" \
    --role "$ROLE_ARN" \
    --zip-file "fileb://$ZIP_PATH" \
    --timeout "$TIMEOUT" \
    --memory-size "$MEMORY" \
    --environment "Variables={API_TOKEN=$TOKEN}" \
    --region "$REGION" --output text --query 'FunctionArn'

  # Create function URL
  FUNC_URL=$(aws lambda create-function-url-config \
    --function-name "$FUNCTION_NAME" \
    --auth-type NONE \
    --cors '{"AllowHeaders":["content-type","authorization"],"AllowMethods":["GET","POST"],"AllowOrigins":["*"]}' \
    --region "$REGION" --query 'FunctionUrl' --output text)

  aws lambda add-permission \
    --function-name "$FUNCTION_NAME" \
    --statement-id FunctionURLAllowPublicAccess \
    --action lambda:InvokeFunctionUrl \
    --principal "*" \
    --function-url-auth-type NONE \
    --region "$REGION" > /dev/null

  echo "Function URL: $FUNC_URL"
fi

# Get current URL
FUNC_URL=$(aws lambda get-function-url-config --function-name "$FUNCTION_NAME" --region "$REGION" --query 'FunctionUrl' --output text 2>/dev/null || echo "")

echo ""
echo "=== Deployed ==="
echo "Function: $FUNCTION_NAME"
echo "URL:      $FUNC_URL"
echo "Token:    $TOKEN"
echo ""
echo "Add to ccc.config.json:"
echo "  \"web_chat_lambda_url\": \"$FUNC_URL\""
