# Event-Driven Observability and Hook-Runner Parity

## Problem

CCC workers and local Claude Code run different enforcement systems. Locally, `grobomo/hook-runner` provides modular gates (enforcement-gate, secret-scan-gate, branch-pr-gate, etc.) configured via `modules.yaml`. Workers get a different set of legacy hooks from `grobomo/claude-code-defaults/hooks/`. This means workers lack guardrails that prevent drift, bad commits, and wasted cycles.

Separately, worker visibility is built on fragile probes: `worker-agent.py` uses `pgrep`, `/proc` reads, file mtime checks, and git commands to reconstruct what Claude is doing. This approach can't determine which pipeline stage is active, what tool Claude just ran, or whether Claude is stuck vs. thinking.

## How Workers Actually Work

Understanding this is critical to the design:

1. `continuous-claude.sh` picks a task from TODO.md
2. It calls `claude --print --dangerously-skip-permissions` with a stage prompt
3. Claude runs for 5-10 minutes, calling tools (Bash, Edit, Write, etc.) — **hooks fire on every tool call**
4. Claude stops. The Stop hook fires.
5. continuous-claude.sh checks the result, moves to next stage or retries
6. Repeat from step 2

**Key insight:** `--dangerously-skip-permissions` skips permission prompts but hooks still fire. A PostToolUse async hook sees every tool call during the entire Claude run. This gives fine-grained visibility without blocking anything.

## Solution

### 1. Event Log

Append-only JSONL at `/data/events.jsonl`. Three sources write to it:

**Source A: PostToolUse async hook** (fires every few seconds during active Claude work)
```json
{"ts":"2026-04-09T14:30:05Z","event":"tool.used","source":"hook-runner","tool":"Bash","command":"git diff --staged","worker_id":"ccc-worker-1","task_id":"task-5","stage":"IMPLEMENT"}
```

**Source B: Stop hook** (fires every 5-10 min when Claude stops)
```json
{"ts":"2026-04-09T14:35:00Z","event":"claude.stopped","source":"hook-runner","worker_id":"ccc-worker-1","task_id":"task-5","stage":"IMPLEMENT","detail":"auto-continuing"}
```

**Source C: continuous-claude.sh** (fires at task/stage transitions)
```json
{"ts":"2026-04-09T14:35:05Z","event":"stage.entered","source":"continuous-claude","worker_id":"ccc-worker-1","task_id":"task-5","stage":"VERIFY"}
```

**All event types:**

| Event | Source | When | Frequency |
|-------|--------|------|-----------|
| `tool.used` | PostToolUse async hook | Every tool call | Every few seconds |
| `claude.stopped` | Stop hook | Claude exits | Every 5-10 min |
| `worker.started` | bootstrap.sh | Container boot | Once |
| `worker.idle` | continuous-claude | No tasks remaining | Rare |
| `task.started` | continuous-claude | Task picked from TODO.md | Per task |
| `task.completed` | continuous-claude | PR merged | Per task |
| `task.failed` | continuous-claude | Task aborted | Per task |
| `stage.entered` | continuous-claude | Pipeline stage begins | Per stage |
| `stage.completed` | continuous-claude | Pipeline stage finished | Per stage |
| `stage.failed` | continuous-claude | Stage failed | Per stage |
| `pr.created` | continuous-claude | PR opened | Per task |
| `pr.merged` | continuous-claude | PR merged | Per task |
| `error` | any | Unexpected error | Rare |

**Schema:** Every event has `ts`, `event`, `source`, `worker_id`. Optional fields: `task_id`, `stage`, `tool`, `command`, `detail`, `exit_code`.

**Log rotation:** Rotate at 10MB. Keep current + 1 previous. Both emitters (JS and bash) handle rotation before each write.

**Local vs. remote:** On workers, `CLAUDE_EVENT_LOG=/data/events.jsonl` (set in bootstrap.sh, always — not optional). Locally, event emission is disabled by default (no `CLAUDE_EVENT_LOG` set = emitter is a no-op). Local users don't need a growing file nobody reads.

### 2. Hook-Runner as Component

Add `grobomo/hook-runner` to `components.yaml`. Workers pull it at boot and use the same gates as local.

