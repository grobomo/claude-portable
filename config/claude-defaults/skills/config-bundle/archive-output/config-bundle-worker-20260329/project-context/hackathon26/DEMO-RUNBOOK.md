# BoothApp Demo Day Runbook

**Date:** Wednesday, April 1, 2026
**Team:** Smells Like Machine Learning

## Pre-Demo Checklist (Joel — morning of)

### 1. Run Automated Preflight Check
```bash
# From Joel's laptop — checks everything in 90 seconds
bash scripts/demo-day-runbook.sh

# Shows PASS/WARN/FAIL for each component with fix instructions
# If dispatcher is down, restore everything:
bash scripts/dispatcher-restore.sh
```

### 2. Refresh OAuth Tokens
```bash
# 1. Open Claude Code, accept OAuth prompt (browser opens, click Allow)
# 2. Copy fresh credentials to dispatcher:
ssh -i ~/.ssh/ccc-keys/claude-portable-key.pem ubuntu@18.224.39.180 \
  "docker exec claude-portable bash -c 'cat /tmp/oauth-creds.json'"
# If stale, push fresh ones:
# scp local creds -> dispatcher /tmp/oauth-creds.json
# Cred-refresh daemon auto-pushes to workers every 4h
```

### 3. Verify Dashboard
- Open https://18.224.39.180/
- All 4 cards should show green dots
- If stale: `bash scripts/dispatcher-restore.sh`

### 4. Verify Watcher
```bash
ssh -i ~/.ssh/ccc-keys/claude-portable-key.pem ubuntu@18.224.39.180 \
  "docker exec claude-portable tail -5 /tmp/watcher.log"
# Should show "Checking N session(s)..." every 30s
```

### 5. Verify S3 Bucket
```bash
aws s3 ls s3://boothapp-sessions-752266476357/sessions/ --profile hackathon --region us-east-1
# Should list existing test sessions (FULL-775860, PD8MITZ0, etc.)
```

## Demo Setup (at the booth)

### Demo PC Requirements
- Chrome browser
- Node.js 18+ installed
- USB microphone connected
- Network access to AWS (us-east-1)

### Install Chrome Extension
1. Clone boothapp: `git clone https://github.com/altarr/boothapp.git`
2. Open Chrome -> `chrome://extensions/`
3. Enable "Developer mode" (top right toggle)
4. Click "Load unpacked" -> select `boothapp/extension/`
5. V1-Helper icon should appear in toolbar

### Start Audio Recorder
```bash
cd boothapp/audio
npm install  # first time only
node recorder.js
# Listens for session start/end signals from S3
# Automatically starts/stops recording when session is active
```

### Configure V1 Tenant (Chris)
- Pre-load a V1 trial tenant
- Log in to `https://portal.xdr.trendmicro.com` on the demo PC
- Keep the browser tab open — extension tracks clicks here

## Running a Demo Session

### Step 1: Create Session (Casey — Android App)
- Take visitor badge photo
- App OCRs name, creates session via Lambda
- Lambda writes `sessions/<id>/metadata.json` + `commands/start.json` to S3

### Step 2: Demo Starts Automatically
- Chrome extension polls S3, detects `start.json`
- Extension starts tracking clicks and taking screenshots
- Audio recorder detects active session, starts recording
- SE demonstrates Vision One naturally

### Step 3: End Session (Casey — Android App)
- Tap "End Session"
- Lambda writes `commands/end.json` to S3
- Chrome extension stops, uploads `clicks/clicks.json` + `screenshots/`
- Audio recorder stops, uploads `audio/recording.wav`

### Step 4: Analysis (Automatic)
- Audio transcriber converts WAV -> MP3 -> AWS Transcribe -> `transcript/transcript.json`
- Watcher on dispatcher detects completed session (metadata + clicks + transcript)
- Pipeline: correlate timeline -> Claude analysis (Bedrock Sonnet) -> HTML report
- Output: `output/summary.json`, `output/summary.html`, `output/follow-up.json`

### Step 5: Show Results
- Download report: `aws s3 cp s3://boothapp-sessions-752266476357/sessions/<id>/output/summary.html . --profile hackathon --region us-east-1`
- Open `summary.html` in browser — dark-themed, personalized follow-up

