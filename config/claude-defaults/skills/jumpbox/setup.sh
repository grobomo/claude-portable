#!/bin/bash
# jumpbox setup -- create a Windows EC2 jumpbox from scratch
# Installs Chrome, Git Bash, sets timezone, enables SSM
# Usage: bash setup.sh [--name NAME] [--region REGION] [--type TYPE] [--timezone TZ]
set -euo pipefail

NAME="${JUMPBOX_NAME:-jumpbox}"
REGION="${AWS_DEFAULT_REGION:-us-east-2}"
INSTANCE_TYPE="t3.large"
DISK_SIZE=50
TIMEZONE="Central Standard Time"
CONFIG_DIR="$HOME/.jumpbox"

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --name) NAME="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --type) INSTANCE_TYPE="$2"; shift 2 ;;
    --timezone) TIMEZONE="$2"; shift 2 ;;
    *) shift ;;
  esac
done

mkdir -p "$CONFIG_DIR"
echo "=== Jumpbox Setup: $NAME ==="

# ── 1. Find latest Windows Server 2022 AMI ──────────────────────────────────
echo "[1/7] Finding Windows Server 2022 AMI..."
AMI_ID=$(aws ec2 describe-images --owners amazon --region "$REGION" \
  --filters "Name=name,Values=Windows_Server-2022-English-Full-Base-*" "Name=architecture,Values=x86_64" \
  --query "Images | sort_by(@, &CreationDate) | [-1].ImageId" --output text)
echo "  AMI: $AMI_ID"

# ── 2. Security group ───────────────────────────────────────────────────────
echo "[2/7] Security group..."
SG_NAME="${NAME}-rdp-sg"
SG_ID=$(aws ec2 describe-security-groups --region "$REGION" \
  --filters "Name=group-name,Values=$SG_NAME" \
  --query "SecurityGroups[0].GroupId" --output text 2>/dev/null)

if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
  SG_ID=$(aws ec2 create-security-group --region "$REGION" \
    --group-name "$SG_NAME" --description "Jumpbox RDP access" \
    --query GroupId --output text)
  aws ec2 authorize-security-group-ingress --region "$REGION" \
    --group-id "$SG_ID" --protocol tcp --port 3389 --cidr 0.0.0.0/0
  echo "  Created: $SG_ID"
else
  echo "  Exists: $SG_ID"
fi

# ── 3. SSH key pair ──────────────────────────────────────────────────────────
echo "[3/7] SSH key pair..."
KEY_NAME="${NAME}-key"
KEY_DIR="$HOME/.ssh/jumpbox-keys"
KEY_PATH="$KEY_DIR/${NAME}.pem"
mkdir -p "$KEY_DIR"

EXISTING_KEY=$(aws ec2 describe-key-pairs --region "$REGION" \
  --key-names "$KEY_NAME" --query "KeyPairs[0].KeyName" --output text 2>/dev/null || echo "")

if [ -n "$EXISTING_KEY" ] && [ "$EXISTING_KEY" != "None" ] && [ -f "$KEY_PATH" ]; then
  echo "  Reusing: $KEY_NAME"
else
  aws ec2 delete-key-pair --region "$REGION" --key-name "$KEY_NAME" 2>/dev/null || true
  MATERIAL=$(aws ec2 create-key-pair --region "$REGION" \
    --key-name "$KEY_NAME" --key-type rsa \
    --query KeyMaterial --output text)
  echo "$MATERIAL" > "$KEY_PATH"
  chmod 600 "$KEY_PATH" 2>/dev/null || true
  echo "  Created: $KEY_PATH"
fi

# ── 4. IAM role for SSM ─────────────────────────────────────────────────────
echo "[4/7] IAM role for SSM..."
ROLE_NAME="${NAME}-ssm-role"
PROFILE_NAME="${NAME}-ssm-profile"

if ! aws iam get-role --role-name "$ROLE_NAME" &>/dev/null; then
  aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}' > /dev/null
  aws iam attach-role-policy --role-name "$ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
  echo "  Created role: $ROLE_NAME"
else
  echo "  Role exists: $ROLE_NAME"
fi

if ! aws iam get-instance-profile --instance-profile-name "$PROFILE_NAME" &>/dev/null; then
  aws iam create-instance-profile --instance-profile-name "$PROFILE_NAME" > /dev/null
  aws iam add-role-to-instance-profile --instance-profile-name "$PROFILE_NAME" --role-name "$ROLE_NAME"
  echo "  Created profile: $PROFILE_NAME"
  echo "  Waiting for IAM propagation..."
  sleep 15
else
  echo "  Profile exists: $PROFILE_NAME"
fi

