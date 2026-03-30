# Dashboard API Endpoints -- Summary

## What was done
Added 4 REST API endpoints to `scripts/git-dispatch.py` for the monitoring dashboard:

1. **GET /api/tasks** -- reads bridge repo `requests/` dirs, returns JSON array of all tasks
2. **GET /api/workers** -- fleet roster enhanced with `_worker_stats` tracking data
3. **GET /api/stats** -- aggregate stats (worker counts, today's tasks, avg duration, success rate, uptime)
4. **GET /api/workers/{worker_id}/live** -- proxies worker port 8090 endpoints into one blob

## Implementation details
- `_worker_stats` dict with `_worker_stats_lock` tracks per-worker metrics
- Stats updated at 5 hook points: register, pick_worker_for_area, /worker/done, relay complete, relay fail
- Duration calculation from dispatched_at/completed_at timestamps in relay JSON files
- Live endpoint uses urllib to HTTP GET worker:8090/{status,output,activity}

## Test coverage
- 15 new tests in `tests/test_dashboard_api.py`
- Unit tests for each helper function + HTTP integration tests
- All 345 tests pass (330 existing + 15 new)

## PR
https://github.com/grobomo/claude-portable/pull/57
