# Dispatcher Architecture

- `git-dispatch.py` is the single dispatcher. There is NO separate chatbot instance.
- Two poll loops:
  1. **TODO poll** (60s): watches TODO.md on main, scales EC2 workers
  2. **Relay poll** (30s): watches ccc-rone-bridge git repo for RONE Teams requests
- Dispatcher responds to chat requests like a chatbot — via RONE git bridge, not direct Teams API.
- HTTP endpoints are for health/status and worker self-reporting only.
- Repos: main repo at `/workspace/claude-portable`, relay repo at `/data/relay-repo`.
