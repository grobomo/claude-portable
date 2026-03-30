# Tasks: 012 CCC Fleet Product — Configurable Target Repo

## Phase 1: Multi-repo dispatch

### T001: Add TARGET_REPO_URL/TARGET_WORKDIR config to git-dispatch.py
- Add env vars: TARGET_REPO_URL, TARGET_WORKDIR, TARGET_BRANCH
- Per-task override via bridge JSON: target_repo, target_workdir fields
- Replace all 6 hardcoded /workspace/boothapp and altarr/boothapp references
- Resolve target per-task: task JSON > env var > default

**Checkpoint:** `bash scripts/test/test-multi-repo.sh` — dispatcher reads target from env and task JSON

### T002: Add POST /api/submit endpoint
- Accept JSON {text, sender, target_repo?, target_workdir?}
- Create bridge task in relay repo pending/
- Return {task_id, status: "pending"}

**Checkpoint:** `curl -X POST /api/submit -d '{"text":"test"}' returns task_id`

### T003: Add bearer token auth to dispatcher API
- Read API_TOKEN from env (or Secrets Manager)
- Require Authorization: Bearer <token> on POST endpoints
- GET endpoints stay public

**Checkpoint:** `bash scripts/test/test-api-auth.sh` — POST without token returns 401
