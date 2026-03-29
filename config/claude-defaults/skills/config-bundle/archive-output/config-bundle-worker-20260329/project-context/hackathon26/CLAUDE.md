# Hackathon 2026 — Coordination Workspace

Joel's workspace for connecting hackathon infrastructure across 5 repos. No feature code belongs here.

## Deadline
**Wednesday, April 1, 2026.** Working demo or nothing.

## The Product — BoothApp

AI-powered trade show demo capture. Visitor walks up to booth, SE demos Vision One, system records everything, Claude generates personalized follow-up.

1. SE takes badge photo (Android app) -> OCR -> session ID created
2. Session starts on demo PC: Chrome extension tracks clicks + takes screenshots, mic records audio
3. SE demos Vision One (or any web product)
4. SE taps "End Session" on phone
5. Data uploads to S3: audio, clicks, screenshots, metadata
6. Watcher detects completed session -> transcribes audio (AWS Transcribe) -> correlates timeline -> Claude analyzes
7. Output: personalized summary with what was shown, visitor interests, follow-up recommendations

## Project Map

| Project | Local Dir | GitHub Repo | Account | Purpose |
|---------|-----------|-------------|---------|---------|
| **hackathon26** | `hackathon26/` | joel-ginsberg_tmemu/hackathon26 | tmemu | This repo. Coordination, scripts, K8s manifests, docs. |
| **rone-teams-poller** | `rone-teams-poller/` | joel-ginsberg_tmemu/rone-teams-poller | tmemu | RONE K8s: polls Teams chat, classifies messages, routes to CCC. |
| **claude-portable** | `claude-portable/` | grobomo/claude-portable | grobomo | AWS CCC fleet: Dockerfile, dispatcher, worker scripts, CloudFormation. |
| **boothapp** | `boothapp/` | altarr/boothapp | grobomo (altarr org) | The actual product. Chrome extension, audio recorder, analysis pipeline, infra. |
| **RONE-boothapp-bridge** | `rone-boothapp-bridge/` | joel-ginsberg_tmemu/RONE-boothapp-bridge | tmemu | Git relay repo. Task requests flow pending -> dispatched -> completed. |

**Note:** `ccc-rone-bridge/` is an old local clone of the same bridge repo (GitHub renamed it from `ccc-rone-bridge` to `RONE-boothapp-bridge`; redirect still works). Both dirs have identical content. Canonical name is `RONE-boothapp-bridge`.

## Architecture — Two CCC Systems

Two independent Claude Code Computer (CCC) systems. Same concept, completely separate infrastructure.

### RONE CCC (Teams chat intelligence)
- **Platform:** Internal K8s (RONE Elastic Runtime), namespace `joelg-hackathon-teams-poller`
- **Components:** Poller container + CCC worker sidecar in one Deployment, sharing a PVC
- **Code:** `rone-teams-poller/k8s/` (deployment.yaml, poller-script.py, ccc-worker-script.py)
- **What it does:** Polls Teams chat every 5s via Graph API. Caches messages in rolling window. Submits to worker sidecar for LLM classification (Haiku). Routes results:
  - **REPLY** — bot/status questions: worker answers via Anthropic API, poller posts reply to Teams
  - **RELAY** — code tasks: poller pushes to RONE-boothapp-bridge git repo for AWS CCC
  - **IGNORE** — regular chat: cached, no action
- **Bridge:** PVC filesystem at `/data/rone-bridge/` (no git, both containers access directly)
- **Identity:** Outbound messages signed as "Coconut (Joel's AI assistant)" with palm tree emoji

### AWS CCC (boothapp feature development)
- **Platform:** EC2 spot instances in AWS account 752266476357 (us-east-1)
- **Components:** 1 dispatcher + 4 workers, each running Claude Code in Docker
- **Code:** `claude-portable/` (Dockerfile, docker-compose, scripts/git-dispatch.py, CloudFormation)
- **What it does:** Dispatcher polls RONE-boothapp-bridge git repo every 30s. Picks up pending tasks, SSHs to idle worker, runs `claude -p` with the task. Worker branches, codes, PRs against `altarr/boothapp`.
- **Bridge:** Git repo `joel-ginsberg_tmemu/RONE-boothapp-bridge` (dispatcher needs tmemu token to pull; workers need grobomo token for altarr/boothapp)
- **Fleet IPs:** Dispatcher 18.224.39.180, workers 3.21.228.154, 13.59.160.30 (account 752266476357, us-east-2, CF stacks: ccc-dispatcher, ccc-worker-1, ccc-worker-2)

### Data Flow
```
Teams chat ("Smells Like Machine Learning")
  |
  v
RONE poller (K8s) --- REPLY ---> RONE CCC worker (K8s sidecar) ---> Teams reply
  |
  | RELAY (@claude code tasks)
  v
RONE-boothapp-bridge (git repo)
  |
  v
AWS CCC dispatcher (EC2) ---> picks idle worker ---> SSH + claude -p
  |
  v
Worker branches, codes, PRs against altarr/boothapp
  |
  v
Result written to bridge completed/ ---> RONE poller posts to Teams
```

## What's Been Built (as of 2026-03-29)