**sync-config.sh** handles the new `hook-runner` component type:
1. Clone `grobomo/hook-runner` to cache
2. Copy runner scripts, modules, config to `~/.claude/hooks/`
3. Skip `archive/`, `.test-*`, `specs/`, `scripts/test/`, docs
4. Run `npm install --production` if `package.json` present

**settings.json hook wiring:** Merge (not replace) hook entries into settings.json. Read existing hooks, add hook-runner entries for any event type not already configured. This preserves custom hooks while adding hook-runner.

```json
{
  "hooks": {
    "PreToolUse": [{"type": "command", "command": "node /home/claude/.claude/hooks/run-pretooluse.js"}],
    "PostToolUse": [{"type": "command", "command": "node /home/claude/.claude/hooks/run-posttooluse.js"}],
    "Stop": [{"type": "command", "command": "node /home/claude/.claude/hooks/run-stop.js"}],
    "UserPromptSubmit": [{"type": "command", "command": "node /home/claude/.claude/hooks/run-userpromptsubmit.js"}],
    "SessionStart": [{"type": "command", "command": "node /home/claude/.claude/hooks/run-sessionstart.js"}]
  }
}
```

**Container modules.yaml:** An overlay file (`config/modules-container.yaml`) specifies which modules to **add or remove** from the upstream `modules.yaml`. Merge semantics are explicit:

```yaml
# config/modules-container.yaml
# Explicit add/remove lists — no ambiguity about array merge behavior
remove:
  PreToolUse:
    - env-var-check           # container env set by bootstrap, not .env
    - remote-tracking-gate    # continuous-claude pushes explicitly
add:
  PostToolUse:
    - tool-event-emitter      # async: emit tool.used events to event log
  Stop:
    - status-emitter          # emit claude.stopped event to event log
```

The merge script reads upstream `modules.yaml`, applies removes, applies adds, writes result. No ambiguity.

**Deployment order:** `event-emitter.js` must be pushed to `grobomo/hook-runner` BEFORE workers are deployed. sync-config.sh clones at boot — if the file isn't in the repo yet, the tool-event-emitter module will fail gracefully (no crash, just no events). Fallback: if `event-emitter.js` is not found, the emitter modules log a warning and become no-ops.

### 3. PostToolUse Async Hook: tool-event-emitter

A new hook-runner module at `modules/PostToolUse/tool-event-emitter.js`:

