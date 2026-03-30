# CCC Fleet Monitoring Dashboard

## Overview

A single-file HTML dashboard served by the dispatcher on port 8082, providing real-time visibility into CCC fleet operations. Two tabs: **Tasks** (feature progress and task assignments) and **Infra Health** (per-worker resource metrics). Designed for booth/demo display with dark theme, large fonts, and 15-second auto-refresh.

## Why

The dispatcher already exposes `/health`, `/board`, and `/tasks` APIs with rich fleet and task data. But there is no visual interface -- operators must curl endpoints and mentally parse JSON. A dashboard turns this data into an at-a-glance status board, critical for hackathon demos and multi-worker fleet management.

## Architecture

```
Browser (port 8082)
  |
  | fetch() every 15s
  v
Dispatcher (git-dispatch.py)
  ├── GET /dashboard           -> serves dashboard.html (single file)
  ├── GET /dashboard/api/tasks -> aggregated task + feature branch data
  └── GET /dashboard/api/infra -> per-worker health metrics
        |
        | aggregates from:
        ├── /health (dispatcher state, fleet roster)
        ├── /board  (task list, worker assignments, phases)
        ├── worker heartbeats (CPU, memory, disk, process status)
        └── task store (dispatched tasks, completion history)
```

The dashboard is a **single HTML file** (HTML + CSS + JS inlined) with zero external dependencies. No build step, no npm, no framework. The dispatcher serves it directly via its existing HTTP server.

## Tab 1: Tasks

### Data Model

| Field | Source | Description |
|-------|--------|-------------|
| Feature branch | `/board` workers[].task_branch | Active `continuous-claude/*` or `feat/*` branches |
| Spec phase | `/board` workers[].phase | Current pipeline phase (WHY, WHAT, HOW, BUILD, REVIEW, etc.) |
| Tasks | `/board` tasks[] | All tasks from TODO.md with status |
| Assigned worker | `/board` tasks[].worker | Worker ID handling the task |
| Task status | `/board` tasks[].status | pending, in_progress, blocked, completed |
| Last activity | `/health` fleet_roster[].last_heartbeat | ISO timestamp of last worker heartbeat |

### Layout

- Group tasks by feature branch (collapsible sections)
- Each feature shows: branch name, spec phase badge, progress bar (completed/total)
- Within each feature: task table with columns -- #, Description, Worker, Status, Last Activity
- Status badges: pending (gray), dispatched (blue), running (amber), completed (green), failed (red), blocked (orange)
- Phase badges colored by pipeline stage
- Summary bar at top: total features, total tasks, completed, in-progress, blocked, idle workers

### Behavior

- Auto-refresh every 15 seconds (configurable via URL param `?refresh=N`)
- Visual pulse animation on status change (new data differs from previous fetch)
- Click feature branch header to collapse/expand task list
- Completed features auto-collapse, active features auto-expand

## Tab 2: Infra Health

### Data Model

Per-worker cards sourced from worker heartbeat data forwarded through the dispatcher.

| Field | Source | Description |
|-------|--------|-------------|
| Worker ID | fleet_roster key | Instance name/ID |
| CPU usage % | heartbeat `cpu_percent` | From /proc/stat or ps |
| Memory usage % | heartbeat `memory_percent` | From /proc/meminfo |
| Memory used/total | heartbeat `memory_mb` | MB used / MB total |
| Disk usage % | heartbeat `disk_percent` | From df on /workspace |
| Disk used/total | heartbeat `disk_gb` | GB used / GB total |
| Container uptime | heartbeat `uptime_seconds` | Seconds since container start |
| Claude process | heartbeat `claude_running` | Boolean -- is claude process alive |
| Tasks completed | fleet_roster completions | Total tasks completed by this worker |
| Tasks/hour | computed | completions / (uptime_seconds / 3600) |
| Recent API calls | heartbeat `recent_calls` | Last 10 API calls with method, path, status, timestamp |
| Error count | fleet_roster errors or heartbeat `error_count` | Total errors since boot |
| Current task | fleet_roster task description | What the worker is doing now |
| Phase | fleet_roster phase | Current pipeline phase |

### Layout

- Grid of worker cards (responsive: 1-3 columns depending on viewport)
- Each card shows: worker name header, status indicator (green dot = healthy, red = unhealthy)
- Gauge bars for CPU, memory, disk (color transitions: green < 60%, yellow < 80%, red >= 80%)
- Uptime displayed as human-readable (e.g., "2h 15m")
- Tasks/hour rate with trend arrow (up/down vs previous reading)
- Recent API calls as a compact scrollable list (method, path, status code, relative timestamp)
- Error count badge (red if > 0)
- Cards sorted: unhealthy first, then by worker ID

### Behavior

- Auto-refresh every 15 seconds (synced with Tasks tab)
- Card border flashes red briefly when a worker transitions to unhealthy
- Clicking a card could expand to show full detail (stretch goal)

## Dashboard API Endpoints

Added to the dispatcher's existing HTTP server (HealthHandler in git-dispatch.py).

### GET /dashboard

