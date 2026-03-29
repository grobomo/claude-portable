# Quickstart: Testing Spec Kit + GSD Integration

## Prerequisites

- SSH access to dispatcher (18.224.39.180) and workers (3.21.228.154, 13.59.160.30)
- SSH key at `~/.ssh/ccc-keys/claude-portable-key.pem`
- Bridge client: `python C:/Users/joelg/Documents/ProjectsCL1/rone-boothapp-bridge/bridge.py`

## Step 1: Verify Dispatcher Has spec-generate.sh

```bash
source scripts/fleet-config.sh
ssh -i $SSH_KEY ubuntu@$DISPATCHER_IP \
  "docker exec claude-portable ls -la /opt/claude-portable/scripts/spec-generate.sh"
```

If missing: `scp` from local `claude-portable/scripts/spec-generate.sh` and `docker cp` in.

## Step 2: Verify Workers Have GSD Hooks

```bash
for ip in $WORKER_IPS; do
  echo "--- $ip ---"
  ssh -i $SSH_KEY ubuntu@$ip \
    "docker exec claude-portable cat /home/claude/.claude/hooks/run-modules/PreToolUse/gsd-gate.js" 2>/dev/null | head -3
  ssh -i $SSH_KEY ubuntu@$ip \
    "docker exec claude-portable cat /home/claude/.claude/settings.json" 2>/dev/null | python3 -m json.tool
done
```

## Step 3: Verify Dispatcher Has ANTHROPIC_API_KEY

```bash
ssh -i $SSH_KEY ubuntu@$DISPATCHER_IP \
  "docker exec claude-portable env | grep ANTHROPIC_API_KEY | cut -c1-30"
```

Should show `ANTHROPIC_API_KEY=sk-ant-...` (first 30 chars).

## Step 4: Submit a Test Task

```bash
python C:/Users/joelg/Documents/ProjectsCL1/rone-boothapp-bridge/bridge.py \
  submit "Add a health check endpoint to analysis/watcher.js that returns 200 OK on GET /health"
```

## Step 5: Watch Dispatcher Logs

```bash
ssh -i $SSH_KEY ubuntu@$DISPATCHER_IP \
  "docker logs -f claude-portable 2>&1 | grep -i 'spec\|relay\|RELAY'"
```

Expected log sequence:
1. `RELAY <id>: generating spec locally...`
2. `[spec-generate] Phase 1/3: Specify...`
3. `[spec-generate] Phase 2/3: Plan...`
4. `[spec-generate] Phase 3/3: Tasks...`
5. `RELAY <id>: spec generated locally at /tmp/spec-<id>`
6. `RELAY <id>: spec artifacts copied to worker`
7. `RELAY <id> completed by <worker>`

## Step 6: Verify Worker Used GSD

After task completes, check the worker:

```bash
ssh -i $SSH_KEY ubuntu@$WORKER_IP \
  "docker exec claude-portable find /workspace/boothapp/.planning -type f 2>/dev/null"
```

Should show:
- `.planning/config.json`
- `.planning/quick/001-<slug>/001-PLAN.md`
- `.planning/quick/001-<slug>/001-SUMMARY.md` (if worker completed verification)

## Step 7: Check PR

```bash
gh pr list --repo altarr/boothapp --state open --limit 5
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "spec-generate.sh not found" in logs | Script not deployed | Rebuild image or docker cp |
| Spec phase timeout | Claude API slow / token limit | Increase SPEC_TIMEOUT env var |
| Worker produces code without PLAN.md | GSD hooks not registered | Check settings.json hook entries |
| SCP fails to worker | Worker IP changed | Update fleet-config.sh, re-register |
| "no idle worker" | Workers stuck busy | Re-register via dispatcher /worker/register |
