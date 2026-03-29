---

name: clawdbot-deploy
description: Cost-optimized AWS deployment for Claude Code bots
keywords:
  - clawdbot
  - bot

---

# Clawdbot AWS Deployment Skill

Deploy a cost-optimized Clawdbot instance on AWS with Lambda-orchestrated EC2 Spot instances.

## Overview

This skill deploys Clawdbot with minimal cost by:
- Running EC2 only when needed (Lambda orchestration)
- Using Spot instances (~70% cheaper)
- Persisting state to S3 across sessions
- Auto-shutdown after idle period

**Estimated cost:** $2-8/month depending on usage

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Clawdbot Serverless Architecture             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ CloudWatch   │───>│ Orchestrator │───>│ EC2 Spot     │      │
│  │ Events       │    │ Lambda       │    │ t4g.micro    │      │
│  └──────────────┘    └──────────────┘    └──────────────┘      │
│        │                    │                   │               │
│        v                    v                   v               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │ Schedule:    │    │ Actions:     │    │ Clawdbot     │      │
│  │ - Start 7am  │    │ - start      │    │ Gateway      │      │
│  │ - Stop 11pm  │    │ - stop       │    │              │      │
│  │ - Idle check │    │ - status     │    └──────────────┘      │
│  └──────────────┘    └──────────────┘           │               │
│                             │                   v               │
│                      ┌──────────────┐    ┌──────────────┐      │
│                      │ S3 Bucket    │<──>│ Claude API   │      │
│                      │ (persist)    │    │ (Enterprise) │      │
│                      └──────────────┘    └──────────────┘      │
│                                                                 │
│  Add-ons (modular):                                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │ Signal   │ │ Teams    │ │ Discord  │ │ Telegram │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Deploy Base Infrastructure

**Option A: Quick Deploy Script (Recommended)**
```bash
# Auto-detects your IP, prompts for key pair
bash .claude/skills/clawdbot-deploy/scripts/deploy.sh --profile YOUR_PROFILE --region YOUR_REGION
```

**Option B: Manual CloudFormation**
```bash
# Get your current public IP
MY_IP=$(curl -s ifconfig.me)/32

# Deploy the base stack
aws cloudformation deploy \
  --template-file .claude/skills/clawdbot-deploy/cloudformation/clawdbot-base.yaml \
  --stack-name clawdbot \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    AllowedIP="$MY_IP" \
    KeyPairName="your-key" \
  --profile YOUR_PROFILE --region YOUR_REGION
```

### 2. Configure Claude Authentication

```bash
# On your local machine, generate setup token:
claude setup-token

# Get the EC2 instance IP (after it starts):
aws cloudformation describe-stacks --stack-name clawdbot \
  --query 'Stacks[0].Outputs[?OutputKey==`InstanceIP`].OutputValue' \
  --output text

# SSH and configure:
ssh -i ~/.aws/your-key.pem ec2-user@<IP>
sudo -u clawdbot clawdbot models auth paste-token --provider anthropic
```

### 3. (Optional) Add Signal Integration

```bash
# Deploy Signal add-on
aws cloudformation deploy \
  --template-file .claude/skills/clawdbot-deploy/cloudformation/addons/signal.yaml \
  --stack-name clawdbot-signal \
  --parameter-overrides \
    BaseStackName="clawdbot" \
    SignalPhoneNumber="+1XXXXXXXXXX" \
    AllowedSenders="+1YYYYYYYYYY,+1ZZZZZZZZZZ"
```

## Parameters

### Base Stack Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `AllowedIP` | (required) | Your public IP in CIDR format (e.g., 203.0.113.50/32) |
| `KeyPairName` | (required) | EC2 key pair for SSH |
| `InstanceType` | `t4g.micro` | EC2 instance type (ARM recommended for cost) |
| `UseSpotInstance` | `true` | Use Spot pricing (~70% cheaper) |
| `ActiveHoursStart` | `7` | Hour (UTC) to auto-start instance |
| `ActiveHoursEnd` | `23` | Hour (UTC) to auto-stop instance |
| `EnableScheduledStart` | `true` | Auto-start/stop on schedule |
| `IdleTimeoutMinutes` | `30` | Minutes of low CPU before auto-stop |
| `VpcId` | (auto) | VPC ID (uses default VPC if empty) |
| `SubnetId` | (auto) | Subnet ID (auto-selects public subnet if empty) |

**Get your IP:** `curl -s ifconfig.me && echo "/32"`

