# Event-Driven Observability -- Implementation Plan

## Branch Strategy

4 feature branches, each with sub-PRs (one per task). All branch from `main`.

| Branch | Tasks | PRs | Can parallelize with |
|--------|-------|-----|---------------------|
| `feat/event-log` | T01, T02, T03 | 3 PRs | feat/hook-runner-component (T04-T05) |
| `feat/hook-runner-component` | T04, T05, T06, T07 | 4 PRs | feat/event-log (T01 needed before T06) |
| `feat/worker-agent-events` | T08, T09, T10 | 3 PRs | After T01 merged to main |
| `feat/ccc-watch` | T11, T12 | 2 PRs | After T10 merged to main |

## Execution Order

### Phase 1: Foundation (T01 + T04-T05 in parallel)

Two independent tracks:

**Track A:** T01 (event-emitter.js + emit-event.sh)
- Create `scripts/emit-event.sh` in claude-portable
- Create `event-emitter.js` in hook-runner repo (separate repo, push there)
- Both write to `/data/events.jsonl` (or local equivalent)

**Track B:** T04 (components.yaml entry) then T05 (sync-config handler)
- T04 is trivial YAML addition
- T05 is the Python handler in sync-config.sh

Merge T01 and T04-T05 to main before Phase 2.

### Phase 2: Wiring (T02, T03, T06, T07)

After T01 is on main:
- T02: Add emit_event calls throughout continuous-claude.sh
- T03: Add rotation logic to both emitters
- T06: Wire hook-runner into settings.json (needs T01 for emitter + T05 for sync)
- T07: Container modules.yaml overlay

T02 and T03 can be done in parallel. T06 needs T05 done. T07 needs T06 done.

### Phase 3: Agent Redesign (T08, T09, T10)

Sequential within feature branch:
- T08: Core rewrite of worker-agent.py (event tailing replaces probes)
- T09: Stuck detection + self-healing rules
- T10: S3 status publishing

### Phase 4: CLI (T11, T12)

Sequential:
- T11: `ccc watch` fleet overview
- T12: Single worker detail view

## Files Modified Per Task

| Task | Repo | Files |
|------|------|-------|
| T01 | hook-runner | `event-emitter.js` (new) |
| T01 | claude-portable | `scripts/emit-event.sh` (new), `.env.example` |
| T02 | claude-portable | `scripts/continuous-claude.sh` |
| T03 | hook-runner | `event-emitter.js` |
| T03 | claude-portable | `scripts/emit-event.sh` |
| T04 | claude-portable | `components.yaml` |
| T05 | claude-portable | `scripts/sync-config.sh` |
| T06 | claude-portable | `scripts/sync-config.sh` |
| T07 | claude-portable | `config/modules-container.yaml` (new), `scripts/sync-config.sh` |
| T08 | claude-portable | `scripts/worker-agent.py` |
| T09 | claude-portable | `scripts/worker-agent.py` |
| T10 | claude-portable | `scripts/worker-agent.py` |
| T11 | claude-portable | `ccc` |
| T12 | claude-portable | `ccc` |

## Risk Mitigation

1. **Hook-runner repo is separate.** T01 and T03 touch hook-runner. Must push to grobomo/hook-runner, then workers pull latest at boot. If hook-runner is mid-update when a worker boots, it gets a partial clone. Mitigation: sync-config does a full clone (not sparse), so it's atomic per git clone.

2. **Breaking existing hooks.** T06 replaces the settings.json hooks config. If hook-runner gates fail, Claude runs without guardrails. Mitigation: T06 keeps a fallback -- if hook-runner scripts aren't found at the expected path, settings.json hooks are left unchanged.

3. **Worker-agent rewrite risk.** T08 is a significant rewrite. If the new event-based agent has bugs, workers lose visibility. Mitigation: keep the HTTP endpoints with the same paths/schemas so `ccc dashboard` (SSH-based) still works as a fallback.

4. **Event log disk pressure.** If a gate fires in a tight loop, events.jsonl could grow fast. Mitigation: T03 adds rotation (10MB cap, 2 files max = 20MB worst case). Gate.passed events are sampled at 10%.

## Testing Strategy

Each PR should be testable independently:

- **T01:** `bash -n scripts/emit-event.sh` (syntax check), then source + call emit_event, verify JSONL output
- **T02:** Run continuous-claude against a test repo with 1 trivial task, verify all event types appear
- **T03:** Generate >10MB of events, verify rotation happens and only 2 files remain
- **T04:** `python3 -c "import yaml; ..."` to validate components.yaml syntax
- **T05:** Run sync-config.sh in a test container, verify hook-runner files land in ~/.claude/hooks/
- **T06:** After bootstrap, `jq '.hooks' ~/.claude/settings.json` shows hook-runner entries
- **T07:** After bootstrap, `diff modules.yaml` shows container overrides applied
- **T08:** Feed synthetic events.jsonl to worker-agent, verify status.json derivation
- **T09:** Feed stuck-simulating events (15min gap), verify stuck detection triggers
- **T10:** Run worker-agent with S3 access, verify `aws s3 ls` shows status files
- **T11:** Mock S3 status files, run `ccc watch --once`, verify output format
- **T12:** Mock S3 status + events, run `ccc watch worker-1 --once`, verify detail view
