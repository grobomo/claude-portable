# Relay: HTTP→Git Migration (2026-03-28)

## Decision
Replaced uncommitted HTTP relay endpoints (`/relay`, `/result`) in git-dispatch.py with git-based relay polling against ccc-rone-bridge repo.

## Why
- HTTP relay requires direct network path from RONE (K8s) to CCC (EC2) — firewall/NAT headache
- Git relay works through GitHub HTTPS — both environments already have tokens
- Architecture was explicitly decided in commits b04324d, b0e5991, f10c020
- The uncommitted HTTP code contradicted those decisions

## What changed
- `git-dispatch.py`: removed HTTP `/relay` endpoint, added `relay_poll_loop()` that clones/pulls ccc-rone-bridge every 30s
- Relay requests flow: RONE→git push→dispatcher git pull→SSH to worker→result→git push→RONE git pull
- Health endpoint now includes relay stats at `/health` and `/relay/status`
- `.env.example`: added RELAY_REPO_URL, RELAY_REPO_DIR, RELAY_POLL_INTERVAL
- `.gitignore`: added `.mcp.json` (local paths)
- `dispatcher-architecture.md`: updated to reflect git relay design
