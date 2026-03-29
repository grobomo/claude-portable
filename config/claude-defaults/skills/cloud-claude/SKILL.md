---

name: cloud-claude
description: Launch Claude Code on AWS EC2 spot instances. Auto-provisions everything -- SSH keys, security groups, Docker container with Chrome and MCP servers. Multi-instance support with inter-instance messaging.
keywords:
  - cloud
  - ec2
  - spot
  - remote
  - portable
  - aws
  - cloud-claude
  - launch
  - instance
  - server

---

# Cloud Claude

Launch Claude Code on AWS EC2 spot instances. Fully automated.

## When to Use

Trigger on: "launch cloud claude", "cloud instance", "spin up ec2", "remote claude", "/cloud-claude", "cloud-claude"

## What Claude Does (ALL AUTOMATIC -- DO NOT ASK USER TO DO THESE)

### 1. Verify Prerequisites

```bash
aws sts get-caller-identity --query Account --output text
git --version
```

If AWS CLI fails: tell user to run `aws configure` first. That's the only manual step.

### 2. Find or Clone the Repo

Look for `claude-portable` in the user's projects directory. If not found:

```bash
git clone https://github.com/grobomo/claude-portable.git "$HOME/claude-portable"
```

Set `PROJ_DIR` to wherever it ends up.

### 3. Create SSH Key Pair (if needed)

```bash
KEY_NAME="claude-portable-key"
if ! aws ec2 describe-key-pairs --key-names "$KEY_NAME" 2>/dev/null; then
  mkdir -p "$HOME/.ssh"
  aws ec2 create-key-pair --key-name "$KEY_NAME" --query 'KeyMaterial' --output text > "$HOME/.ssh/claude-portable.pem"
  chmod 600 "$HOME/.ssh/claude-portable.pem"
fi
```

Also find where the .pem file is (check `$HOME/.ssh/`, `$HOME/archive/.ssh/`, etc).

### 4. Detect Auth Method and Write .env

**Check in order:**

1. **ANTHROPIC_API_KEY env var** -- if set, use API key mode
2. **Claude credentials file** -- check these paths:
   - `$HOME/.claude/.credentials.json` (Linux/Mac)
   - `$USERPROFILE/.claude/.credentials.json` (Windows, via Git Bash)
   - `$APPDATA/../.claude/.credentials.json` (Windows alternative)
   If file exists and has `claudeAiOauth.accessToken`, use OAuth mode
3. **Neither found** -- ask user: "Do you have an Anthropic API key, or are you on Claude Enterprise/Max?"
   - API key: ask them to paste it
   - Enterprise: ask them to run `claude` locally first to generate OAuth tokens

**Write .env:**

For API key mode:
```bash
cat > "$PROJ_DIR/.env" << EOF
ANTHROPIC_API_KEY=<the-key>
REPO_URL=https://github.com/grobomo/claude-portable.git
EOF
```

For OAuth mode:
```bash
CREDS_FILE=<detected-path-to-.credentials.json>
ACCESS_TOKEN=$(python3 -c "import json; print(json.load(open('$CREDS_FILE'))['claudeAiOauth']['accessToken'])")
REFRESH_TOKEN=$(python3 -c "import json; print(json.load(open('$CREDS_FILE'))['claudeAiOauth']['refreshToken'])")
EXPIRES_AT=$(python3 -c "import json; print(json.load(open('$CREDS_FILE'))['claudeAiOauth']['expiresAt'])")
GH_TOKEN=$(gh auth token 2>/dev/null || echo "none")

cat > "$PROJ_DIR/.env" << EOF
CLAUDE_OAUTH_ACCESS_TOKEN=$ACCESS_TOKEN
CLAUDE_OAUTH_REFRESH_TOKEN=$REFRESH_TOKEN
CLAUDE_OAUTH_EXPIRES_AT=$EXPIRES_AT
GITHUB_TOKEN=$GH_TOKEN
REPO_URL=https://github.com/grobomo/claude-portable.git
EOF
```

### 5. Launch

```bash
cd "$PROJ_DIR"
bash run.sh --name <name>
```

Use `--name` from user request, or default to something like "dev" or "box1".

### 6. Wait for Container

The CF stack takes ~2-3 min, then Docker builds ~2-3 min more. Poll:

```bash
SSH_KEY="$HOME/.ssh/claude-portable.pem"
IP=$(aws cloudformation describe-stacks --stack-name "claude-portable-<name>" \
  --query "Stacks[0].Outputs[?OutputKey=='PublicIP'].OutputValue" --output text)

for i in $(seq 1 30); do
  STATUS=$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -i "$SSH_KEY" ubuntu@$IP \
    "docker ps --filter name=claude-portable --format '{{.Status}}'" 2>/dev/null || echo "")
  if [[ "$STATUS" == Up* ]]; then break; fi
  sleep 10
done
```

### 7. Push Fresh Credentials

**OAuth mode only** (API key is baked into .env at build time):

```bash
CREDS=$(cat "$CREDS_FILE")
ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" ubuntu@$IP \
  "docker exec claude-portable bash -c 'cat > /home/claude/.claude/.credentials.json << CREDEOF
$CREDS
CREDEOF'"
```

### 8. Set Trusted Directories

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

Detect platform and open appropriately:

**Windows Terminal:**
```bash
wt.exe -w 0 new-tab --title "<name> ($IP)" ssh -o StrictHostKeyChecking=no -i "$SSH_KEY" ubuntu@$IP -t "docker exec -it claude-portable claude"
```

**macOS:**
```bash
osascript -e "tell application \"Terminal\" to do script \"ssh -o StrictHostKeyChecking=no -i $SSH_KEY ubuntu@$IP -t 'docker exec -it claude-portable claude'\""
```

**Linux / fallback:** print the command:
```
ssh -i ~/.ssh/claude-portable.pem ubuntu@<IP> -t 'docker exec -it claude-portable claude'
```

## Management Commands

**"list cloud instances":**
```bash
cd "$PROJ_DIR" && bash list.sh
```

**"terminate <name>" / "kill all cloud instances":**
```bash
cd "$PROJ_DIR" && bash terminate.sh --name <name>
cd "$PROJ_DIR" && bash terminate.sh --all
```

**"push updates to cloud":**
```bash
cd "$PROJ_DIR" && bash push.sh --all
```

**"refresh tokens on cloud instances":**
Read fresh tokens from local credentials file, push to each running instance via SSH.
