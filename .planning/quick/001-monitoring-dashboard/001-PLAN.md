# Monitoring Dashboard

## Goal
Build a real-time two-tab HTML dashboard (Tasks + Infra Health) served by the dispatcher at GET /dashboard on port 8082, with 15s auto-refresh, dark theme, booth-readable fonts.

## Success Criteria
1. `curl http://dispatcher:8082/dashboard` returns working HTML
2. Tasks tab shows feature branches with correct task statuses
3. Infra Health tab shows per-worker CPU/memory/disk gauges updating every 15s
4. Readable from 3m on 24" monitor
5. Dashboard survives 1h auto-refresh without memory growth
6. Workers with no heartbeat >60s show as unhealthy (red)
7. All data matches /health and /board APIs

## Remaining Fixes
1. Bug: /api/submit matched by auth-required handler before public handler in do_POST
2. Gap: central-server.js doesn't proxy /dashboard/api/* or /api/submit
3. Gap: central-server.js embeds old simple dashboard, should proxy to full two-tab version
4. Run all tests, verify pass