### boothapp (altarr/boothapp) — 12 PRs merged to main
| Component | Directory | Key Files | What It Does |
|-----------|-----------|-----------|-------------|
| Chrome extension | `extension/` | background.js, content.js, manifest.json | Click tracking (DOM paths + coords), silent screenshots on every click, session start/stop via S3 polling |
| Audio recorder | `audio/` | recorder.js, lib/device-detect.js, lib/ffmpeg-recorder.js | Session-triggered ffmpeg capture from USB mic, auto-detect device, graceful stop |
| Transcriber | `audio/transcriber/` | index.js, transcribe.js, convert.js, upload.js | WAV -> MP3 conversion, S3 upload, AWS Transcribe job, poll for result |
| Session orchestrator | `infra/session-orchestrator/` | orchestrator.js, index.js (Lambda handler), s3.js, tenant-pool.js | Lambda: create/end sessions, write metadata.json + commands to S3, claim V1 tenant |
| Shared config | `infra/` | config.js, config.py | Single source of truth for S3 bucket name, region, session paths |
| S3 storage | `infra/` | s3-session-storage.yaml | CloudFormation: S3 bucket with lifecycle policies |
| Session watcher | `analysis/` | watcher.js, lib/s3.js, lib/pipeline.js | Polls S3 every 30s for completed sessions, claims + triggers analysis |
| Correlator | `analysis/` | lib/correlator.js | Merges click timestamps + transcript timestamps into unified timeline.json |
| Claude analysis | `analysis/` | analyze.py, engines/analyzer.py, engines/claude_client.py, engines/prompts.py | Two-pass analysis: factual extraction then contextual recommendations |
| Pipeline runner | `analysis/` | pipeline-run.js | Orchestrates: fetch S3 data -> correlate -> write timeline -> run analyze.py |

### AWS Infrastructure (deployed)
- S3 bucket: `boothapp-sessions-752266476357` (CloudFormation stack)
- Lambda: `boothapp-session-orchestrator` (Function URL exists but blocked by account SCP — use direct invoke)
- Watcher: NOT yet deployed to EC2 (runs via `S3_BUCKET=boothapp-sessions-752266476357 node analysis/watcher.js`)

### RONE Infrastructure (deployed)
- Deployment: `teams-poller` (1 replica, 2 containers: poller + ccc-worker)
- PVC: `teams-poller-data` (1Gi at /data/)
- Secrets: `teams-poller-graph-token`, `claude-api-key`
- ConfigMaps: `teams-poller-script`, `ccc-worker-script`
- Kubeconfig: 8h TTL, download from RONE portal -> org 216 -> hackathon-teams-poller

## S3 Data Contract

All components communicate through S3 session folders. No direct dependencies.
```
sessions/<session-id>/
  metadata.json          # Android app creates (session_id, visitor_name, status, timestamps)
  badge.jpg              # Android app uploads
  audio/recording.wav    # Audio recorder uploads on session end
  transcript/transcript.json  # Transcriber writes after AWS Transcribe completes
  clicks/clicks.json     # Chrome extension uploads on session end
  screenshots/click-001.jpg, click-002.jpg, ...  # Chrome extension uploads
  commands/start.json, end.json  # Orchestrator writes, demo PC polls
  output/summary.json, summary.html, follow-up.json  # Analysis pipeline writes
  v1-tenant/tenant.json  # Orchestrator writes (tenant URL, creds, expiry)
```

## What Lives in This Repo

```
hackathon26/
  CLAUDE.md               # This file
  TODO.md                 # Task tracking across all projects
  .claude/rules/          # Claude Code rules for this workspace
  .github/                # publish.json (tmemu), secret-scan workflow
  config/                 # Kubeconfigs (gitignored)
  k8s/                    # CCC pod manifest for RONE namespace
  scripts/
    deploy-aws.sh         # CloudFormation deploy
    test-e2e.sh           # End-to-end pipeline test with sample data
    fleet-bootstrap.sh    # Push OAuth creds to workers, register with dispatcher
    fleet-status.sh       # Check dispatcher/worker/bridge health
    relay-submit.py       # Submit tasks to CCC via bridge.py
    test-bridge.py        # Bridge client connectivity test
    team-chat.py          # Send messages as Coconut to hackathon Teams chat
  archive/                # Stale files (gitignored)
```

## What Does NOT Belong Here
- Feature code (extension, audio, analysis) -> altarr/boothapp
- Poller/worker K8s scripts -> rone-teams-poller
- CCC Dockerfile, dispatcher, bootstrap -> claude-portable
- Bridge task files -> RONE-boothapp-bridge

## AWS
- **Account:** 752266476357 (Casey's)
- **Region:** us-east-1
- **Profile:** `hackathon` (creds in OS credential store)

## Team — "Smells Like Machine Learning"

| Name | Role | Focus |
|------|------|-------|
| Casey Mondoux | MKT-NA | Android app, web interface, presentation |
| Joel Ginsberg | TS-NA | Infrastructure (CCC fleet, RONE poller, AWS) |
| Tom Gamull | SE-NA | Unavailable (wedding) |
| Kush Mangat | SE-NA | Presentation, demo |
| Chris LaFleur | BD-NA | V1 tenants, presentation, demo |

## Teams Chat
- **Group:** "Smells Like Machine Learning"
- **Chat ID:** `19:cf504fc638964747bff028e4ba785869@thread.v2`
- **Read:** `python C:/Users/joelg/Documents/ProjectsCL1/rone-teams-poller/scripts/read_latest.py --hours 24`
- **Send (as Coconut):** `python scripts/team-chat.py "message"`

## Authorized Actions
- Message Teams group chat "Smells Like Machine Learning" (as Coconut, not Joel)
- Send email / schedule meetings for hackathon team members only
- Disclosure required: always identify as Claude acting on Joel's behalf

## GitHub
- **boothapp:** `gh auth switch --user grobomo` (altarr org)
- **hackathon26, rone-teams-poller, bridge:** `gh auth switch --user joel-ginsberg_tmemu`
