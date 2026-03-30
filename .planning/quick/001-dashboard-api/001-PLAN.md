# Dashboard API Endpoints

## Goal
Add REST API endpoints to git-dispatch.py for the monitoring dashboard: /api/tasks, /api/workers, /api/stats, /api/workers/{id}/live.

## Success Criteria
1. GET /api/tasks returns JSON array from bridge repo requests/ dirs with {id, text, state, worker, dispatched_at, completed_at, duration_seconds}
2. GET /api/workers returns fleet_roster enhanced with {current_task_id, tasks_completed, tasks_failed, registered_at, last_dispatch_time}
3. GET /api/stats returns {total_workers, idle_count, busy_count, tasks_completed_today, tasks_failed_today, avg_duration_seconds, success_rate_percent, uptime_seconds}
4. GET /api/workers/{worker_id}/live proxies worker port 8090 /status + /output + /activity into one JSON blob
5. _worker_stats dict tracks dispatch/completion events per worker
6. All endpoints return application/json with proper HTTP status codes
