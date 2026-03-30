# Fleet Dashboard -- Summary

## What was done
Created `central-server.js` -- a Node.js server (zero external deps) that:

1. Serves fleet dashboard HTML at GET /
2. Proxies /api/tasks, /api/workers, /api/stats, /health to the dispatcher
3. Proxies POST /task for task submission

## Dashboard features
- **Worker grid**: 10-slot grid with colored cards (green=idle, yellow=busy, red=unreachable, dim=empty)
- **Task list**: sorted by status (dispatched > pending > completed > failed), with badges
- **Fleet stats bar**: total workers, idle, busy, tasks today, failed, success rate, avg duration, uptime
- **Submit form**: sticky bottom bar with text input and submit button
- **Auto-refresh**: 10-second countdown with visual pulse indicator
- **Dark theme**: GitHub-dark inspired, large readable text (18px base)

## Config
- `DASHBOARD_PORT` (default 3000)
- `DISPATCHER_URL` (default http://localhost:8080)
- `DISPATCH_API_TOKEN` (optional, for task submission auth)

## Tests
- JS syntax check: pass
- HTML serving: verified DOCTYPE, all sections, API fetch paths
- Proxy: returns 502 with clear error when dispatcher unreachable
- Existing 15 dashboard API tests: all pass
