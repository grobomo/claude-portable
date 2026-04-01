# Summary: API Input Validation

## What was done

1. Added validation helpers (`_validate_worker_name`, `_validate_private_ip`, `_reject_payload`) to git-dispatch.py
2. **POST /worker/register**: name must match `hackathon26-worker-N`, ip must be `172.31.x.x`
3. **POST /task** (submit): `text` required non-empty, `sender` required non-empty, `priority` validated
4. **POST /worker/report** (new endpoint): `worker_id` must exist in roster, `status` must be idle/busy/error
5. All rejections return 400 JSON with `{"error": "Validation failed", "fields": {...}}`
6. All rejections logged at WARNING level with payload details
7. Added `--no-poll` flag for test-only HTTP server mode
8. Created `scripts/test/test-api-validation.sh` -- 27 tests, all passing

## Files changed
- `scripts/git-dispatch.py` -- validation logic + new endpoint + --no-poll flag
- `scripts/test/test-api-validation.sh` -- new test script
- `.planning/quick/001-api-validation/` -- GSD artifacts
