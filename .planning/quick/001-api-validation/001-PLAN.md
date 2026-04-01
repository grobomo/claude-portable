# API Input Validation for git-dispatch.py

## Goal
Add input validation to dispatcher API endpoints in git-dispatch.py with field-level 400 JSON errors and rejection logging.

## Success Criteria
1. POST /worker/register: name must match `hackathon26-worker-N` pattern, ip must be valid private IP (172.31.x.x)
2. POST /api/submit (/task): text required non-empty, sender required
3. POST /worker/report (mapped to /worker/heartbeat or /worker/done): worker_id must exist in roster, status must be idle/busy/error
4. Return 400 JSON errors with field-level details
5. Log rejected payloads
6. Add scripts/test/test-api-validation.sh
