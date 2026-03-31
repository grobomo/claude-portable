# Monitoring Dashboard -- Summary

## What was done

1. **Rewrote `scripts/dashboard.html`** -- Two-tab layout (Tasks + Infra Health) with:
   - Tasks tab: summary bar, task submission form, feature branch groups with collapsible task tables, recent completed tasks table
   - Infra Health tab: worker cards with CPU/memory/disk gauge bars, tasks/hour rate with trend arrows, error counts, recent API calls, health status dots
   - Dark theme (#0d1117 GitHub dark palette), monospace fonts, 16px+ base for booth readability
   - 15s auto-refresh with configurable `?refresh=N` URL param
   - Disconnected banner with exponential backoff retry
   - Visibility API: pauses refresh when tab is hidden
   - Change detection: flash animation on updated worker cards

2. **Added dashboard API endpoints to `git-dispatch.py`**:
   - `GET /dashboard` and `GET /dashboard/` -- serves dashboard.html
   - `GET /dashboard/api/tasks` -- aggregated task/feature data from board
   - `GET /dashboard/api/infra` -- per-worker resource metrics with health status
   - `DISPATCHER_DASHBOARD_PORT` env var (default 8082) for separate dashboard port
   - CORS support for dashboard API endpoints

3. **Extended worker heartbeat** in `worker-health.py`:
   - `cpu_percent` -- reads /proc/stat with 100ms sample interval
   - `memory_percent` + `memory_mb` -- reads /proc/meminfo
   - `disk_percent` + `disk_gb` -- reads df output
   - `error_count` -- cumulative error counter
   - Dispatcher stores all new fields in fleet roster

4. **Added 14 tests** to `tests/test_dashboard_api.py`:
   - Unit tests for `_dashboard_api_tasks()` and `_dashboard_api_infra()`
   - HTTP integration tests for /dashboard, /dashboard/api/tasks, /dashboard/api/infra
   - Heartbeat resource field storage test
   - Health/stale detection tests

## Success criteria verification

1. Dashboard HTML served at /dashboard -- VERIFIED (test_dashboard_serves_html passes)
2. Tasks tab shows features with statuses -- VERIFIED (test_busy_worker_creates_feature)
3. Infra tab shows gauges -- VERIFIED (test_healthy_worker, test_dashboard_api_infra_with_worker)
4. Booth readable -- 16px base, 28px metrics, 22px stats, monospace
5. No memory leaks -- DOM replacement (innerHTML), no unbounded arrays
6. Stale workers unhealthy -- VERIFIED (test_stale_worker_unhealthy, 60s threshold)
7. Data matches APIs -- VERIFIED (built from same _build_board and _fleet_roster)
