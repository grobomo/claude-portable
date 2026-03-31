# Monitoring Dashboard -- Implementation Plan

## Goal

Build a full-featured fleet monitoring dashboard served on port 8082 by the dispatcher, with two tabs (Tasks and Infra Health), auto-refresh, dark theme, and booth-readable design.

## Success Criteria

1. `curl http://dispatcher:8082/dashboard` returns working HTML
2. Tasks tab shows feature branches with correct task statuses
3. Infra Health tab shows per-worker CPU/memory/disk gauges updating every 15s
4. Page readable from 3m on 24" monitor (large fonts, high contrast)
5. Dashboard survives 1hr auto-refresh without memory growth
6. Workers with no heartbeat >60s show unhealthy (red)
7. All data matches `/health` and `/board` APIs

## Implementation Summary

The dashboard.html already exists with basic structure, mock data, and tab switching. The dispatcher already has `/api/tasks`, `/api/workers`, `/api/stats` endpoints. Need to:

1. **Upgrade dashboard.html** to match spec: feature-branch grouping, phase badges, progress bars, gauge bars with thresholds, disconnected banner, booth-readable fonts, tasks/hour, error counts, recent calls, change detection with pulse animations
2. **Add dashboard API endpoints** per spec (`/dashboard/api/tasks`, `/dashboard/api/infra`) that aggregate `/board` + `/health` data into the spec schema
3. **Serve dashboard on port 8082** (new HTTPServer thread)
4. **Extend worker heartbeat** with cpu/memory/disk/claude_running fields
5. **Add integration tests**
6. **Validate end-to-end**
