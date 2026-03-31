# Monitoring Dashboard -- Summary

## What was done

1. **Dashboard HTML** (`scripts/dashboard.html`) -- complete rewrite with:
   - Task submission form at top
   - Fleet summary bar (workers, idle, busy, unreachable, done today, failed, avg duration)
   - Worker card grid with status dots (green=idle, yellow=busy, red=unreachable)
   - Each card: name, status, completions, heartbeat time, uptime, progress bar, CPU/memory/disk gauges
   - Recent tasks table below grid (25 most recent, sorted by state/time)
   - 15s auto-refresh with exponential backoff on disconnect
   - Dark theme (#0d1117 background), monospace fonts, mobile-responsive CSS grid
   - Visibility API pause when tab hidden (no wasted fetches)

2. **Dispatcher endpoints** (`scripts/git-dispatch.py`):
   - `GET /dashboard` and `GET /dash` -- serve dashboard HTML
   - `GET /dashboard/api/infra` -- per-worker health data (CPU, memory, disk, uptime, completions, tasks/hour)
   - `GET /dashboard/api/tasks` -- feature branch groupings with pipeline phases
   - Dashboard served on port 8082 (DISPATCHER_DASHBOARD_PORT env var), separate from health API on 8080
   - Heartbeat handler now stores cpu_percent, memory_percent, memory_mb, disk_percent, disk_gb, error_count

3. **Worker heartbeat extensions** (`scripts/worker-health.py`):
   - `_get_cpu_percent()` -- reads /proc/stat with 100ms delta
   - `_get_memory_info()` -- reads /proc/meminfo
   - `_get_disk_info()` -- runs `df -BG /workspace`
   - `_error_count` counter included in heartbeat payload

4. **Tests** (`tests/test_dashboard_api.py`):
   - 24 tests total (was 16, added 8 new)
   - Tests for /dashboard, /dash, /dashboard/api/infra, /dashboard/api/tasks
   - Tests for empty fleet, populated fleet, unhealthy workers, resource metrics, sort order

## Success criteria verification

- [x] `curl /dashboard` returns working HTML (19KB, all inline)
- [x] Worker cards show name, status, task (80 chars), progress %, heartbeat, completions
- [x] Green/yellow/red dot indicators
- [x] 15s auto-refresh with backoff
- [x] Dark theme, large fonts, mobile-responsive
- [x] Task submission form at top
- [x] Recent completed tasks table below grid
- [x] Dashboard APIs: /dashboard/api/tasks and /dashboard/api/infra
