# Dispatcher Area

## What it does
Watches TODO.md via git poll, manages EC2 worker fleet (scale up/down), polls relay repo for RONE requests, runs leader election for HA.

## Key files
- `scripts/git-dispatch.py` — main dispatcher: TODO poll, relay poll, fleet monitor, health endpoint, leader election
- `scripts/dispatcher-daemon.sh` — container entrypoint for dispatcher role
- `cloudformation/dispatcher.yaml` — IAM role, CloudWatch alarm, SNS, Lambda auto-healer

## Architecture
- Two poll loops: TODO (60s) and relay (30s), both skip in standby mode
- S3-based leader election: heartbeat every 30s, stale threshold 5min
- Fleet roster maintained via worker self-reporting (POST /worker/register, /done, /idle)
- Fleet monitor (safety net): SSH checks stale workers every 60s, 35min threshold
- Health endpoint on port 8080: GET /health, /relay/status

## Gotchas
- `max_workers` vs `max_instances` — both supported in ccc.config.json, env var takes priority
- Workers launched by dispatcher must register within 5min or get terminated
- Relay repo (ccc-rone-bridge) is tmemu private — needs tmemu GitHub token
