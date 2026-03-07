# Claude Portable Container

Dockerized Claude Code environment with pre-configured skills, MCP servers, hooks, and rules -- pulled from GitHub repos at container startup.

---

## CRITICAL: AWS EC2 Only -- No Local Docker

**NEVER build or run this container on the local machine.** Always deploy to AWS EC2.

- Use the CloudFormation template (`cloudformation/claude-portable-spot.yaml`) to launch a spot instance
- Build and run the container ON the EC2 instance
- SSH into the EC2 to interact with Claude inside the container
- Local Docker Desktop is NOT used for this project

**Why:** The local machine already runs Claude Code natively. The container is for remote/headless use cases (CI, cloud workers, portable environments on fresh machines).

---

## Architecture

```
Local machine (Windows)
  |
  | SSH (port 2222)
  v
EC2 Spot Instance (t3.medium, Amazon Linux 2023)
  |
  | docker-compose up
  v
claude-portable container (Debian bookworm + Node 20)
  ├── Claude Code CLI (npm global)
  ├── Skills (from grobomo/claude-code-skills)
  ├── MCP servers (from <your-org>/mcp-dev sparse checkout)
  ├── Hooks + rules (from grobomo/claude-code-defaults)
  ├── AWS CLI v2, gh CLI, Python 3, Bitwarden CLI
  └── SSH server (port 22 -> host 2222)
```

## Key Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Container image -- Node 20, Claude CLI, AWS/gh/Python, SSH server |
| `docker-compose.yml` | Local compose (NOT USED -- see rule above) |
| `docker-compose.remote.yml` | EC2 compose override |
| `cloudformation/claude-portable-spot.yaml` | EC2 spot instance with Docker, builds from git |
| `components.yaml` | Component manifest -- repos to pull at startup |
| `config/components.yaml` | Copy baked into image |
| `.env.example` | Template for secrets (OAuth, GitHub, API tokens) |
| `.env` | Actual secrets (gitignored) |

## Auth Modes

1. **Bitwarden Secrets Manager** (production) -- set `BWS_ACCESS_TOKEN`, bootstrap fetches all secrets from BWS
2. **Direct env vars** (dev) -- set `CLAUDE_OAUTH_ACCESS_TOKEN` + other tokens in `.env`

## Component System

`components.yaml` defines what gets pulled into the container at startup:

- **config** -- CLAUDE.md, settings.json, hooks, rules (from `grobomo/claude-code-defaults`)
- **skill-marketplace** -- published skills (from `grobomo/claude-code-skills`)
- **mcp** -- MCP servers via sparse checkout (from `<your-org>/mcp-dev`)

Each component has: name, repo, type, target path, enabled flag, visibility (public/private).

## Deployment

```bash
# 1. Deploy EC2 spot instance
aws cloudformation create-stack \
  --stack-name claude-portable \
  --template-body file://cloudformation/claude-portable-spot.yaml \
  --parameters ParameterKey=GitHubToken,ParameterValue=<token> \
               ParameterKey=OAuthAccessToken,ParameterValue=<token> \
  --capabilities CAPABILITY_NAMED_IAM \
  --profile <your-profile> --region us-east-2

# 2. SSH to container on EC2
ssh -i ~/.ssh/<your-key>.pem -p 2222 claude@<ec2-ip>

# 3. Run Claude inside container
claude -p "do something"
```

## Session Tracking

Every SSH connection gets a unique session ID. All Claude interactions are logged to persistent storage at `/data/sessions/`.

### How It Works

1. SSH into container -> `.bashrc` sources `config/bashrc-session.sh`
2. Session ID generated: `YYYYMMDD-HHMMSS-<random hex>` (e.g. `20260306-143022-a1b2c3d4`)
3. `claude` is aliased to `scripts/claude-session.sh` which wraps the real CLI
4. Full terminal I/O captured to `/data/sessions/<id>/conversation.log`
5. Metadata (start time, SSH client, invocation count) in `meta.json`

### Session Storage

```
/data/                          # Persistent Docker volume (survives container destroy)
  sessions/
    20260306-143022-a1b2c3d4/   # One dir per SSH session
      meta.json                 # Session metadata
      conversation.log          # Full terminal capture of all Claude interactions
    20260306-150100-e5f6a7b8/   # Another concurrent session
      meta.json
      conversation.log
  exports/                      # Clean text exports (ANSI stripped)
```

### Commands (inside container)

```bash
sessions list              # List recent sessions (newest first)
sessions view <id>         # Read full conversation log
sessions tail <id> [N]     # Last N lines of a session
sessions search <pattern>  # Grep across all session logs
sessions active            # Show sessions active in last 5 min
sessions export <id>       # Export clean text to /data/exports/
sessions current           # Show current session ID
sessions clean [days]      # Delete sessions older than N days
```

### Commands (from local machine via CLI wrapper)

```bash
claude-portable sessions list          # Run sessions command in container
claude-portable session-logs           # Pull all session logs to ./session-logs/
```

### Multiple Concurrent Sessions

Each SSH connection gets its own session ID. You can have multiple terminals connected simultaneously, each with separate logs:

```
Terminal 1: ssh -p 2222 claude@<ec2-ip>   ->  session 20260306-143022-a1b2c3d4
Terminal 2: ssh -p 2222 claude@<ec2-ip>   ->  session 20260306-143500-b2c3d4e5
Terminal 3: ssh -p 2222 claude@<ec2-ip>   ->  session 20260306-144000-c3d4e5f6
```

### Persistence

| Volume | Mount | Survives container destroy? |
|--------|-------|---------------------------|
| `claude-sessions` | `/data/` | YES -- session logs persist |
| `claude-config` | `~/.claude/` | YES -- but rebuilt from git |
| `claude-mcp` | `/opt/mcp/` | YES -- but rebuilt from git |

The `claude-sessions` volume is the only truly persistent state. Config and MCP are reconstructable from git repos.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/bootstrap.sh` | Container entrypoint -- injects secrets, syncs config, starts SSH |
| `scripts/inject-secrets.sh` | BWS or direct env var secret injection |
| `scripts/sync-config.sh` | Git clone/pull components from components.yaml |
| `scripts/rewrite-paths.sh` | Fix Windows paths to Linux paths in configs |
| `scripts/push-config.sh` | Push local config changes back to repos |
| `scripts/claude-session.sh` | Wraps Claude CLI with per-session logging |
| `scripts/sessions.sh` | List/view/search/export session logs |
| `config/bashrc-session.sh` | Sourced on SSH login -- generates session ID, sets up aliases |
| `bin/claude-portable` | CLI wrapper (local convenience) |

## Gotchas

- `docker-compose.yml` exists for reference but is NOT used locally -- deploy to EC2
- `.claude.json` must exist at BOTH `~/` and `~/.claude/` (symlinked by bootstrap)
- `hasCompletedOnboarding: true` required in both `.claude.json` and `settings.local.json`
- MCP servers from monorepo use sparse checkout (not full clone)
- `claude-sessions` volume is the only non-reconstructable persistent state -- back it up
- `push-config.sh` references `/opt/claude-portable/defaults` but sync-config caches to `/opt/claude-portable/repos/` -- needs fix

## TODO

- [ ] Test full CF deploy end-to-end on fresh spot instance
- [ ] Add health check script (verify Claude auth, MCP servers, skills loaded)
- [ ] Add `run.sh` one-click deploy wrapper
- [ ] Test BWS secret injection mode
- [ ] Add auto-shutdown on idle (spot cost savings)
- [ ] Fix push-config.sh path mismatch (defaults vs repos cache dir)
- [ ] Add S3 backup for session logs (survive EC2 termination)
