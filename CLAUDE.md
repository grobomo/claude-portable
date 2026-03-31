# Claude Portable Container

Dockerized Claude Code environment on AWS EC2. Chrome, MCP servers, skills, session logging -- all pre-configured.

---

## CRITICAL: AWS EC2 Only -- No Local Docker

**NEVER build or run this container on the local machine.** Always deploy to AWS EC2.

- Use `ccc` (Python launcher) to manage instances
- Build and run the container ON the EC2 instance
- Connect via `ccc --name <name>` or SSH directly

---

## Architecture

```
Local machine
  |
  | ccc --name dev (Python launcher)
  v
EC2 Instance (t3.large, Ubuntu 24.04)
  |
  | docker-compose up
  v
claude-portable container (Debian bookworm + Node 20)
  ├── Claude Code CLI (npm global)
  ├── Google Chrome + Xvfb + VNC (headless browser)
  ├── AWS CLI v2, gh CLI, Python 3, Bitwarden CLI
  ├── Skills (from components.yaml repos)
  ├── MCP servers (from components.yaml repos)
  ├── SSH server (port 22 -> host 2222)
  ├── Idle monitor (auto-shutdown after 30min)
  ├── S3 state-sync (every 60s)
  └── Credential refresh daemon (every 15min)
```

## Key Files

| File | Purpose |
|------|---------|
| `ccc` | Python launcher -- manages EC2 lifecycle, SSH, VNC, SCP |
| `ccc.config.json` | Launcher config (alias, region, instance type, idle timeout) |
| `Dockerfile` | Container image -- Node 20, Claude CLI, Chrome, AWS/gh/Python, SSH |
| `docker-compose.yml` | Base compose config |
| `docker-compose.remote.yml` | EC2 compose override (adds VNC/DevTools/filebrowser ports) |
| `cloudformation/claude-portable-spot.yaml` | CF template (spot instance + IAM role) |
| `components.yaml` | Component manifest -- repos to pull at startup |
| `install.sh` | One-time installer (prereqs + `ccc` command on PATH) |
| `test.sh` | E2E test (launch, validate, teardown) |
| `.env.example` | Template for secrets |
| `.env` | Actual secrets (gitignored) |

### Scripts (inside container)

| Script | Purpose |
|--------|---------|
| `scripts/bootstrap.sh` | Container entrypoint -- 6 steps + daemon startup |
| `scripts/idle-monitor.sh` | Auto-shutdown after N minutes idle |
| `scripts/state-sync.sh` | S3 backup/restore for conversations + sessions |
| `scripts/cred-refresh.sh` | OAuth token refresh daemon |
| `scripts/sync-config.sh` | Pull skills/hooks/MCP from git repos |
| `scripts/sessions.sh` | Session management CLI |
| `scripts/claude-session.sh` | Per-session conversation logging |
| `scripts/health-check.sh` | Container health verification |
| `scripts/browser.sh` | Xvfb + VNC + Chrome + filebrowser |
| `scripts/msg.sh` | Inter-instance messaging via S3 |
| `scripts/inject-secrets.sh` | BWS or direct env var injection |
| `scripts/rewrite-paths.sh` | Fix absolute paths for container |
| `scripts/web-chat.js` | WebSocket chat server for mobile phone access |
| `scripts/web-chat.html` | Mobile-first chat UI (served by web-chat.js) |
| `lambda/web-chat/index.mjs` | Lambda entry point -- discovers EC2, relays prompts |
| `lambda/web-chat/ui.mjs` | Embedded mobile chat UI (served by Lambda on GET /) |
| `lambda/web-chat/deploy.sh` | Deploy/update the Lambda + function URL |

## Auth

The container needs Claude auth tokens. Three modes:

1. **API key** -- set `ANTHROPIC_API_KEY` in `.env` (from RDSEC portal)
2. **OAuth tokens** -- set `CLAUDE_OAUTH_ACCESS_TOKEN` + `CLAUDE_OAUTH_REFRESH_TOKEN` in `.env`
3. **Bitwarden Secrets Manager** -- set `BWS_ACCESS_TOKEN`, bootstrap fetches all secrets

To get OAuth tokens from a running Claude Code session:
```bash
cat ~/.claude/.credentials.json
```

## Bootstrap Sequence

Container entrypoint (`bootstrap.sh`) runs these steps:

1. **Inject secrets** -- BWS or direct env vars -> credential files
2. **Verify auth** -- check OAuth creds or API key, mark onboarding complete
3. **Sync config** -- pull skills/hooks/MCP from git repos via `components.yaml`
4. **Rewrite paths** -- fix absolute paths in config files for container
5. **Start SSH** -- if `SSH_PUBLIC_KEY` set, start sshd on port 22
6. **Install MCP deps** -- npm install / pip install for each MCP server
7. **Start browser** -- Xvfb + VNC + Chrome (if available)
8. **S3 state pull** -- restore conversations from S3 (if bucket exists)
9. **Start daemons** -- auto-sync (60s), cred-refresh (15min), idle-monitor (30min)

## Idle Monitor

Runs as background daemon in remote mode. Checks every 60s for:
- Active Claude CLI processes (`node.*claude`)
- SSH sessions (`who`)
- Interactive shells (`bash -l`)

If idle for `CLAUDE_PORTABLE_IDLE_TIMEOUT` minutes (default 30):
1. Pushes state to S3
2. Gets instance ID from EC2 metadata (IMDSv2)
3. Calls `aws ec2 stop-instances`
4. Fallback: `sudo shutdown -h now`

Configure via env var or `ccc.config.json`:
```bash
CLAUDE_PORTABLE_IDLE_TIMEOUT=30
```

