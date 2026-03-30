# Fix Task Store Drain

## Phase 1: Add drain function
- [ ] T001: Add _drain_task_store() to _relay_poll_tick in git-dispatch.py

**Checkpoint**: `bash scripts/test/test-task-drain.sh` exits 0

## Phase 2: Verify
- [ ] T002: Submit task via API and confirm it dispatches to worker

**Checkpoint**: `bash scripts/test/test-task-drain.sh` exits 0
