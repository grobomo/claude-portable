# Dual-Verification PR System

## Goal
Implement a belt-and-suspenders verification system for the CCC fleet where PRs cannot merge until BOTH a worker's e2e tests AND a manager's independent review have passed, enforced by a PreToolUse hook gate.

## Success Criteria
1. PreToolUse hook (`dual-verify-gate.js`) blocks `gh pr merge` unless both `.test-results/T<NNN>.worker-passed` and `.test-results/T<NNN>.manager-reviewed` marker files exist
2. `worker-verify.sh` runs e2e tests, creates the worker-passed marker, and pushes it to the PR branch
3. `manager-review.sh` pulls the PR branch, runs independent verification, creates manager-reviewed marker on pass or requests changes on fail
4. `test-dual-verify.sh` exercises the full flow end-to-end with mocked PR data
5. All scripts are executable and pass shellcheck

## Files
- `.claude/hooks/run-modules/PreToolUse/dual-verify-gate.js`
- `scripts/fleet/worker-verify.sh`
- `scripts/fleet/manager-review.sh`
- `scripts/test/test-dual-verify.sh`
