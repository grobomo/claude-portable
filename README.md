# Claude Portable

Run Claude Code on AWS EC2. Full environment with Chrome, VNC, MCP servers, session persistence. ~$0.03/hr.

## Prerequisites

| Requirement | How to get it |
|-------------|--------------|
| AWS CLI + credentials | `aws configure` -- [install](https://aws.amazon.com/cli/) |
| Git | [git-scm.com](https://git-scm.com/) |
| Python 3.8+ | [python.org/downloads](https://www.python.org/downloads/) |
| **Anthropic API key** | RDSEC portal > Claude API > Generate Key |
| **GitHub token** | Run `gh auth token` or create at [github.com/settings/tokens](https://github.com/settings/tokens) |

> **Enterprise/Max users:** Instead of an API key, you can use OAuth tokens from your local Claude Code session: `cat ~/.claude/.credentials.json`

## Install

```bash
git clone https://github.com/grobomo/claude-portable.git ~/claude-portable
cd ~/claude-portable
bash install.sh
```

## Configure

```bash
cp .env.example .env
```

Edit `.env`:

```bash
ANTHROPIC_API_KEY=sk-ant-...         # from RDSEC portal
GITHUB_TOKEN=ghp_...                 # from: gh auth token
REPO_URL=https://github.com/grobomo/claude-portable.git
```

## Launch

```bash
ccp --name dev
```

First launch: ~5-7 min (builds Docker on EC2). After that, stopped instances resume in ~30 sec.

## Usage

```bash
ccp --name dev         # Connect (starts if stopped)
ccp list               # List instances
ccp vnc                # Open VNC (Chrome browser)
ccp scp file.txt       # Copy file to instance
ccp stop dev           # Stop ($0/hr while stopped)
ccp kill dev           # Destroy permanently
ccp kill --all         # Destroy everything
```

## What's included

- Claude Code CLI (latest)
- Google Chrome + VNC (headless browser)
- AWS CLI, GitHub CLI, Python 3
- S3 conversation backup (auto-sync every 60s)
- Auto-shutdown after 30min idle (configurable)
- Session logging to `/data/sessions/`
- MCP servers and skills from `components.yaml`

## Cost

| Instance | $/hr | 8hr day |
|----------|------|---------|
| t3.medium | ~$0.04 | ~$0.34 |
| **t3.large** (default) | **~$0.08** | **~$0.67** |
| t3.xlarge | ~$0.17 | ~$1.33 |

Instances auto-stop after 30min idle. Stopped instances cost $0.

## Uninstall

```bash
bash install.sh uninstall
```

## Testing

```bash
bash test.sh           # Launch instance, run all checks, tear down
bash test.sh --keep    # Keep instance for manual inspection
```

## License

MIT
