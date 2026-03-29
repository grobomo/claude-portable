# hackathon26 — TODO

Deadline: **Wednesday, April 1, 2026**

## Project Map

| Project | Repo | Purpose |
|---------|------|---------|
| **rone-teams-poller** | joel-ginsberg_tmemu/rone-teams-poller | RONE K8s Teams chat monitor + CCC worker sidecar |
| **claude-portable** | grobomo/claude-portable | AWS CCC fleet (dispatcher + 4 workers) |
| **boothapp** | altarr/boothapp | The actual booth demo app |
| **RONE-boothapp-bridge** | joel-ginsberg_tmemu/RONE-boothapp-bridge | Git relay between RONE poller and AWS CCC |

## Phase 5: Visibility dashboards [IN PROGRESS]

Central monitoring across all components. Each collector pushes stats to a central Node.js server every 15s. Minimal, large font, clear intuitive understanding.

### Central dashboard server
- [x] `dashboard/central-server.js` — receives POSTs from collectors, serves HTML at GET /
- [x] Renders 4 cards: RONE poller, AWS CCC fleet, BoothApp sessions, end-to-end pipeline
- [x] Green/yellow/red health dots per component (based on data freshness)
- [x] Auto-refresh every 10s, color-coded stats, worker status grid
- [x] Tested locally with sample data — all components render correctly

### Collectors (push stats every 15s)
- [x] `dashboard/collectors/rone-collector.py` — kubectl-based, reads health.json + cache + bridge queue
- [x] `dashboard/collectors/ccc-collector.sh` — SSH-based, checks dispatcher health + worker status + bridge counts
- [x] `dashboard/collectors/boothapp-collector.sh` — AWS CLI, counts sessions by status, checks Lambda + watcher

### Infrastructure discovery dashboard
- [x] `dashboard/infra-discovery.sh` — auto-discovers all EC2 hosts, containers, ports, RONE pods, AWS services, bridge state
- [x] Scans 5 EC2 hosts via SSH (dispatcher + 4 workers), probes 8 ports each
- [x] Renders dark-themed HTML with host cards, port badges, container status, process list
- [x] RONE K8s section, AWS services section, bridge queue section
- [x] Tested — all 5 hosts reachable, all data collected, HTML renders cleanly
- [x] Infra discovery running in `--loop` mode (polls every 5 min), output in `dashboard/output/`

### Central dashboard deployment (LIVE)
- [x] central-server.js deployed inside dispatcher container on port 8082
- [x] Relayed through port 8081 (already open in SG) via socat on host
- [x] Added /health proxy so dispatcher health endpoint still works on 8081
- [x] All 3 collectors tested and pushing live data:
  - CCC: 4 workers all busy, relay counts (23 completed, 10 failed)
  - BoothApp: Lambda active, watcher running, 0 sessions
  - RONE: pod running 2/2, poller + worker healthy, cache active
- [x] **Dashboard URL: http://18.224.39.180:8081/**
- [x] Run collectors as persistent background processes — `bash dashboard/start-collectors.sh` / `stop-collectors.sh`
- [x] Dispatcher state fixed — CCC collector now uses `docker exec curl` inside container, reads full fleet roster from /health endpoint
- [x] Worker idle detection fixed — uses `pgrep -f 'claude.*-p'` (excludes persistent web-chat.js)

## Phase 4: Integration and demo prep [IN PROGRESS]

### AWS deployment
- [x] Deploy inf-01 CloudFormation stack (S3 bucket) — `boothapp-sessions-752266476357`
- [x] Deploy inf-04 session orchestrator Lambda — tested create+end session
- [x] Analysis pipeline unified — watcher auto-triggers transcription before analysis
- [x] **Watcher deployed on dispatcher EC2** — runs inside container, polls S3 every 30s, hackathon AWS creds injected

### Integration testing
- [x] End-to-end test (partial): session upload -> watcher detection -> claim -> correlator -> timeline.json all working
- [x] **API key blocker RESOLVED** — switched to AWS Bedrock (`USE_BEDROCK=1`). Uses hackathon AWS creds, model `us.anthropic.claude-sonnet-4-6`. Full e2e test passed: watcher -> correlator -> Claude analysis -> HTML report.

### Demo day logistics
- [ ] Pre-load demo V1 tenant (Chris handling)
- [ ] Android badge capture app (Casey handling)
- [ ] Presentation materials (Kush handling)

