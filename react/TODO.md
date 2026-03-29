# Neural Pipeline — Improvement Tasks

<!-- Workers develop these using continuous-claude with branches/PRs. -->

## Phase 1: Core fixes

- [ ] Fix monitor status bar in ccc board: currently board.json may have stale entries from workers that stopped reporting. Add a `last_seen` timestamp to each worker entry and mark workers as `stale` if no heartbeat received in >90s. `ccc board` should show stale workers in red/dim instead of their last known phase.
  - What: Add staleness detection to board aggregation
  - Why: stale workers show as active in the dashboard, misleading operators
  - How: in worker-health.py heartbeat handler, record `last_seen` per worker in board.json. In ccc board renderer, compare `last_seen` to now and dim stale entries.
  - Acceptance: worker stops heartbeating -> within 90s board shows it as stale, not as its last phase
  - PR title: "fix: mark stale workers in ccc board"

- [ ] Make phases actually enforce gates in worker-pipeline.py: currently the pipeline tracker just records state but doesn't enforce ordering. Add validation that phases must progress in order (WHY->RESEARCH->REVIEW->PLAN->TESTS->IMPLEMENT->VERIFY->PR). Reject out-of-order phase transitions with an error. Allow re-entering the current phase (for retries) but not skipping phases.
  - What: Enforce phase ordering in worker-pipeline.py
  - Why: nothing prevents a buggy caller from jumping from RESEARCH to PR, which would bypass TDD enforcement
  - How: in cmd_phase(), check that the new phase is either the current phase (retry) or the next phase in PHASES list. Return error code 1 if out of order.
  - Acceptance: `worker-pipeline.py phase PR running` after only completing WHY returns exit code 1 and prints error
  - PR title: "feat: enforce phase ordering in worker pipeline"

- [ ] Add API endpoint for status queries: add GET /pipeline to worker-health.py that returns the full pipeline-state.json contents (not just the summary from /health). Include phase timings, gate results, and output file paths. This gives the dispatcher richer data for the board.
  - What: New /pipeline HTTP endpoint on worker-health.py
  - Why: GET /health returns a summary; dispatcher needs full phase detail for audit and board rendering
  - How: add handler for GET /pipeline in worker-health.py that reads and returns pipeline-state.json directly
  - Acceptance: `curl http://worker:8081/pipeline` returns full JSON with all phase entries and gate results
  - PR title: "feat: add /pipeline endpoint to worker health API"

## Phase 2: Observability

- [ ] Add phase duration tracking: worker-pipeline.py should calculate and store duration_seconds for each completed phase (end - start). Include total task duration in the done state. This data feeds into performance optimization later.
  - What: Auto-calculate phase durations in pipeline state
  - Why: no visibility into which phases take longest, can't optimize pipeline without data
  - How: in cmd_phase() when status is passed/failed, compute duration from start timestamp. In cmd_done(), compute total from task started_at.
  - Acceptance: after completing a phase, pipeline-state.json shows `duration_seconds` for that phase
  - PR title: "feat: track phase durations in worker pipeline"

- [ ] Add pipeline event log: every state change (phase start, phase end, gate pass/fail, retry) appends to `/data/pipeline-events.jsonl` as a single JSON line with timestamp, worker_id, task_num, event_type, and details. This provides a time-series audit trail separate from the state file.
  - What: Append-only event log for pipeline state changes
  - Why: pipeline-state.json is overwritten each time; event log preserves full history for debugging
  - How: add _append_event() helper in worker-pipeline.py, call it from every state mutation
  - Acceptance: after running a task through 3 phases, events.jsonl has 6+ lines (start+end per phase)
  - PR title: "feat: append-only pipeline event log"

- [ ] Aggregate phase duration stats across tasks: dispatcher reads completed task stage-logs and computes average, median, p95 duration per phase across all tasks. Exposed via GET /stats on dispatcher. Helps identify which phases are bottlenecks.
  - What: Cross-task phase duration statistics on dispatcher
  - Why: individual task durations exist but fleet-level stats don't; need to identify systematic bottlenecks
  - How: dispatcher reads /data/task-*-stages.json files, computes stats, serves via GET /stats
  - Acceptance: after 3+ completed tasks, GET /stats returns avg/median/p95 per phase
  - PR title: "feat: fleet-wide phase duration statistics"

## Phase 3: Reliability

- [ ] Add pipeline state recovery: if worker-pipeline.py crashes mid-phase, the next invocation should detect the incomplete state and offer recovery options: resume (re-enter current phase) or reset (start fresh). Currently a crash leaves the state file with status=running but no process is actually running.
  - What: Detect and recover from crashed pipeline state
  - Why: container restarts or OOM kills leave orphaned running state that confuses the next run
  - How: on startup commands (start/phase), check if state shows running but PID is dead. Add recovery logic.
  - Acceptance: kill worker-pipeline.py during a phase, re-run start -> detects stale state and recovers
  - PR title: "feat: pipeline state crash recovery"

- [ ] Add pipeline state backup: before each state mutation, copy the current pipeline-state.json to pipeline-state.json.bak. If the write fails or produces corrupt JSON, the backup can be restored. Simple safety net.
  - What: Atomic state file writes with backup
  - Why: power loss or disk full during write corrupts pipeline-state.json with no recovery
  - How: in _write_state(), copy current file to .bak before writing. Add _restore_backup() fallback in _read_state().
  - Acceptance: corrupt pipeline-state.json -> _read_state() falls back to .bak and logs warning
  - PR title: "feat: pipeline state backup for crash safety"
