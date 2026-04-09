# Event-Driven Observability -- Tasks

## Dependency Graph

```
Feature A (event-log)              Feature B (hook-runner-component)
  T01 emitters (JS + bash)           T05 components.yaml entry
  T02 tool-event-emitter module      T06 sync-config handler
  T03 status-emitter module          T07 settings.json hook wiring
  T04 cc.sh event emission           T08 container modules.yaml

Feature C (worker-agent-redesign)  Feature D (ccc-watch)
  T09 event-tail status derivation   T12 ccc watch fleet view
  T10 stuck detection + self-heal    T13 ccc watch single worker
  T11 S3 status sync
```

```
T01 ──> T02 ──> T04
    ──> T03
    ──> T09 ──> T10 ──> T11 ──> T12 ──> T13
T05 ──> T06 ──> T07 ──> T08
T01 + T07 ──> T02, T03  (emitter modules need both event-emitter.js and hook wiring)
```

Feature A and B can start in parallel (T01 and T05 are independent).
Feature C needs T01. Feature D needs T11.

---

## Feature A: Event Log Foundation

**Branch prefix:** `feat/event-log-`

- [ ] T01: Event emitter (JS module + bash helper)
  - What: `event-emitter.js` in hook-runner repo, `scripts/emit-event.sh` in claude-portable
  - Why: No structured event stream exists. Both JS hooks and bash scripts need to write events
  - How: JS `emit({event, ...})` appends JSONL to `$CLAUDE_EVENT_LOG`. No-op if env var unset. Bash `emit_event <type> [detail]` does same. Both handle 10MB rotation before each write
  - Acceptance: On worker (CLAUDE_EVENT_LOG set): valid JSONL appended. Locally (unset): no file created, no error
  - PR title: "feat: add event-emitter.js and shell emit_event helper"

- [ ] T02: PostToolUse async hook -- tool-event-emitter module
  - What: `modules/PostToolUse/tool-event-emitter.js` in hook-runner
  - Why: This is the primary heartbeat. Every tool call = proof Claude is alive and working
  - How: Async module reads tool name + command from stdin JSON, calls emit with `tool.used` event. Truncates command at 200 chars. Reads CURRENT_TASK_ID and CURRENT_STAGE from env
  - Acceptance: During `claude --print` run, events.jsonl gets `tool.used` entries every few seconds
  - PR title: "feat: PostToolUse async hook emits tool.used events"

- [ ] T03: Stop hook -- status-emitter module
  - What: `modules/Stop/status-emitter.js` in hook-runner
  - Why: Coarse-grained checkpoint every 5-10 min when Claude stops. Confirms the loop is alive
  - How: Emits `claude.stopped` event with task_id, stage, stop reason. Runs alongside existing auto-continue module
  - Acceptance: When Claude stops, events.jsonl gets a `claude.stopped` entry
  - PR title: "feat: Stop hook emits claude.stopped status events"

- [ ] T04: Emit events from continuous-claude.sh
  - What: Source emit-event.sh in continuous-claude.sh, emit at task/stage/PR transitions
  - Why: Tool events show Claude is alive; stage events show pipeline progress
  - How: `source /opt/claude-portable/scripts/emit-event.sh`. Call emit_event at: task pickup, stage enter/complete/fail, PR create/merge, task complete/fail, idle. Export CURRENT_TASK_ID and CURRENT_STAGE as env vars
  - Acceptance: Run pipeline on test repo, verify `jq '.event' events.jsonl | sort | uniq -c` shows task/stage/pr events
  - PR title: "feat: emit structured events from continuous-claude pipeline"

---

## Feature B: Hook-Runner as Container Component

**Branch prefix:** `feat/hook-runner-`

- [ ] T05: Add hook-runner to components.yaml
  - What: `grobomo/hook-runner` entry in components.yaml, type `hook-runner`
  - Why: Workers need the same gates as local. Currently they get legacy hooks from claude-code-defaults
  - How: Add YAML entry. sync-config doesn't handle this type yet (logs warning, skips)
  - Acceptance: `grep hook-runner components.yaml` matches
  - PR title: "feat: add hook-runner component to manifest"

- [ ] T06: sync-config.sh handler for hook-runner type
  - What: Teach sync-config to clone hook-runner and install into ~/.claude/hooks/
  - Why: Components.yaml entry does nothing without a handler
  - How: Add `hook-runner` case to Python processor. Clone repo, copy runner scripts + modules + config. Skip archive/test/docs. Run npm install if package.json present
  - Acceptance: After sync-config, `ls ~/.claude/hooks/run-pretooluse.js` and `ls ~/.claude/hooks/modules/PreToolUse/` show files
  - PR title: "feat: sync-config handler for hook-runner component type"