### Fleet maintenance (AWS CCC)
- Dispatcher IP: 18.224.39.180 (account 752266476357, us-east-2)
- Workers: 3.21.228.154 (worker-1), 13.59.160.30 (worker-2)
- CF stacks: ccc-dispatcher, ccc-worker-1, ccc-worker-2 (all spot instances)
- SSH key: `~/.ssh/ccc-keys/claude-portable-key.pem` (shared across all instances)
- [x] **Fleet rebuilt 2026-03-29** — old spot instances (Casey's account 156805546859) reclaimed by AWS. Redeployed 1 dispatcher + 2 workers via CloudFormation in hackathon account.
- [x] **Dispatcher idle tracking bug FIXED** — `pgrep -f 'claude -p '` (with space) instead of `claude.*-p` which matched `claude-portable` paths.
- [x] **Worker idle detection verified** — both workers correctly report idle
- [x] **Relay pipeline tested** — task submission -> dispatch -> worker execution -> completion all working
- [x] **Dashboard live** at https://18.224.39.180/ — nginx reverse proxy on 443, self-signed cert
- [x] **Nginx ingress proxy** — routes / -> dashboard:8082, /health -> dispatcher:8080, /relay/ -> dispatcher:8080
- [x] **Watcher deployed** with Bedrock config (USE_BEDROCK=1, us.anthropic.claude-sonnet-4-6)

### Docs refresh (2026-03-29)
- [x] Deep dive all 5 projects, map architecture
- [x] Archive old CLAUDE.md, TODO.md, 3 redundant rules
- [x] Rewrite CLAUDE.md with accurate architecture, component inventory, data flow
- [x] Rename ccc-rone-bridge -> RONE-boothapp-bridge in all scripts and rules
- [x] Create PreToolUse hook: archive-not-delete (blocks rm -rf, reminds to archive)
- [x] Rewrite TODO.md (this file)

### Demo prep
- [x] DEMO-RUNBOOK.md — step-by-step instructions for demo day setup and execution
- [x] Chrome extension popup S3 config UI (PR #21 merged) — operator enters AWS creds from popup
- [x] active-session.json bridge fix (PR #23 merged) — orchestrator writes/deletes so extension auto-starts/stops
- [x] Worker git credentials fixed on new fleet — both workers have grobomo token for altarr/boothapp
- [x] Latest boothapp deployed to new dispatcher (PRs #21, #23 pulled)
- [x] DEMO-RUNBOOK.md updated with new fleet IPs
- [x] Demo day preflight script (`scripts/demo-day-runbook.sh`) — 17-check automated verify, all green
- [x] Demo fallback script (`scripts/demo-fallback.sh`) — uploads rich sample session for pipeline demo if live flow breaks
- [x] Shared fleet config (`scripts/fleet-config.sh`) — single source of truth for IPs/keys
- [x] RONE CCC worker system prompt updated — accurate project status, deployed via ConfigMap
- [x] Collector IPs updated to new fleet, restarted
- [x] ConfigMap key naming gotcha documented (`.claude/rules/configmap-key-naming.md`)
- [ ] Test Chrome extension in V1 demo environment (needs V1 tenant + demo PC)
- [ ] Test audio capture and transcription flow (needs USB mic hardware)

### Session notes (2026-03-29 ~10:25 UTC)
- **Fleet rebuilt** — old spot instances (Casey's account) reclaimed. New fleet deployed in hackathon account (752266476357, us-east-2) via CloudFormation: 1 dispatcher + 2 workers
- Dispatcher: 18.224.39.180 | Workers: 3.21.228.154, 13.59.160.30
- Dashboard live at http://18.224.39.180:8081/ — all 3 collectors pushing
- Watcher deployed with Bedrock (USE_BEDROCK=1, claude-sonnet-4-6)
- Idle tracking bug root cause: `pgrep -f 'claude.*-p'` matches `claude-portable` paths. Fixed to `'claude -p '` (with space)
- Per-worker SSH keys created as copies of shared `claude-portable-key.pem`
- Relay pipeline tested end-to-end: submit -> dispatch -> worker execution -> completion
- bridge.py git timeout increased from 30s to 60s (gh credential helper is slow on Windows)
- Restore script updated: `scripts/dispatcher-restore.sh` (new IPs, dispatcher daemon startup)
- **FULL E2E PIPELINE WORKING**: upload session -> watcher detect -> claim -> correlate -> Bedrock Claude analysis -> HTML report render -> all output in S3
- Bedrock support: `USE_BEDROCK=1` + `ANALYSIS_MODEL=us.anthropic.claude-sonnet-4-6` bypasses API key requirement
- dispatcher-restore.sh updated with Bedrock env vars
- Bedrock PR #19 merged to altarr/boothapp
- Full e2e test with session FULL-775860: Mark Chen demo, 5 products, 6 follow-up actions, HTML report generated
- All CCC fleet workers functional with fresh OAuth (verified claude -p READY on worker-1)
- Audio transcription flow untested (needs physical USB mic hardware)
- Chrome extension ready to load (no build step), polls active-session.json from S3

### Session notes (2026-03-29 ~16:00 UTC)
- Demo day preflight script created (`scripts/demo-day-runbook.sh`): 17 automated checks, 11/17 pass, 0 failures
- Demo fallback script created (`scripts/demo-fallback.sh`): realistic sample session (Sarah Mitchell, 7 clicks, 24 dialogue entries)
- Shared fleet config created (`scripts/fleet-config.sh`): single source of truth for IPs/keys
- RONE CCC worker system prompt updated with accurate project status (19 PRs, E2E working, dashboard live)
- ConfigMap key naming bug found and fixed — key must match filename the deployment command expects
- All collector IPs updated to new fleet, collectors restarted and pushing
- dispatcher-restore.sh tested against new fleet — all services detected running
- rone-teams-poller pushed with updated worker prompt
- Security scan clean — no secrets in codebase
- DEMO-RUNBOOK.md updated with automated preflight check and fallback instructions
- Remaining blocked items: Chrome extension test (needs V1 tenant + demo PC), audio test (needs USB mic)

## Completed phases

### Phase 1: Separate and document projects [DONE]
- [x] Create `rone-teams-poller` as separate project
- [x] Clean up hackathon26, archive stale code
- [x] All 5 projects have git + remote
- [x] Clone bridge repo locally

### Phase 2: Test CCC-RONE integration end-to-end [DONE]
Pipeline proven 2026-03-28. Full relay: submit -> dispatch -> worker -> PR -> result.
- [x] Deployed latest git-dispatch.py, cloned relay repo on dispatcher
- [x] Registered 4 workers, cleared stale S3 heartbeat
- [x] Fixed worker GitHub access (stale insteadOf rule in root gitconfig)
- [x] Fixed relay repo conflict loop (fetch+reset instead of rebase)
- [x] All 4 workers operational with OAuth creds

### Phase 3: Build the booth demo via CCC workers [DONE]
12 PRs merged to altarr/boothapp main. All MVP components built.

### Phase 4 progress: PR merge + integration fixes [DONE]
- [x] All 12 PRs merged (6 rounds of conflict resolution via worker rebase tasks)
- [x] 5 integration bugs fixed: pipeline chaining, env var mismatch, click handler, signed S3 polling, bucket name
- [x] RONE CCC worker updated with project context, deployed to K8s
- [x] Session orchestrator Lambda deployed and tested

## Phase 6: Spec Kit + GSD Integration [IN PROGRESS]

Spec-driven development: dispatcher generates specs, workers enforce with GSD gates.

### Spec Kit install
- [x] `specify` CLI installed locally via `uv tool install`
- [x] Spec Kit slash commands scaffolded in `.claude/commands/speckit.*.md`
- [x] Integration spec written at `.specs/speckit-gsd-integration/`

### Worker GSD enforcement
- [x] `gsd-gate.js` added to `claude-portable/config/claude-defaults/hooks/run-modules/PreToolUse/`
- [x] Worker settings.json updated — PreToolUse hooks now cover Bash, Task, WebFetch (in addition to Edit, Write)
- [x] Worker CLAUDE.md updated with spec-driven workflow instructions

### Dispatcher spec generation
- [x] `spec-generate.sh` — generates `.specs/` + `.planning/config.json` from raw task text using `claude -p`
- [x] `git-dispatch.py` updated — generates spec locally, SCPs to worker, modifies prompt to reference spec
- [x] Fallback: if spec generation fails, dispatches raw task (no blocking)
- [x] `SPEC_KIT_ENABLED=0` env var to disable spec generation

### Docker image
- [x] `uv` added to Dockerfile (for spec-kit and general Python tooling)

### Deployment
- [ ] Build updated Docker image with uv + GSD hooks
- [ ] Deploy to dispatcher + workers
- [ ] End-to-end test: bridge task -> spec generated -> worker implements with GSD -> PR

## Deferred (post-demo)
- [ ] `inf-03-tenant-pool` — V1 tenant pool
- [ ] `inf-05-load-tests` — Load testing
- [x] `ana-04-html-report` — HTML report renderer built (`render-report.js`), integrated into pipeline-run.js step 5
- [x] `inf-00-worker-enforcement` — Worker convention enforcement (DONE: GSD gate + spec-kit integration)
- [ ] `aud-03-s3-upload` — Audio S3 upload (may be covered by aud-01)
