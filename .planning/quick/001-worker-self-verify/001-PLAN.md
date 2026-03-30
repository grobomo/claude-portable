# Worker Self-Verification

## Goal
Workers run verify-integration.sh before creating PRs. Test results included in PR body. Dispatcher exposes /api/verify/TASKID endpoint.

## Success Criteria
1. scripts/test/verify-integration.sh exists and runs: tests, syntax checks, secret scan
2. continuous-claude.sh calls verify-integration.sh during VERIFY stage
3. Verification results stored in pipeline state and reported to dispatcher
4. POST /worker/verify endpoint accepts verification results from workers
5. GET /api/verify/TASKID returns verification results for a task
6. PR body includes test results summary