- Runs async (doesn't block Claude)
- Reads tool name and command from hook input (stdin JSON)
- Calls `emit({ event: 'tool.used', tool, command })`
- Includes `task_id` and `stage` from env vars (set by continuous-claude.sh)
- Truncates `command` at 200 chars to keep events readable

This is the primary heartbeat signal. During active Claude work, this fires every few seconds.

### 4. Stop Hook: status-emitter

A new hook-runner module at `modules/Stop/status-emitter.js`:

- Runs alongside existing `auto-continue` module
- Emits `claude.stopped` event with current task_id, stage, and stop reason
- This is the coarse-grained checkpoint — fires every 5-10 min

### 5. Event Emission from continuous-claude.sh

Shell helper `scripts/emit-event.sh` provides `emit_event <type> [detail]`. continuous-claude.sh sources it and calls at:
- Task pickup (`task.started`)
- Stage enter/complete/fail (`stage.*`)
- PR create/merge (`pr.*`)
- Task complete/fail (`task.*`)
- Idle (`worker.idle`)

These are the structural events. Combined with `tool.used` and `claude.stopped`, they give a complete picture.

### 6. Worker-Agent Redesign

Replace process/file probing with event log tailing:

**Input:** Tail `/data/events.jsonl` (poll every 5s)

**Derived state (`/data/status.json`):**

```json
{
  "worker_id": "ccc-worker-1",
  "updated_at": "2026-04-09T14:30:00Z",
  "state": "working",
  "task_id": "task-5",
  "stage": "IMPLEMENT",
  "stage_entered_at": "2026-04-09T14:25:00Z",
  "time_in_stage_s": 300,
  "last_tool": "Bash: git diff --staged",
  "last_tool_at": "2026-04-09T14:30:05Z",
  "last_stop_at": "2026-04-09T14:25:00Z",
  "tools_last_5min": 42,
  "stuck": false,
  "stuck_reason": null,
  "tasks_completed": 3,
  "tasks_failed": 0,
  "uptime_s": 7200,
  "last_pr_url": "https://github.com/grobomo/claude-portable/pull/78"
}
```

**Two-tier stuck detection:**

| Condition | Threshold | Meaning |
|-----------|-----------|---------|
| No `tool.used` events for 5 min | Claude is stuck | Claude should fire tools every few seconds during active work |
| No `claude.stopped` events for 20 min | Loop is stuck | Claude should stop and restart every 5-10 min |

**Self-healing:**
- Claude stuck (no tools 5 min): kill Claude process (`pkill -f "claude --print"`), write `error` event, continuous-claude.sh will retry the stage
- Loop stuck (no stops 20 min): kill Claude, write `task.failed` event, continuous-claude.sh will move to next task
- 3+ stuck events in 1 hour: set state to `unhealthy`, write `worker.unhealthy` event

**Backward compatibility:** HTTP endpoints stay at same paths (`/status`, `/health`) but serve derived state. `ccc dashboard` (SSH-based) still works as fallback. Heartbeat to dispatcher (if configured) populated from derived state.

### 7. S3 Status Sync

Worker-agent uploads:
- `/data/status.json` -> `s3://bucket/fleet/{worker_id}/status.json` every 30s
- `/data/events.jsonl` -> `s3://bucket/fleet/{worker_id}/events.jsonl` every 5 min

Readable from anywhere without SSH.

### 8. ccc watch

Reads S3 status files. No SSH.

```
ccc watch              # Fleet overview, 10s refresh
ccc watch worker-1     # Single worker + recent events, 5s refresh
ccc watch --once       # Print once, exit
```

Fleet view:
```
CCC Fleet Watch  2026-04-09 14:30:00 UTC

 WORKER     STATE    TASK    STAGE       TIME   LAST TOOL              ALERT
 worker-1   WORKING  task-5  IMPLEMENT   5m     Bash: git diff
 worker-2   WORKING  task-6  VERIFY      2m     Bash: pytest
 worker-3   IDLE     --      --          --     --
 worker-4   STUCK    task-7  PLAN        22m    Edit: spec.md (5m ago) !!!
```

## Key Decisions

1. **PostToolUse async hook is the heartbeat.** Not gate events, not sampling — actual tool calls. Fires constantly during active work, goes silent when stuck. Clean signal.

2. **Two-tier stuck detection.** 5 min no tools = Claude stuck. 20 min no stops = loop stuck. Based on how workers actually work (5-10 min Claude runs, tools every few seconds).

3. **Local event emission off by default.** `CLAUDE_EVENT_LOG` unset = no-op. Workers set it in bootstrap. Local users don't get a growing file nobody reads.

4. **Merge, not replace, for settings.json and modules.yaml.** Settings.json: add hook-runner entries for events not already configured. modules.yaml: explicit add/remove lists, no ambiguous array merge.

5. **Graceful fallback for cross-repo dependency.** If `event-emitter.js` isn't in hook-runner yet when a worker boots, emitter modules become no-ops. No crash.

6. **JSONL append-only.** Simplest possible format. Rotation at 10MB keeps disk bounded. S3 sync for durability.

## Success Criteria

1. Workers use hook-runner gates from `modules.yaml` after bootstrap
2. PostToolUse async hook emits `tool.used` events during `claude --print` runs
3. Stop hook emits `claude.stopped` events when Claude exits
4. `continuous-claude.sh` emits task/stage lifecycle events
5. `worker-agent.py` derives status from events only (no pgrep/proc)
6. No `tool.used` for 5 min triggers stuck detection
7. No `claude.stopped` for 20 min triggers loop-stuck detection
8. `status.json` synced to S3, readable via `ccc watch`
9. `CLAUDE_EVENT_LOG` unset locally = emitter is no-op (no side effects)
10. Event log stays under 20MB with rotation

## Out of Scope

- Dashboard HTML (separate spec at `specs/monitoring-dashboard/`)
- Dispatcher changes
- Historical analytics
- External event forwarding