## S3 State Sync

Persists conversations across ephemeral EC2 instances.

**Bucket:** `claude-portable-state-<AWS_ACCOUNT_ID>` (auto-derived)

**What's synced:**
- `claude-state/projects/` -- conversation JSONL + tool results
- `claude-state/sessions/` -- session metadata
- `claude-state/session-env/` -- per-session environment
- `claude-state/history.jsonl` -- full conversation history
- `session-logs/` -- all session conversation logs
- `claude-state/.last-sync.json` -- instance marker + timestamp

**Commands:**
```bash
state-sync setup                 # Create encrypted S3 bucket (one-time)
state-sync pull                  # Pull all state from S3
state-sync push                  # Push current state to S3
state-sync list                  # List conversations in S3
state-sync resume <session-id>   # Resume specific session
state-sync auto [interval]       # Background auto-sync (default 60s)
```

**Security:**
- AES-256 at rest (SSE-S3)
- TLS in transit (HTTPS)
- Versioning enabled (30-day retention)
- Public access blocked

**IAM:** CF template creates a scoped IAM role with:
- `ec2:StopInstances` (only for `Project: claude-portable` tagged instances)
- S3 CRUD on the state bucket only
- `sts:GetCallerIdentity`

## Container Shutdown

EXIT/TERM/INT trap in bootstrap pushes final state to S3 before container stops. Combined with auto-sync (every 60s), maximum data loss on unexpected termination is ~60s.

## Inter-Instance Messaging

Instances communicate via S3 mailbox:
```bash
msg send test2 "Can you research X?"
msg inbox
msg history
msg who
```

## Component System

`components.yaml` defines what gets pulled into the container at startup:

```yaml
- name: my-mcp-server
  repo: your-org/my-mcp-server
  type: mcp              # config | skill | mcp | skill-marketplace
  target: /opt/mcp/my-mcp-server
  enabled: true
  branch: main           # optional
  sparse: path/in/repo   # optional, for monorepos
  visibility: public     # public | private (private needs GITHUB_TOKEN)
```

## Web Chat (Mobile Access)

Offload conversations to the cloud and continue from your phone.

**Offload from local machine:**
```bash
ccc offload "refactor the auth module"          # send prompt, get web URL
ccc offload -n dev                              # just get the web URL for existing instance
ccc offload -n dev -w /workspace/my-project     # set working directory
```

**How it works:**
1. `ccc offload` ensures an instance is running + web-chat server is up
2. Prints a URL with embedded auth token -- open on your phone
3. Mobile chat UI connects via WebSocket, sends prompts to Claude CLI
4. Claude streams responses back in real-time

**Security:**
- Token auth (auto-generated or set via `CLAUDE_WEB_TOKEN` env var)
- WebSocket heartbeat (30s ping, detects dead connections)
- Rate limiting (20 msgs/min per client)
- Max 5 concurrent connections
- Port 8888 open in security group (token required to use)

**Architecture:**
- `lambda/web-chat/` -- Lambda Function URL (stable HTTPS endpoint, never changes)
- `scripts/web-chat.js` -- runs on EC2 container, handles Claude CLI interaction
- Lambda discovers running EC2 instance and relays prompts to it
- Phone -> Lambda (HTTPS) -> EC2:8888 (HTTP) -> Claude CLI

**Deploy Lambda:** `bash lambda/web-chat/deploy.sh`

**Stable URL:** configured in `ccc.config.json` as `web_chat_lambda_url`

**Env vars:**
| Variable | Default | Purpose |
|----------|---------|---------|
| `CLAUDE_WEB_TOKEN` | auto-generated | Auth token for web chat |
| `CLAUDE_WEB_PORT` | 8888 | Server port |
| `CLAUDE_WEB_MAX_CONN` | 5 | Max concurrent WebSocket connections |

## Session Tracking

Every SSH connection gets a unique session ID. All Claude interactions are logged to `/data/sessions/`.

```bash
sessions list              # List recent sessions
sessions view <id>         # Read conversation log
sessions search <pattern>  # Search across sessions
sessions export <id>       # Export clean text
sessions clean [days]      # Delete older than N days
```

## Persistence

| Volume | Mount | Survives restart? | Survives destroy? |
|--------|-------|-------------------|-------------------|
| `claude-sessions` | `/data/` | YES | YES |
| `claude-config` | `~/.claude/` | YES | Rebuilt from git |
| `claude-mcp` | `/opt/mcp/` | YES | Rebuilt from git |

S3 state-sync provides durability beyond Docker volumes.

## Ports (remote mode)

| Port | Service | Access |
|------|---------|--------|
| 2222 | Container SSH | Public (key-based auth) |
| 5900 | VNC (Chrome desktop) | localhost only (SSH tunnel) |
| 9222 | Chrome DevTools | localhost only |
| 8080 | Dispatcher health API | localhost only |
| 8082 | Fleet dashboard (Tasks + Infra Health) | localhost only |
| 8888 | Web chat (phone access) | Public (token-authed) |

## Testing

```bash
bash test.sh           # Full E2E: launch, validate, teardown (~8 min)
bash test.sh --keep    # Keep instance for manual inspection
```

Tests: script syntax, bootstrap completion, auth, idle monitor, S3 sync, cred refresh, Chrome/VNC, sessions, health check.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "OAuth token has expired" | Push fresh tokens or restart local Claude |
| Container crash-looping | `ssh ubuntu@<IP> 'docker logs claude-portable'` |
| Spot interrupted | Relaunch: `ccc --name <name>` |
| `ccc` not found after reboot | `bash install.sh` (re-creates wrapper) |
| S3 sync fails | Run `state-sync setup` on instance first |
