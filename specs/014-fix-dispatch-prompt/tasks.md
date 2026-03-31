# Tasks: Fix Dispatch Prompt for PR Creation

## Phase 1: Prompt Fix

### T001: Add explicit PR creation instructions to dispatch prompt
- [ ] Add PR creation instructions to `_dispatch_relay_request()` prompt in git-dispatch.py
- [ ] Instructions must tell worker to: create branch, commit, push, create PR via `gh pr create`
- [ ] Must apply to both continuous-claude and simple claude -p paths

**Checkpoint**: `bash scripts/test/test-dispatch-prompt.sh` — verifies prompt contains PR instructions

### T002: Hot-patch dispatcher with fixed git-dispatch.py
- [ ] SCP updated git-dispatch.py to dispatcher container
- [ ] Restart dispatcher process
- [ ] Verify fix by submitting a test task and checking for PR creation

**Checkpoint**: `bash scripts/test/test-dispatch-prompt.sh` — submit task, verify PR created