Serves the dashboard HTML file. Content-Type: text/html. The HTML is either:
- Read from `scripts/dashboard.html` at startup and cached in memory, OR
- Embedded as a string constant in git-dispatch.py

Preference: separate file (`scripts/dashboard.html`) loaded at startup for easier editing.

### GET /dashboard/api/tasks

Returns aggregated task data for the Tasks tab.

```json
{
  "features": [
    {
      "branch": "continuous-claude/task-42-add-logging",
      "phase": "BUILD",
      "phase_start": "2026-03-29T10:00:00Z",
      "time_in_phase_s": 300,
      "tasks": [
        {
          "num": 42,
          "description": "Add structured logging to worker pipeline",
          "worker": "worker-a1b2c3",
          "status": "running",
          "last_activity": "2026-03-29T10:05:00Z"
        }
      ],
      "progress": {"completed": 3, "total": 5}
    }
  ],
  "summary": {
    "total_features": 2,
    "total_tasks": 15,
    "completed": 8,
    "in_progress": 3,
    "pending": 2,
    "blocked": 1,
    "failed": 1,
    "idle_workers": 1,
    "busy_workers": 3
  },
  "updated_at": "2026-03-29T10:05:15Z"
}
```

### GET /dashboard/api/infra

Returns per-worker infrastructure health data.

```json
{
  "workers": [
    {
      "worker_id": "worker-a1b2c3",
      "healthy": true,
      "cpu_percent": 45.2,
      "memory_percent": 62.0,
      "memory_mb": {"used": 1240, "total": 2048},
      "disk_percent": 38.5,
      "disk_gb": {"used": 12.3, "total": 32.0},
      "uptime_seconds": 8100,
      "claude_running": true,
      "tasks_completed": 7,
      "tasks_per_hour": 3.1,
      "recent_calls": [
        {"method": "POST", "path": "/heartbeat", "status": 200, "timestamp": "2026-03-29T10:05:00Z"},
        {"method": "POST", "path": "/heartbeat", "status": 200, "timestamp": "2026-03-29T10:04:30Z"}
      ],
      "error_count": 0,
      "current_task": "Add structured logging",
      "phase": "BUILD",
      "last_heartbeat": "2026-03-29T10:05:00Z"
    }
  ],
  "updated_at": "2026-03-29T10:05:15Z"
}
```

## Worker Heartbeat Extensions

Workers already POST heartbeats to the dispatcher. The heartbeat payload needs these additional fields:

| New field | Type | Source |
|-----------|------|--------|
| `cpu_percent` | float | Read /proc/stat delta or `ps aux` |
| `memory_percent` | float | Read /proc/meminfo |
| `memory_mb` | object | `{used, total}` from /proc/meminfo |
| `disk_percent` | float | `df /workspace` |
| `disk_gb` | object | `{used, total}` from df |
| `claude_running` | bool | `pgrep -f "claude"` exit code |
| `recent_calls` | array | Last 10 HTTP calls made by worker (ring buffer) |
| `error_count` | int | Cumulative error counter |

The dispatcher stores these in the fleet roster and exposes them via `/dashboard/api/infra`.

## Visual Design

- **Theme**: Dark background (#0d1117), card backgrounds (#161b22), borders (#30363d) -- GitHub dark palette
- **Fonts**: System monospace stack, base size 16px, headers 20-24px
- **Status colors**: green (#3fb950), amber (#d29922), red (#f85149), blue (#58a6ff), gray (#8b949e), orange (#db6d28)
- **Gauge bars**: 8px height, rounded, color transitions at 60%/80% thresholds
- **Tab bar**: Sticky top, two tabs with active indicator underline
- **Animations**: CSS transitions on status changes (0.3s), pulse on new data
- **Responsive**: min-width 800px, scales to 1920px+ for large monitors
- **No scrollbar jank**: overflow-y auto on main content area

## Constraints

1. Single HTML file -- all CSS and JS inlined, no external resources
2. No build step, no npm, no bundler
3. Served by the dispatcher's existing Python HTTP server
4. Dashboard port 8082 (separate from health API on 8080)
5. Must work in Chrome 90+ (container has Chrome, also viewed from laptop)
6. Auto-refresh must not cause memory leaks (no unbounded array growth)
7. Dashboard must gracefully handle dispatcher being unreachable (show "disconnected" banner)
8. No authentication required (internal network only)

## Success Criteria

1. `curl http://dispatcher:8082/dashboard` returns a working HTML page
2. Tasks tab shows all active feature branches with correct task statuses
3. Infra Health tab shows per-worker CPU/memory/disk gauges that update every 15s
4. Page is readable from 3 meters away on a 24" monitor (booth demo)
5. Dashboard survives 1 hour of continuous auto-refresh without memory growth
6. Workers with no heartbeat for >60s show as unhealthy (red indicator)
7. All data matches what `/health` and `/board` APIs return (no stale/phantom entries)

## Out of Scope

- Historical data / time-series graphs (future feature)
- Task control actions from dashboard (start/stop/reassign)
- Authentication / access control
- Mobile-optimized layout
- Persistent storage of dashboard state