## Fallback: Rich Sample Session

If the live demo flow breaks entirely, upload a pre-built realistic session:
```bash
bash scripts/demo-fallback.sh
# Uploads: Sarah Mitchell from GlobalTech, 7 clicks, 24 dialogue entries
# Watcher auto-detects within 30s and runs full pipeline
```

## Manual Session (Fallback — No Android App)

If the Android app isn't ready, create sessions manually:

```bash
# Create session
SESSION_ID="DEMO-$(date +%s | tail -c 7)"
aws lambda invoke --function-name boothapp-session-orchestrator \
  --payload "{\"action\":\"create\",\"visitor_name\":\"Mark Chen\",\"se_name\":\"Demo SE\"}" \
  --profile hackathon --region us-east-1 /dev/stdout

# Or direct S3 upload:
echo '{"session_id":"'$SESSION_ID'","visitor_name":"Mark Chen","status":"active","started_at":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}' | \
  aws s3 cp - s3://boothapp-sessions-752266476357/sessions/$SESSION_ID/metadata.json \
  --profile hackathon --region us-east-1

# End session (update status to completed)
echo '{"session_id":"'$SESSION_ID'","visitor_name":"Mark Chen","status":"completed","started_at":"...","ended_at":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}' | \
  aws s3 cp - s3://boothapp-sessions-752266476357/sessions/$SESSION_ID/metadata.json \
  --profile hackathon --region us-east-1
```

## Troubleshooting

### Chrome Extension Not Tracking Clicks
- Check `chrome://extensions/` -> V1-Helper -> "Inspect views: service worker" for errors
- Verify extension has access to the page (host_permissions: `<all_urls>`)
- Extension polls `commands/start.json` from S3 — verify it exists

### Watcher Not Picking Up Sessions
```bash
# Check watcher log
ssh -i ~/.ssh/ccc-keys/claude-portable-key.pem ubuntu@18.224.39.180 \
  "docker exec claude-portable tail -30 /tmp/watcher.log"

# Session needs ALL THREE files to trigger:
#   metadata.json (status: completed)
#   clicks/clicks.json
#   transcript/transcript.json
```

### Analysis Fails
```bash
# Check for Bedrock access
ssh -i ~/.ssh/ccc-keys/claude-portable-key.pem ubuntu@18.224.39.180 \
  "docker exec claude-portable bash -c 'AWS_REGION=us-east-1 python3 -c \"import boto3; c=boto3.client(\\\"bedrock-runtime\\\",region_name=\\\"us-east-1\\\"); print(\\\"Bedrock OK\\\")\"'"

# Env vars needed on watcher:
#   USE_BEDROCK=1
#   ANALYSIS_MODEL=us.anthropic.claude-sonnet-4-6
#   S3_BUCKET=boothapp-sessions-752266476357
#   AWS_REGION=us-east-1
```

### Workers Not Responding
```bash
# Re-register workers
bash scripts/dispatcher-restore.sh

# Push fresh OAuth
# (get fresh creds from local Claude Code session, push to dispatcher)
```

### Dashboard Not Loading
```bash
# Check socat relay
ssh -i ~/.ssh/ccc-keys/claude-portable-key.pem ubuntu@18.224.39.180 "pgrep -af socat"

# Restart if needed
CONTAINER_IP=$(ssh -i ~/.ssh/ccc-keys/claude-portable-key.pem ubuntu@18.224.39.180 \
  "docker inspect claude-portable --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'")
ssh -i ~/.ssh/ccc-keys/claude-portable-key.pem ubuntu@18.224.39.180 \
  "nohup socat TCP-LISTEN:8081,fork,reuseaddr TCP:${CONTAINER_IP}:8082 > /dev/null 2>&1 &"
```

## Key URLs and IPs
| Resource | Location |
|----------|----------|
| Dashboard | https://18.224.39.180/ |
| S3 Bucket | boothapp-sessions-752266476357 (us-east-1) |
| Dispatcher | 18.224.39.180 (SSH key: ~/.ssh/ccc-keys/claude-portable-key.pem) |
| Worker 1 | 3.21.228.154 |
| Worker 2 | 13.59.160.30 |
| Teams Chat | "Smells Like Machine Learning" |
| boothapp repo | github.com/altarr/boothapp |
