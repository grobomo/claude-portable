# Monitoring Dashboard -- Summary

## What was done

1. **Rewrote `scripts/dashboard.html`** (29KB, single file, zero dependencies):
   - Two tabs: Tasks (feature-branch grouping) and Infra Health (worker cards)
   - GitHub dark theme (#0d1117 palette), monospace font stack
   - Feature branches with phase badges, progress bars, collapsible sections
   - Worker cards with CPU/memory/disk gauge bars (green/amber/red thresholds)
   - Tasks/hour rate with trend arrows, error count badges
   - Recent API calls list per worker with color-coded status
   - Disconnected banner with last-update timestamp
   - Auto-refresh every 15s (configurable via `?refresh=N`), pauses when tab hidden
   - Change detection with pulse animation on updated elements
   - Workers with no heartbeat >60s shown as unhealthy/stale
   - Demo mode with mock data (auto-activates on API failure or `?demo`)

2. **Added dashboard API endpoints** (spec-compliant schemas):
   - `GET /dashboard` -- serves cached HTML (Content-Type: text/html)
   - `GET /dashboard/api/tasks` -- features grouped by branch with phase/progress
   - `GET /dashboard/api/infra` -- per-worker health with CPU/mem/disk/rate/errors
   - Available on both port 8080 (HealthHandler) and port 8082 (DashboardHandler)

3. **Dashboard port 8082** -- new `DashboardHandler` class + `start_dashboard_server()`:
   - `DISPATCHER_DASHBOARD_PORT` env var (default 8082)
   - HTML cached in memory at startup

4. **Extended worker heartbeat** (`worker-health.py`):
   - `_get_cpu_percent()` -- reads /proc/stat twice (100ms delta)
   - `_get_memory_info()` -- parses /proc/meminfo
   - `_get_disk_info()` -- parses `df -B1 /workspace`
   - Ring buffer for recent HTTP calls (last 10)
   - Cumulative error counter
   - All new fields stored by dispatcher's heartbeat handler

5. **Updated tests** (30 tests, all pass):
   - 15 existing v1 API tests preserved
   - 3 new `_dashboard_api_tasks()` unit tests
   - 4 new `_dashboard_api_infra()` unit tests (including stale/unhealthy detection)
   - 5 new `DashboardHandler` HTTP integration tests
   - 3 new `HealthHandler` dashboard route tests

## Files changed

- `scripts/dashboard.html` -- complete rewrite (589 -> 808 lines)
- `scripts/git-dispatch.py` -- added ~200 lines (dashboard APIs, DashboardHandler, port 8082)
- `scripts/worker-health.py` -- added ~90 lines (resource metrics, ring buffer)
- `tests/test_dashboard_api.py` -- added ~200 lines (15 new test cases)
- `.planning/quick/001-monitoring-dashboard/001-PLAN.md` -- GSD plan
