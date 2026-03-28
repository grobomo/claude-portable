# Claude Portable

Run Claude Code on AWS EC2. Chrome, VNC, MCP servers, session persistence. ~$0.08/hr, auto-stops when idle.

## Setup (one command)

```bash
bash <(curl -sL https://raw.githubusercontent.com/grobomo/claude-portable/main/install.sh)
```

The installer walks you through everything:
1. Checks/installs Git, Python, AWS CLI
2. Prompts for AWS credentials (if not already configured)
3. Clones the repo
4. Prompts for your **Anthropic API key** (from RDSEC portal) or auto-detects **OAuth tokens** from local Claude Code
5. Auto-detects **GitHub token** from `gh` CLI (or prompts)
6. Adds the `ccc` command to your PATH

**Have everything ready?** The whole thing takes ~2 minutes.

### What you'll need

| Item | Where to get it |
|------|----------------|
| AWS Access Key | AWS Console > IAM > Security credentials > Create access key |
| Anthropic API key | RDSEC portal > Claude API > Generate Key |
| GitHub token | Already have `gh` CLI? Auto-detected. Otherwise: github.com/settings/tokens |

## Launch

```bash
ccc --name dev
```

First launch: ~5-7 min (builds Docker on EC2). After that, stopped instances resume in ~30 sec.

## Usage

```bash
ccc --name dev         # Connect (starts if stopped)
ccc list               # List instances
ccc vnc                # Open Chrome via VNC
ccc scp file.txt       # Copy file to instance
ccc stop dev           # Stop ($0/hr while stopped)
ccc kill dev           # Destroy permanently
```

## What's included

- Claude Code CLI (latest)
- Google Chrome + VNC
- AWS CLI, GitHub CLI, Python 3
- S3 conversation backup (auto-sync every 60s)
- Auto-shutdown after 30min idle
- Session logging + MCP servers

## Cost

| Instance | $/hr | 8hr day |
|----------|------|---------|
| **t3.large** (default) | **~$0.08** | **~$0.67** |

Auto-stops when idle. Stopped = $0.

## Uninstall

```bash
bash install.sh uninstall
```

## License

MIT
