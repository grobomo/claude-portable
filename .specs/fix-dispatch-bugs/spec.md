# Fix git-dispatch.py: Broken Git Pull and Wrong S3 Bucket

## Problem Statement

Two bugs in `scripts/git-dispatch.py` cause dispatcher failures:

1. **git_pull() uses rebase, which permanently breaks the repo on conflict.** The `git_pull()` function (line 142) runs `git pull --rebase origin main`. If a merge conflict occurs during rebase, the repo enters a stuck rebase state and all subsequent pulls fail. The dispatcher never makes local changes to the repo -- it only reads TODO.md and branch state -- so rebase logic is unnecessary and harmful.

2. **S3 heartbeat bucket name is wrong.** The `_get_s3_bucket()` function (line 2553) constructs the bucket name as `claude-portable-state-{account_id}`, producing `claude-portable-state-752266476357`. The actual bucket is `hackathon26-state-752266476357`. This causes all leader election heartbeat writes/reads to fail silently, breaking multi-dispatcher failover.

## Solution

### BUG 1: Replace git pull --rebase with fetch + force-sync

Replace the `git_pull()` function body. Instead of `git pull --rebase origin main`, use:
1. `git fetch origin main` -- get latest remote state
2. `git reset --hard origin/main` -- force local main to match remote exactly

This is safe because the dispatcher never makes local commits. It only reads files. Force-syncing guarantees the local repo always matches origin with zero possibility of merge conflicts or stuck rebase states.

The `_relay_git_pull()` function (line 2020) already uses this exact fetch+reset pattern for the relay repo -- this fix makes the main repo pull consistent with that approach.

### BUG 2: Change S3 bucket prefix from claude-portable-state to hackathon26-state

In `_get_s3_bucket()` (line 2564), change:
```python
return f"claude-portable-state-{r.stdout.strip()}"
```
to:
```python
return f"hackathon26-state-{r.stdout.strip()}"
```

This makes the derived bucket name `hackathon26-state-752266476357`, matching the actual S3 bucket.

## Components

| Component | File | Change |
|-----------|------|--------|
| `git_pull()` | `scripts/git-dispatch.py:142-163` | Replace `git pull --rebase` with `git fetch` + `git reset --hard origin/main` |
| `_get_s3_bucket()` | `scripts/git-dispatch.py:2553-2567` | Change bucket prefix from `claude-portable-state` to `hackathon26-state` |

## Success Criteria

1. `git_pull()` uses `git fetch origin main` followed by `git reset --hard origin/main` -- no `pull` or `rebase` commands remain in that function.
2. `grep -n 'claude-portable-state' scripts/git-dispatch.py` returns zero matches.
3. `_get_s3_bucket()` returns `hackathon26-state-{account_id}`.
4. Log messages in `git_pull()` still report success/failure accurately.
5. No other functions are modified -- only `git_pull()` and `_get_s3_bucket()`.
6. PR passes secret-scan CI check.

## Out of Scope

- Refactoring `_relay_git_pull()` (already uses the correct fetch+reset pattern)
- Adding retry logic or exponential backoff to git operations
- Changing any other S3 bucket references outside this file
- Modifying leader election logic beyond the bucket name fix
- Adding tests (dispatcher has no test suite currently)
