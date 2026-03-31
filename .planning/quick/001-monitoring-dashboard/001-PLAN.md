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

## Approach
- Rewrite `scripts/dashboard.html` with two-tab layout (Tasks + Infra Health)
- Add `/dashboard`, `/dashboard/api/tasks`, `/dashboard/api/infra` endpoints to dispatcher
- Add dashboard port 8082 support
- Extend worker heartbeat with CPU/memory/disk metrics
- Single HTML file, zero external deps
