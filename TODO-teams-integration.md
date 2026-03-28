# Teams Integration & Fleet Config TODO

## Phase 0: Architecture — dedicated dispatcher instance
- [ ] Create `dispatcher` role — a CCC instance that runs teams-dispatch.py as a daemon
  - NOT a worker (doesn't execute tasks itself)
  - NOT on the laptop (survives laptop shutdown)
  - Pulls Graph API token from AWS Secrets Manager at boot
  - Has SSH keys to all worker instances (shared via S3 key bucket)
  - Manages worker lifecycle via AWS EC2 API directly (start/stop/launch)
  - Runs as systemd service or supervised daemon (auto-restart on crash)
  - Logs all dispatch activity to S3 for auditing
- [ ] Create `scripts/dispatcher-daemon.sh` — entrypoint that:
  - Pulls Graph token from Secrets Manager
  - Pulls SSH keys from S3 key bucket
  - Starts teams-dispatch.py with watchdog (restarts on crash)
  - Streams logs to /data/dispatcher.log + S3
- [ ] Add `ccc --name dispatcher` launch flow that:
  - Launches small instance (t3.small, no Chrome/browser needed)
  - Injects IAM role for Secrets Manager + EC2 + S3 access
  - Starts dispatcher-daemon.sh as bootstrap entrypoint
  - Does NOT start continuous-claude (dispatcher doesn't do work)
- [ ] SSH key sharing: dispatcher needs keys to all workers
  - On worker launch, upload public key to S3 key bucket
  - Dispatcher pulls all keys from S3 at boot + periodically
  - Or: use a shared SSH key across all workers (simpler)
- [ ] Test: launch dispatcher + 2 workers, send @claude prompt, verify end-to-end

## Phase 0.5: Dispatcher monitoring & self-healing
- [ ] Heartbeat: dispatcher writes timestamp to S3 every 60s (`s3://bucket/dispatcher/heartbeat.json`)
- [ ] CloudWatch alarm: if heartbeat file age > 5 min, trigger SNS alert
  - SNS sends email notification
  - SNS triggers Lambda that auto-restarts the dispatcher instance
- [ ] Lambda auto-healer: checks EC2 instance state, restarts if stopped, recreates if terminated
- [ ] Dispatcher health endpoint: simple HTTP server on port 8080 that returns status JSON
  - Dispatch loop alive (last poll timestamp)
  - Workers reachable (last successful SSH to each)
  - Graph API token valid (last successful Teams API call)
  - Pending requests count
  - Error count in last hour
- [ ] Dead letter queue: if a request fails dispatch 3 times, notify in Teams and stop retrying
- [ ] Daily summary: dispatcher posts daily digest to Teams chat
  - Requests handled, success/fail rate, worker utilization, uptime

## Phase 1: Fleet config template (grobomo/claude-code-defaults)
- [ ] Create `fleet/` folder in grobomo/claude-code-defaults repo
- [ ] Create `fleet/worker.yaml` — manifest:
  - settings.json (bypass perms, opus model)
  - CLAUDE.md (shared instructions: branches/PRs, no secrets)
  - MCP servers (mcp-manager, blueprint-extra-mcp)
  - Skills (from grobomo marketplace)
  - Tools (v1-api, trend-docs)
- [ ] Create `fleet/dispatcher.yaml` — manifest for dispatcher (lightweight, no browser)
- [ ] Create `fleet/CLAUDE.md` — shared instructions for ALL instances:
  - Always use branches and PRs for code changes
  - Track all work with continuous-claude workflow
  - Never commit secrets
- [ ] Bootstrap reads fleet config from claude-code-defaults at startup

## Phase 2: Worker lifecycle management
- [ ] Dispatcher manages workers via AWS EC2 API:
  - Auto-scale: launch workers when queue is full, stop when idle
  - Health check: verify workers are responsive, restart if not
  - Instance tagging: role=worker/dispatcher/interactive
- [ ] Maintenance mode: dispatcher pauses task dispatch to a worker
- [ ] Worker registration: new workers announce themselves to dispatcher

## Phase 3: Continuous-claude for ALL instances
- [ ] Workers get continuous-claude rules via fleet CLAUDE.md
- [ ] Interactive instances get same rules
- [ ] All code changes tracked with branches/PRs regardless of instance type

## Phase 4: Extensibility
- [ ] Add new tools by editing fleet/worker.yaml, redeploy
- [ ] Config changes auto-propagate on next instance launch
- [ ] Add v1-api, v1-ego, trend-docs as they become ready