# ── 5. Launch instance ───────────────────────────────────────────────────────
echo "[5/7] Launching instance..."
INSTANCE_ID=$(aws ec2 run-instances --region "$REGION" \
  --image-id "$AMI_ID" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" \
  --iam-instance-profile "Name=$PROFILE_NAME" \
  --block-device-mappings "[{\"DeviceName\":\"/dev/sda1\",\"Ebs\":{\"VolumeSize\":$DISK_SIZE,\"VolumeType\":\"gp3\",\"Encrypted\":true}}]" \
  --tag-specifications "[{\"ResourceType\":\"instance\",\"Tags\":[{\"Key\":\"Name\",\"Value\":\"$NAME\"},{\"Key\":\"Project\",\"Value\":\"jumpbox\"},{\"Key\":\"no-delete\",\"Value\":\"true\"}]}]" \
  --instance-initiated-shutdown-behavior stop \
  --metadata-options '{"HttpTokens":"required","HttpEndpoint":"enabled"}' \
  --query "Instances[0].InstanceId" --output text)

echo "  Instance: $INSTANCE_ID"
echo "  Waiting for running state..."
aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"

IP=$(aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" \
  --query "Reservations[0].Instances[0].PublicIpAddress" --output text)
echo "  IP: $IP"

# ── 6. Wait for SSM + install software ───────────────────────────────────────
echo "[6/7] Waiting for SSM agent..."
for i in $(seq 1 30); do
  STATUS=$(aws ssm describe-instance-information --region "$REGION" \
    --filters "Key=InstanceIds,Values=$INSTANCE_ID" \
    --query "InstanceInformationList[0].PingStatus" --output text 2>/dev/null)
  if [ "$STATUS" = "Online" ]; then echo "  SSM Online"; break; fi
  echo -n "."
  sleep 10
done
echo ""

echo "  Installing Chrome, Git Bash, setting timezone..."
CMD_ID=$(aws ssm send-command --region "$REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunPowerShellScript" \
  --parameters "commands=[
    \"Set-TimeZone -Id '$TIMEZONE'\",
    \"Write-Output 'Timezone: $TIMEZONE'\",
    \"\\\$ProgressPreference = 'SilentlyContinue'\",
    \"Invoke-WebRequest -Uri 'https://dl.google.com/chrome/install/GoogleChromeStandaloneEnterprise64.msi' -OutFile \\\"\\\$env:TEMP\\\\chrome.msi\\\"\",
    \"Start-Process msiexec.exe -ArgumentList '/i \\\"\\\$env:TEMP\\\\chrome.msi\\\" /qn' -Wait\",
    \"Remove-Item \\\"\\\$env:TEMP\\\\chrome.msi\\\" -ErrorAction SilentlyContinue\",
    \"Write-Output 'Chrome installed'\",
    \"Invoke-WebRequest -Uri 'https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.2/Git-2.47.1.2-64-bit.exe' -OutFile \\\"\\\$env:TEMP\\\\git.exe\\\"\",
    \"Start-Process \\\"\\\$env:TEMP\\\\git.exe\\\" -ArgumentList '/VERYSILENT /NORESTART' -Wait\",
    \"Remove-Item \\\"\\\$env:TEMP\\\\git.exe\\\" -ErrorAction SilentlyContinue\",
    \"Write-Output 'Git Bash installed'\",
    \"Write-Output 'Installing Python 3.12...'\",
    \"Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe' -OutFile \\\"\\\$env:TEMP\\\\python.exe\\\"\",
    \"Start-Process \\\"\\\$env:TEMP\\\\python.exe\\\" -ArgumentList '/quiet InstallAllUsers=1 PrependPath=1 TargetDir=C:\\\\Python312' -Wait\",
    \"\\\$path = [Environment]::GetEnvironmentVariable('PATH','Machine')\",
    \"[Environment]::SetEnvironmentVariable('PATH','C:\\\\Python312;C:\\\\Python312\\\\Scripts;' + \\\$path,'Machine')\",
    \"Remove-Item \\\"\\\$env:TEMP\\\\python.exe\\\" -ErrorAction SilentlyContinue\",
    \"Write-Output 'Python installed'\",
    \"Write-Output 'Done'\"
  ]" \
  --timeout-seconds 600 \
  --query "Command.CommandId" --output text)

# Wait for install
for i in $(seq 1 60); do
  S=$(aws ssm get-command-invocation --region "$REGION" \
    --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" \
    --query "Status" --output text 2>/dev/null || echo "Pending")
  if [ "$S" = "Success" ]; then
    echo "  Software installed."
    break
  elif [ "$S" = "Failed" ]; then
    echo "  WARNING: Install may have partially failed."
    aws ssm get-command-invocation --region "$REGION" \
      --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" \
      --query "StandardErrorContent" --output text 2>/dev/null
    break
  fi
  echo -n "."
  sleep 5
done
echo ""

# ── 7. Save config ───────────────────────────────────────────────────────────
echo "[7/7] Saving config..."
cat > "$CONFIG_DIR/${NAME}.json" << CFGEOF
{
  "name": "$NAME",
  "instance_id": "$INSTANCE_ID",
  "region": "$REGION",
  "key_path": "$KEY_PATH",
  "instance_type": "$INSTANCE_TYPE",
  "timezone": "$TIMEZONE",
  "created": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
CFGEOF

echo ""
echo "=== Jumpbox Ready ==="
echo "  Name:     $NAME"
echo "  Instance: $INSTANCE_ID"
echo "  IP:       $IP"
echo "  Config:   $CONFIG_DIR/${NAME}.json"
echo ""
echo "  Connect:  jumpbox"
echo "  Stop:     jumpbox stop"
