# Claude Portable

Run Claude Code on AWS EC2 spot instances. Docker container with Chrome, headless browser automation, session logging, and inter-instance messaging. ~$0.03/hr.

---

## Quickstart

**Tell Claude:** "set up claude portable" or "launch a cloud claude instance"

Claude reads this README and does everything below automatically. You should not need to run any commands yourself.

---

## How It Works

1. Claude clones this repo to your projects directory
2. Claude detects your auth method (API key or OAuth) and extracts tokens
3. Claude creates an AWS SSH key pair if you don't have one
4. Claude writes the `.env` config file
5. Claude launches a spot EC2 instance via CloudFormation
6. Claude waits for the Docker container to finish building
7. Claude pushes fresh credentials into the container
8. Claude opens a terminal tab with Claude Code running on the instance

Total time: ~7 minutes. Cost: ~$0.03/hr (t3.large spot).

---

## Prerequisites

Claude will check for these and tell you what's missing.

| Tool | What For | Install |
|------|----------|---------|
| AWS CLI | Launching EC2 instances | [aws.amazon.com/cli](https://aws.amazon.com/cli/) |
| Git | Cloning this repo | [git-scm.com](https://git-scm.com/) |

AWS CLI must be configured with credentials and a default region:

```
aws configure
```

---

## Authentication

Claude Portable supports two auth methods. Claude will auto-detect which one you're using.

### Option A: Anthropic API Key (Individual / Teams)

If you have an API key from [console.anthropic.com](https://console.anthropic.com/):

- Claude sets `ANTHROPIC_API_KEY` in the container
- No OAuth tokens needed
- Key does not expire

How to get one: Go to console.anthropic.com > API Keys > Create Key.

### Option B: Claude OAuth Token (Enterprise / Claude Max)

If you're on an enterprise plan or Claude Max and logged into Claude Code locally:

- Claude reads your tokens from the local credentials file (located in the Claude config directory under `.credentials.json`)
- Tokens include `accessToken` and `refreshToken`
- Tokens expire every ~5-6 hours but auto-refresh locally
- Claude pushes fresh tokens to the container at launch

**No action needed** -- Claude extracts these automatically from your running Claude Code session.

### How Claude Detects Your Auth

1. Check for `ANTHROPIC_API_KEY` environment variable -- if set, use API key mode
2. Check the Claude config directory for `.credentials.json` -- if present with `claudeAiOauth`, use OAuth mode
3. If neither found, ask the user which method they want to use

---

## Setup (Claude Does This)

When you say "set up claude portable", Claude will:

### 1. Verify Prerequisites

```bash
# Check AWS CLI
aws sts get-caller-identity

# Check git
git --version
```

If either fails, Claude tells you what to install.

### 2. Clone the Repo

Clone into the user's projects directory (detect from context or use home directory):

```bash
git clone https://github.com/grobomo/claude-portable.git
cd claude-portable
```

### 3. Create SSH Key Pair (if needed)

```bash
KEY_NAME="claude-portable-key"
if ! aws ec2 describe-key-pairs --key-names "$KEY_NAME" 2>/dev/null; then
  mkdir -p "$HOME/.ssh"
  aws ec2 create-key-pair \
    --key-name "$KEY_NAME" \
    --query 'KeyMaterial' \
    --output text > "$HOME/.ssh/claude-portable.pem"
  chmod 600 "$HOME/.ssh/claude-portable.pem"
fi
```

### 4. Write .env

Detect auth method and write the config:

**API Key mode:**
```bash
cat > .env << 'EOF'
ANTHROPIC_API_KEY=<from-env-or-ask-user>
REPO_URL=https://github.com/grobomo/claude-portable.git
EOF
```

**OAuth mode:**
```bash
# Read from Claude config directory
CREDS_FILE="$HOME/.claude/.credentials.json"  # Linux/Mac
# On Windows Git Bash: CREDS_FILE="$APPDATA/../.claude/.credentials.json" or similar

ACCESS_TOKEN=$(python3 -c "import json; print(json.load(open('$CREDS_FILE'))['claudeAiOauth']['accessToken'])")
REFRESH_TOKEN=$(python3 -c "import json; print(json.load(open('$CREDS_FILE'))['claudeAiOauth']['refreshToken'])")
EXPIRES_AT=$(python3 -c "import json; print(json.load(open('$CREDS_FILE'))['claudeAiOauth']['expiresAt'])")

cat > .env << EOF
CLAUDE_OAUTH_ACCESS_TOKEN=$ACCESS_TOKEN
CLAUDE_OAUTH_REFRESH_TOKEN=$REFRESH_TOKEN
CLAUDE_OAUTH_EXPIRES_AT=$EXPIRES_AT
GITHUB_TOKEN=$(gh auth token 2>/dev/null || echo "")
REPO_URL=https://github.com/grobomo/claude-portable.git
EOF
```

> Note: `GITHUB_TOKEN` is only required if the repo is private or if you want private component repos pulled at startup. For the public repo, it can be blank -- but CloudFormation currently validates it. If the user has `gh` CLI, use `gh auth token`. Otherwise set it to any non-empty placeholder for public-only usage.

### 5. Launch

```bash
./run.sh --name <instance-name>
```

### 6. Wait for Container

After the CF stack creates (~2-3 min), the Docker image builds on the instance (~2-3 min more). Poll until ready:

```bash
SSH_KEY="$HOME/.ssh/claude-portable.pem"
IP=$(aws cloudformation describe-stacks --stack-name "claude-portable-<name>" \
  --query "Stacks[0].Outputs[?OutputKey=='PublicIP'].OutputValue" --output text)

# Poll until container is running
for i in $(seq 1 30); do
  STATUS=$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -i "$SSH_KEY" ubuntu@$IP \
    "docker ps --filter name=claude-portable --format '{{.Status}}'" 2>/dev/null || echo "")
  if [[ "$STATUS" == Up* ]]; then break; fi
  sleep 10
done
```

### 7. Push Fresh Credentials

**OAuth mode:** push current tokens directly to the container:

```bash
CREDS=$(cat "$CREDS_FILE")
ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" ubuntu@$IP \
  "docker exec claude-portable bash -c 'cat > /home/claude/.claude/.credentials.json' << CREDEOF
$CREDS
CREDEOF"
```

**API key mode:** set the env var in the container:

```bash
ssh -i "$SSH_KEY" ubuntu@$IP \
  "docker exec claude-portable bash -c 'echo export ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY >> /home/claude/.bashrc'"
```

### 8. Set Up Trusted Directories

```bash
ssh -i "$SSH_KEY" ubuntu@$IP 'docker exec -u root claude-portable python3 << PYEOF
import json
p = "/home/claude/.claude/settings.local.json"
try: d = json.load(open(p))
except: d = {}
d["trustedDirectories"] = ["/workspace", "/home/claude", "/tmp"]
d["hasCompletedOnboarding"] = True
json.dump(d, open(p, "w"), indent=2)
PYEOF'
```

### 9. Open Terminal Tab

**Windows Terminal:**
```bash
wt.exe -w 0 new-tab --title "<name> ($IP)" ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" ubuntu@$IP -t "docker exec -it claude-portable claude"
```

**macOS Terminal.app:**
```bash
osascript -e "tell application \"Terminal\" to do script \"ssh -o StrictHostKeyChecking=no -i $SSH_KEY ubuntu@$IP -t 'docker exec -it claude-portable claude'\""
```

**Linux / fallback:** Print the SSH command for the user:
```
Connect: ssh -i ~/.ssh/claude-portable.pem ubuntu@<IP> -t 'docker exec -it claude-portable claude'
```

---

## Multiple Instances

```bash
./run.sh --name dev
./run.sh --name research
./run.sh --name lab
```

List all:
```bash
./list.sh
```

Terminate:
```bash
./terminate.sh --name dev
./terminate.sh --all
```

---

## Inter-Instance Messaging

Instances communicate through an S3 mailbox (auto-created from your AWS account ID).

### Setup

For each instance, deploy the `msg` script and AWS credentials:

```bash
# Push msg script
./push.sh scripts/msg.sh

# Then for each instance, SSH in and configure identity + AWS creds
SSH_KEY="$HOME/.ssh/claude-portable.pem"
AWS_AK=$(aws configure get aws_access_key_id)
AWS_SK=$(aws configure get aws_secret_access_key)
AWS_RG=$(aws configure get region)

# Per instance (get IP from ./list.sh):
ssh -i "$SSH_KEY" ubuntu@<IP> "docker exec claude-portable bash -c 'echo export CLAUDE_PORTABLE_ID=<name> >> /home/claude/.bashrc'"
ssh -i "$SSH_KEY" ubuntu@<IP> "docker exec claude-portable bash -c 'mkdir -p /home/claude/.aws && printf \"[default]\naws_access_key_id = $AWS_AK\naws_secret_access_key = $AWS_SK\nregion = $AWS_RG\n\" > /home/claude/.aws/credentials'"
```

### Usage

Inside any instance (Claude runs these via bash):

```bash
msg send research "Can you look up the average rainfall in Seattle?"
msg inbox
msg who
msg history
msg ack <message-id>
```

Tell Claude on one instance: "Send a message to research asking about X" -- Claude runs `msg send` automatically.

---

## Push Updates

Edit files locally and push to running instances without restarting:

```bash
./push.sh scripts/msg.sh              # one file to all instances
./push.sh scripts/msg.sh --name dev   # one file to one instance
./push.sh --all                       # all scripts + config to all instances
```

---

## Refreshing Expired Tokens

OAuth tokens expire every ~5-6 hours. If Claude on an instance reports auth errors:

**Tell your local Claude:** "refresh tokens on my cloud instances"

Claude reads fresh tokens from your local credentials file and pushes them to all running instances.

---

## What's in the Container

| Component | Details |
|-----------|---------|
| Claude Code CLI | latest (npm global) |
| Node.js | 20 LTS |
| Google Chrome | stable + Xvfb (headless) |
| Python 3 | system |
| AWS CLI v2 | for S3, CloudFormation, etc. |
| GitHub CLI | for repo operations |

---

## Cost

| Instance | Spot $/hr | 8hr Day |
|----------|----------|---------|
| t3.medium (4GB) | ~$0.01 | ~$0.10 |
| **t3.large (8GB)** | **~$0.03** | **~$0.24** |
| t3.xlarge (16GB) | ~$0.07 | ~$0.54 |

Change type: `./run.sh --name dev --instance-type t3.xlarge`

---

## Customization

### Custom Components

Edit `components.yaml` to pull your own repos into the container:

```yaml
- name: my-mcp-server
  repo: your-org/my-mcp-server
  type: mcp
  target: /opt/mcp/my-mcp-server
  enabled: true
  visibility: public
```

### Custom Region

```bash
./run.sh --name dev --region us-west-2
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "OAuth token has expired" | Push fresh tokens (see Refreshing Expired Tokens) |
| Stack creation fails | `aws cloudformation describe-stack-events --stack-name claude-portable-<name>` -- usually spot capacity; try another region |
| Container won't start | SSH to host: `ssh -i ~/.ssh/claude-portable.pem ubuntu@<IP> 'docker logs claude-portable'` |
| `file://` path error (Windows) | Run from Git Bash, not PowerShell |
| Spot instance terminated | Relaunch: `./run.sh --name <name>` |

---

## License

MIT
