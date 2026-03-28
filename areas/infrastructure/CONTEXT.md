# Infrastructure Area

## What it does
Container image, bootstrap, credential management, S3 state sync, browser automation, session tracking.

## Key files
- `Dockerfile` — container image: Node 20, Claude CLI, Chrome, AWS/gh/Python, SSH
- `docker-compose.yml` — base compose config
- `docker-compose.remote.yml` — EC2 compose override (VNC/DevTools/filebrowser ports)
- `scripts/bootstrap.sh` — container entrypoint: 9-step startup sequence
- `scripts/inject-secrets.sh` — BWS or direct env var injection
- `scripts/cred-refresh.sh` — OAuth token refresh daemon (every 15min)
- `scripts/sync-config.sh` — pull skills/hooks/MCP from git repos via components.yaml
- `scripts/rewrite-paths.sh` — fix absolute paths for container environment
- `scripts/browser.sh` — Xvfb + VNC + Chrome + filebrowser
- `scripts/sessions.sh` — session management CLI
- `scripts/health-check.sh` — container health verification
- `components.yaml` — component manifest: repos to pull at startup
- `install.sh` — one-time installer (prereqs + ccc on PATH)

## Architecture
- Bootstrap runs 9 steps in order: secrets, auth, config sync, path rewrite, SSH, MCP deps, browser, S3 pull, daemons
- Three auth modes: API key, OAuth tokens, Bitwarden Secrets Manager
- S3 state sync: push/pull every 60s, encrypted at rest, versioned
- Persistent volumes: claude-sessions (/data/), claude-config (~/.claude/), claude-mcp (/opt/mcp/)
- Container runs as `claude` user (not root)

## Gotchas
- Container is Debian bookworm, NOT Ubuntu
- Chrome home dir is /home/claude (not /root)
- Never build/run locally — always deploy to EC2
- EXIT trap in bootstrap pushes final state to S3