### Signal Add-on Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `BaseStackName` | `clawdbot` | Name of the base Clawdbot stack |
| `SignalPhoneNumber` | (required) | Phone number for Signal bot |
| `AllowedSenders` | (required) | Comma-separated phone numbers that can message the bot |

## Cost Breakdown

| Usage Pattern | EC2 Hours/Day | Monthly Cost |
|---------------|---------------|--------------|
| Always-on | 24 | ~$8 |
| Business hours (7am-11pm) | 16 | ~$5 |
| Active hours + idle shutdown | 4-8 | ~$2-3 |
| On-demand only | 1-2 | ~$1 |

*Costs assume t4g.micro Spot in us-east-2. S3 and Lambda costs are negligible (<$0.50/mo).*

## Managing the Instance

### Manual Control via Lambda

```bash
# Start instance
aws lambda invoke --function-name clawdbot-orchestrator \
  --payload '{"action": "start"}' /dev/stdout

# Stop instance
aws lambda invoke --function-name clawdbot-orchestrator \
  --payload '{"action": "stop"}' /dev/stdout

# Check status
aws lambda invoke --function-name clawdbot-orchestrator \
  --payload '{"action": "status"}' /dev/stdout
```

### SSH Access

```bash
# Get current IP (changes on each start)
aws cloudformation describe-stacks --stack-name clawdbot \
  --query 'Stacks[0].Outputs[?OutputKey==`InstanceIP`].OutputValue' \
  --output text

# SSH
ssh -i ~/.aws/your-key.pem ec2-user@<IP>

# Access Clawdbot TUI
sudo -u clawdbot clawdbot tui
```

## Files

```
clawdbot-deploy/
├── skill.md                      # This file
├── cloudformation/
│   ├── clawdbot-base.yaml        # Core infrastructure
│   └── addons/
│       ├── signal.yaml           # Signal messaging integration
│       └── teams.yaml            # Microsoft Teams (planned)
├── lambda/
│   └── orchestrator/
│       ├── index.py              # EC2 lifecycle management
│       └── requirements.txt      # Python dependencies
├── scripts/
│   ├── bootstrap.sh              # EC2 startup (sync from S3)
│   ├── shutdown.sh               # Graceful shutdown (sync to S3)
│   └── install-addon.sh          # Install integration dependencies
└── templates/
    └── clawdbot-config.json      # Default Clawdbot configuration
```

## Troubleshooting

### Instance won't start
```bash
# Check Lambda logs
aws logs tail /aws/lambda/clawdbot-orchestrator --follow

# Check Spot capacity (may need to try different AZ)
aws ec2 describe-spot-instance-requests \
  --filters "Name=state,Values=open,active,failed"
```

### Clawdbot not responding
```bash
# SSH and check service
ssh -i ~/.aws/your-key.pem ec2-user@<IP>
sudo systemctl status clawdbot
sudo journalctl -u clawdbot -f
```

### Signal not receiving messages
```bash
# Check signal-cli status
sudo -u clawdbot signal-cli -a +1XXXXXXXXXX receive --timeout 1

# Re-link if needed
sudo -u clawdbot signal-cli link -n "Clawdbot"
```

## Security Notes

1. **IP Restriction**: SSH and dashboard access restricted to specified IPs only
2. **No Public Ports**: Clawdbot dashboard only accessible via SSH tunnel
3. **Encrypted Storage**: S3 bucket uses server-side encryption
4. **IAM Least Privilege**: EC2 role only has access to its own S3 prefix
5. **Spot Interruption**: State syncs to S3 every 5 minutes + on shutdown signal

## Extending with Add-ons

Add-ons follow a standard pattern:

1. **CloudFormation template** in `addons/` that:
   - Takes `BaseStackName` parameter to import resources
   - Adds integration-specific IAM permissions if needed
   - Updates SSM parameter with addon config

2. **Install script** that runs on EC2:
   - Installs dependencies (e.g., signal-cli, Teams SDK)
   - Configures Clawdbot channel settings
   - Syncs config to S3

3. **S3 paths** for addon state:
   - `/integrations/<addon-name>/config.json`
   - `/integrations/<addon-name>/state/`

See `addons/signal.yaml` as a reference implementation.

## Claude Enterprise Token Setup

Clawdbot needs a Claude API token. For enterprise users, generate a setup token from an authenticated Claude Code installation:

### Generate Token (on your local machine)

```bash
# Ensure you're authenticated with Claude Code (enterprise)
claude --version

# Generate a setup token (valid for 24 hours)
claude setup-token
# Output: clawdbot:eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Apply Token (on EC2 instance)

```bash
# SSH to instance
ssh -i ~/.aws/your-key.pem ec2-user@<IP>

