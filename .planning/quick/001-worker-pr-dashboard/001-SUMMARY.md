# Worker PR Dashboard -- Summary

## What was done

1. **Dispatcher: PR cache** -- Background thread refreshes open PRs from `gh pr list` every 30s
2. **Dispatcher: Worker-PR matching** -- `_get_worker_pr()` matches worker branch to open PR by headRefName
3. **Dashboard: Worker & PR cards** -- New card grid at top of Tasks tab showing each worker's active PR
4. **API: active_pr field** -- Both `/api/workers` and `/dashboard/api/infra` now include `active_pr` per worker

## Files changed
- `scripts/git-dispatch.py` -- PR cache thread, `_refresh_open_prs_cache()`, `_get_worker_pr()`, active_pr in API responses
- `scripts/dashboard.html` -- Worker-PR card grid with CSS and JS rendering
