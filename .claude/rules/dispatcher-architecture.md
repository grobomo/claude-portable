# Dispatcher Architecture

- `git-dispatch.py` is the single dispatcher script. It runs two poll loops:
  1. **TODO poll** (every 60s): watches TODO.md on main, scales EC2 workers
  2. **Relay poll** (every 30s): watches ccc-rone-bridge git repo for RONE requests
- HTTP endpoints are for health/status and worker self-reporting only — not for relay.
- RONE communication uses git files (see git-relay-design.md), not HTTP APIs.
- Dispatcher needs the main repo at `/workspace/claude-portable` and the relay repo at `/data/relay-repo`.
