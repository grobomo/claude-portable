# Fleet Dashboard -- central-server.js

## Goal
Create central-server.js that serves the fleet dashboard HTML with live data from the dispatcher API endpoints.

## Success Criteria
1. central-server.js serves HTML dashboard at GET /
2. Worker grid shows up to 10 workers with colored cards (green=idle, yellow=busy, red=unreachable)
3. Task list with status badges, auto-refresh every 10s
4. Submit form for new tasks (POST /task)
5. Fleet stats bar (workers, idle, busy, tasks today, success rate)
6. Dark theme, large text
7. Pulls live data from /health, /api/workers, /api/tasks, /api/stats
8. Dashboard proxies API calls to dispatcher (configurable DISPATCHER_URL)

## Approach
- Single Node.js file with embedded HTML (no external deps)
- Proxy /api/* and /health to dispatcher
- Update existing dashboard.html inline with: 10-worker grid, submit form, 10s refresh