- [ ] T07: Merge hook-runner into settings.json
  - What: After installing hook-runner, merge hook entries into settings.json (not replace)
  - Why: Claude won't use hook-runner unless settings.json references the runner scripts
  - How: Read existing settings.json. For each event type (PreToolUse, PostToolUse, Stop, etc.), add hook-runner entry if not already present. Preserve all other keys. Set CLAUDE_EVENT_LOG=/data/events.jsonl in env
  - Acceptance: `jq '.hooks.PreToolUse' ~/.claude/settings.json` shows hook-runner command. Existing custom hooks preserved
  - PR title: "feat: merge hook-runner entries into settings.json"

- [ ] T08: Container modules.yaml overlay
  - What: `config/modules-container.yaml` with explicit add/remove lists
  - Why: Some local gates don't apply in container (env-var-check, remote-tracking-gate). Container needs tool-event-emitter and status-emitter
  - How: Overlay format has `remove:` and `add:` keys per event type. Merge script reads upstream modules.yaml, applies removes, applies adds. No ambiguous array merge
  - Acceptance: Container modules.yaml has tool-event-emitter in PostToolUse, status-emitter in Stop, no env-var-check in PreToolUse
  - PR title: "feat: container modules.yaml with explicit add/remove overlay"

---

## Feature C: Worker-Agent Redesign

**Branch prefix:** `feat/worker-agent-`

- [ ] T09: Event-tailing status derivation
  - What: Rewrite worker-agent.py to derive status from events.jsonl, not pgrep/proc
  - Why: Process probing is fragile, can't determine task/stage, requires SSH
  - How: EventProcessor class tails events.jsonl (poll 5s). Maintains: current task, stage, last tool, timing, event counts. Writes /data/status.json every 30s. HTTP endpoints serve derived state. Remove all pgrep/proc functions
  - Acceptance: GET /status returns correct task/stage/last_tool. Zero pgrep or /proc reads in codebase
  - PR title: "feat: event-driven worker-agent with status.json derivation"

- [ ] T10: Two-tier stuck detection and self-healing
  - What: Detect stuck workers from event gaps, auto-recover
  - Why: Currently no automated stuck detection. Workers can spin for hours unnoticed
  - How: Tier 1: no `tool.used` for 5 min = Claude stuck (kill claude, retry stage). Tier 2: no `claude.stopped` for 20 min = loop stuck (kill claude, fail task). 3+ stucks in 1 hour = unhealthy
  - Acceptance: Simulate 5min tool gap -> stuck detected, Claude killed. Simulate 20min stop gap -> loop-stuck detected
  - PR title: "feat: two-tier stuck detection and self-healing"

- [ ] T11: S3 fleet status sync
  - What: Upload status.json and events.jsonl to S3 periodically
  - Why: Makes worker status readable from anywhere without SSH
  - How: Every 30s: upload status.json to s3://bucket/fleet/{worker_id}/status.json. Every 5min: upload events.jsonl
  - Acceptance: `aws s3 ls s3://bucket/fleet/` shows per-worker files updating
  - PR title: "feat: S3 fleet status sync from worker-agent"

---

## Feature D: CCC Watch Command

**Branch prefix:** `feat/ccc-watch-`

- [ ] T12: ccc watch fleet overview
  - What: New ccc subcommand, reads S3 status files, renders fleet table
  - Why: Current dashboard needs SSH. Watch reads S3 (fast, works from phone)
  - How: List s3://bucket/fleet/, download status.json per worker, render table. 10s refresh. --once for scripting. Color: green=WORKING, red=STUCK, gray=IDLE
  - Acceptance: `ccc watch --once` shows all workers with state/task/stage/last-tool
  - PR title: "feat: ccc watch command for fleet monitoring via S3"

- [ ] T13: ccc watch single-worker detail
  - What: `ccc watch worker-1` shows detailed status + recent tool events
  - Why: Fleet view shows which worker is stuck. Detail view shows what it was doing
  - How: Download status.json + last 100 events from S3. Show task, stage, timing, last 20 tool events in reverse chronological. 5s refresh
  - Acceptance: `ccc watch worker-1 --once` shows detail view with recent tool calls
  - PR title: "feat: single-worker detail view in ccc watch"
