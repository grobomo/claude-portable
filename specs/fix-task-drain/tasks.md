# Fix Task Store Drain

## Phase 1: Add drain function
- [ ] T001: Add _drain_task_store() to _relay_poll_tick in git-dispatch.py
  **Checkpoint**: `grep -c _drain_task_store scripts/git-dispatch.py` returns > 0

## Phase 2: Verify
- [ ] T002: Submit task via API and confirm it dispatches to worker
  **Checkpoint**: `bash scripts/test/test-api-drain.sh` exits 0
