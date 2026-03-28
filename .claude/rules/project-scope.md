# Project Scope

This repo (claude-portable) is the CCC fleet system only:
- Launcher (ccc), Dockerfile, bootstrap, worker pipeline
- Dispatcher (git-dispatch.py), fleet scaling
- continuous-claude runner
- Worker config, MCP, skills

RONE Teams poller, K8s manifests, and hackathon-specific code belong in:
- `teams-helper/` (joel-ginsberg_tmemu, private)
- `hackathon26/` (local infra workspace)

Communication between RONE and CCC uses git relay files, not HTTP APIs.
