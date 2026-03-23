# Claude Portable Container

Dockerized Claude Code environment on AWS EC2 spot instances. Chrome, MCP servers, skills, session logging -- all pre-configured.

---

## CRITICAL: AWS EC2 Only -- No Local Docker

**NEVER build or run this container on the local machine.** Always deploy to AWS EC2.

- Use `run.sh` or the CloudFormation template to launch a spot instance
- Build and run the container ON the EC2 instance
- SSH into the EC2 to interact with Claude inside the container

---

## Architecture

```
Local machine
  |
  | SSH (port 2222)
  v
EC2 Spot Instance (t3.large, Ubuntu 24.04)
  |
  | docker-compose up
  v
claude-portable container (Debian bookworm + Node 20)
  ├── Claude Code CLI (npm global)
  ├── Google Chrome + Xvfb (headless browser for Blueprint MCP)
  ├── AWS CLI v2, gh CLI, Python 3, Bitwarden CLI
  ├── Skills (from components.yaml repos)
  ├── MCP servers (from components.yaml repos)
  └── SSH server (port 22 -> host 2222)
```

## Key Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Container image -- Node 20, Claude CLI, Chrome, AWS/gh/Python, SSH |
| `docker-compose.yml` | Base compose config |
| `docker-compose.remote.yml` | EC2 compose override |
| `cloudformation/claude-portable-spot.yaml` | EC2 spot instance with Docker |
| `components.yaml` | Component manifest -- repos to pull at startup |
| `run.sh` | One-click deploy (supports --name for multi-instance) |
| `list.sh` | List all running instances |
| `terminate.sh` | Terminate instances by name or --all |
| `push.sh` | Push file updates to running instances |
| `scripts/msg.sh` | Inter-instance messaging via S3 |
| `.env.example` | Template for secrets |
| `.env` | Actual secrets (gitignored) |

## Auth

The container needs Claude OAuth tokens. Two modes:

1. **Direct env vars** -- set `CLAUDE_OAUTH_ACCESS_TOKEN` + `CLAUDE_OAUTH_REFRESH_TOKEN` in `.env`
2. **Bitwarden Secrets Manager** -- set `BWS_ACCESS_TOKEN`, bootstrap fetches all secrets

To get your OAuth tokens from a running Claude Code session:
```bash
cat ~/.claude/.credentials.json
```

## Deployment

```bash
# Set up .env (copy from .env.example, fill in tokens)
cp .env.example .env

# Launch named instances
./run.sh --name dev
./run.sh --name lab1

# List running instances
./list.sh

# SSH to container and use Claude
ssh -p 2222 claude@<IP>

# Push file updates to running instances
./push.sh scripts/msg.sh
./push.sh --all

# Terminate
./terminate.sh --name dev
./terminate.sh --all
```

## Inter-Instance Messaging

Instances can communicate via S3 mailbox:
```bash
msg send test2 "Can you research X?"
msg inbox
msg history
msg who
```

## Component System

`components.yaml` defines what gets pulled into the container at startup. Add your own repos for config, skills, and MCP servers. Each component has: name, repo, type, target path, enabled flag.

## Session Tracking

Every SSH connection gets a unique session ID. All Claude interactions are logged to `/data/sessions/`.

```bash
sessions list              # List recent sessions
sessions view <id>         # Read conversation log
sessions search <pattern>  # Search across sessions
sessions export <id>       # Export clean text
```

## Persistence

| Volume | Mount | Survives container destroy? |
|--------|-------|---------------------------|
| `claude-sessions` | `/data/` | YES -- session logs persist |
| `claude-config` | `~/.claude/` | YES -- but rebuilt from git |
| `claude-mcp` | `/opt/mcp/` | YES -- but rebuilt from git |

## TODO

- [x] Full CF deploy e2e tested
- [x] Health check script
- [x] One-click deploy wrapper
- [x] Chrome + Blueprint MCP support
- [x] Multi-instance with --name flag
- [x] list.sh + terminate.sh + push.sh
- [x] Inter-instance messaging (msg)
- [ ] Auto-shutdown on idle (cost savings)
- [ ] S3 backup for session logs