# Switch to clawdbot user and paste token
sudo -u clawdbot clawdbot models auth paste-token --provider anthropic
# Paste the token when prompted

# Verify
sudo -u clawdbot clawdbot models status
```

## Connect Claude Code to Remote Clawdbot

Use a hook to make Claude Code aware of your remote Clawdbot gateway. This allows you to reference the gateway in conversations.

### Setup Hook

```bash
# Get your Clawdbot gateway IP
GATEWAY_IP=$(aws lambda invoke --function-name clawdbot-orchestrator \
  --payload '{"action": "status"}' /tmp/out.json \
  --profile YOUR_PROFILE --region YOUR_REGION \
  && cat /tmp/out.json | jq -r '.public_ip')

# Run hook setup script
bash .claude/skills/clawdbot-deploy/scripts/setup-hook.sh "ws://${GATEWAY_IP}:18789"

# Restart Claude Code to apply
```

### Manual Hook Setup

Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "CLAWDBOT_GATEWAY_URL=ws://YOUR_IP:18789 python ~/.claude/hooks/clawdbot-gateway-hook.py"
          }
        ]
      }
    ]
  }
}
```

### What the Hook Does

When you mention "clawdbot", "gateway", "remote claude", "bot", "signal", or "message", the hook injects:
- Gateway WebSocket URL
- Authentication status
- Available Clawdbot commands

## Publishing to Custom Marketplace

### Option 1: Git-based Distribution

Share the skill via a git repository:

```bash
# Create a standalone skill repo
mkdir clawdbot-deploy-skill
cp -r .claude/skills/clawdbot-deploy/* clawdbot-deploy-skill/
cd clawdbot-deploy-skill
git init
git add .
git commit -m "Initial clawdbot-deploy skill"
git remote add origin https://github.com/YOUR_ORG/clawdbot-deploy-skill.git
git push -u origin main
```

Users install via:
```bash
git clone https://github.com/YOUR_ORG/clawdbot-deploy-skill.git .claude/skills/clawdbot-deploy
```

### Option 2: NPM Package (Advanced)

Package as an npm module for easier distribution:

```bash
# Create package.json in skill directory
cat > .claude/skills/clawdbot-deploy/package.json << 'EOF'
{
  "name": "@your-org/clawdbot-deploy-skill",
  "version": "1.0.0",
  "description": "Clawdbot AWS deployment skill for Claude Code",
  "main": "skill.md",
  "files": [
    "skill.md",
    "cloudformation/",
    "lambda/",
    "scripts/",
    "hooks/",
    "templates/"
  ],
  "keywords": ["claude", "clawdbot", "aws", "skill"],
  "author": "Your Name",
  "license": "MIT"
}
EOF

# Publish
npm publish --access public
```

Users install via:
```bash
npm install @your-org/clawdbot-deploy-skill --prefix .claude/skills/clawdbot-deploy
```

### Option 3: Enterprise Skill Registry

For enterprise deployments, host skills in a central location:

1. **Create S3 bucket** for skill artifacts
2. **Upload skill zip** to S3
3. **Create skill manifest** with version info
4. **Distribute via internal tooling**

Example manifest (`skills-registry.json`):
```json
{
  "skills": {
    "clawdbot-deploy": {
      "version": "1.0.0",
      "description": "Deploy Clawdbot on AWS with Lambda orchestration",
      "source": "s3://your-skills-bucket/clawdbot-deploy-v1.0.0.zip",
      "sha256": "abc123..."
    }
  }
}
```

## Files

```
clawdbot-deploy/
├── skill.md                      # This file
├── cloudformation/
│   ├── clawdbot-base.yaml        # Core infrastructure
│   └── addons/
│       ├── signal.yaml           # Signal messaging integration
│       └── teams.yaml            # Microsoft Teams (planned)
├── lambda/
│   └── orchestrator/
│       ├── index.py              # EC2 lifecycle management
│       └── requirements.txt      # Python dependencies
├── scripts/
│   ├── deploy.sh                 # Quick deploy with IP detection
│   ├── bootstrap.sh              # EC2 startup (sync from S3)
│   ├── shutdown.sh               # Graceful shutdown (sync to S3)
│   ├── install-addon.sh          # Install integration dependencies
│   └── setup-hook.sh             # Configure Claude Code hook
├── hooks/
│   └── clawdbot-gateway-hook.py  # Hook to inject gateway context
└── templates/
    └── clawdbot-config.json      # Default Clawdbot configuration
```
