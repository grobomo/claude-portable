# Tasks: 012 CCC Fleet Product — Configurable Target Repo

## Phase 1: Multi-repo dispatch

- [ ] T001 Add TARGET_REPO_URL/TARGET_WORKDIR config to git-dispatch.py
- [ ] T002 Add POST /api/submit endpoint to dispatcher
- [ ] T003 Add bearer token auth to dispatcher API

**Checkpoint**: `bash scripts/test/test-multi-repo-dispatch.sh` exits 0 — dispatcher reads target config
