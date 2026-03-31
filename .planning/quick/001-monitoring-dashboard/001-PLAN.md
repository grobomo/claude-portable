# Monitoring Dashboard

## Goal
Add a real-time HTML dashboard served at GET /dashboard on port 8082, showing worker status cards, task submission, and completed tasks. Dark theme, auto-refresh, mobile-friendly.

## Success Criteria
1. `curl http://dispatcher:8082/dashboard` returns working HTML page
2. Worker cards show name, status (idle/busy/unreachable), current task, progress, heartbeat, completions
3. Green/yellow/red dot indicators for worker status
4. Auto-refresh every 15 seconds
5. Dark theme, large readable fonts, mobile-friendly CSS grid
6. Task submission form at top
7. Recent completed tasks table below worker grid
8. Dashboard APIs: /dashboard/api/tasks and /dashboard/api/infra

## Approach
1. Create `scripts/dashboard.html` -- single file with inlined CSS/JS
2. Add `/dashboard` route to HealthHandler to serve HTML
3. Add `/dashboard/api/tasks` and `/dashboard/api/infra` endpoints aggregating existing data
4. Start dashboard on port 8082 (DISPATCHER_DASHBOARD_PORT env var)
5. Extend heartbeat with cpu/memory/disk fields
6. Add tests for new endpoints
