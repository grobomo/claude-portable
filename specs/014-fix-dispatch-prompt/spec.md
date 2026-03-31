# Spec 014: Fix Dispatch Prompt for PR Creation

## Problem
Workers complete code tasks (rc=0) but don't create PRs. Root cause: the dispatch prompt in `_dispatch_relay_request()` doesn't explicitly instruct Claude to create a branch, push, and open a PR. Workers make local commits but never push.

## Solution
Add explicit PR creation instructions to the prompt text in git-dispatch.py, after the task text and before escaping. This ensures both continuous-claude and simple claude -p paths include the instruction.

## Success Criteria
1. git-dispatch.py prompt includes explicit branch/commit/push/PR instructions
2. Submitted tasks result in PRs on the target repo
