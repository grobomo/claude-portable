# Monitoring Dashboard -- Tasks

## Dependencies

```
T01 ──> T04 ──> T07 ──> T10
T02 ──> T05 ──> T08 ──> T11
T03 ──> T06 ──> T09 ──> T12
                        T13 (all above)
```

T01-T03 are independent foundation tasks. T04-T06 depend on their respective foundation. T07-T09 build on mid-layer. T10-T13 are polish/integration.

---

## T01: Dashboard HTML skeleton and tab switching

**Depends on:** none

Create `scripts/dashboard.html` with:
- HTML boilerplate, dark theme CSS variables, system monospace font stack
- Two-tab layout (Tasks, Infra Health) with sticky tab bar
- Tab switching via vanilla JS (show/hide content divs)
- Empty placeholder content in each tab ("Loading...")
- Disconnected banner (hidden by default, shown when fetch fails)
- All CSS inlined in `<style>`, all JS inlined in `<script>`

**Done when:** Opening the HTML file in a browser shows dark-themed two-tab interface with working tab switching.

---

## T02: Dashboard API endpoints in dispatcher

**Depends on:** none

Add to `git-dispatch.py` HealthHandler:
- `GET /dashboard` -- reads and serves `scripts/dashboard.html` (cached in memory at startup)
- `GET /dashboard/api/tasks` -- aggregates `/board` and `/health` data into the tasks response schema (see spec)
- `GET /dashboard/api/infra` -- aggregates fleet roster heartbeat data into the infra response schema (see spec)
- Serve dashboard on port 8082 (new HTTPServer thread, reusing HealthHandler)

**Done when:** `curl http://localhost:8082/dashboard` returns HTML; `/dashboard/api/tasks` and `/dashboard/api/infra` return valid JSON matching the spec schemas.

---

## T03: Worker heartbeat extensions for resource metrics

**Depends on:** none

Extend `worker-health.py` heartbeat payload to include:
- `cpu_percent` -- read /proc/stat twice (100ms apart), compute delta
- `memory_percent`, `memory_mb` -- parse /proc/meminfo
- `disk_percent`, `disk_gb` -- parse `df /workspace` output
- `claude_running` -- check if claude process is alive (pgrep)
- `error_count` -- cumulative counter (already partially tracked)

Update dispatcher's heartbeat handler to store these new fields in fleet roster.

**Done when:** Worker heartbeat POST includes all new fields; dispatcher `/health` fleet_roster entries contain cpu/memory/disk/claude data.

---

## T04: Tasks tab -- summary bar

**Depends on:** T01, T02

Add summary bar to top of Tasks tab:
- Fetch `/dashboard/api/tasks` on load and every 15s
- Display: total features, total tasks, completed, in-progress, blocked, idle workers, busy workers
- Each metric in a card with label + large number
- Color-coded numbers (green for completed, amber for in-progress, red for blocked)

**Done when:** Summary bar shows correct counts that match `/board` API data, updates every 15s.

---

## T05: Tasks tab -- feature branch groups with task table

**Depends on:** T01, T02

Render the features array from `/dashboard/api/tasks`:
- Collapsible section per feature branch
- Header: branch name, phase badge (colored by pipeline stage), progress bar (completed/total)
- Task table within each section: #, Description, Worker, Status badge, Last Activity (relative time)
- Status badge colors per spec (pending=gray, running=amber, completed=green, failed=red, blocked=orange)
- Active features auto-expanded, completed auto-collapsed

**Done when:** Feature branches render with correct task data, collapsing works, status badges display correctly.

---

## T06: Infra Health tab -- worker cards grid

**Depends on:** T01, T02, T03

Render worker cards from `/dashboard/api/infra`:
- Responsive CSS grid (1-3 columns based on viewport)
- Each card: worker ID header, health status dot (green/red)
- Gauge bars for CPU, memory, disk with color thresholds (green <60%, yellow <80%, red >=80%)
- Uptime as human-readable string
- Current task and phase displayed
- Cards sorted: unhealthy first, then alphabetical

**Done when:** Worker cards display with correct metrics, gauge bars reflect actual values, unhealthy workers sort to top.

---

## T07: Infra Health tab -- tasks/hour rate and error count

**Depends on:** T06

Add to each worker card:
- Tasks completed count (large number)
- Tasks/hour rate (computed: completions / uptime_hours)
- Trend arrow comparing current rate to previous refresh cycle (store previous values in JS)
- Error count badge (red background if > 0, gray if 0)

**Done when:** Rate calculation is correct, trend arrows update on refresh, error badge renders.

---

## T08: Infra Health tab -- recent API calls list

**Depends on:** T06

Add expandable "Recent Calls" section to each worker card:
- Show last 10 API calls: method, path, status code, relative timestamp
- Compact single-line format per call
- Status code colored: 2xx green, 4xx amber, 5xx red
- Scrollable if more than 5 visible (max-height with overflow-y)

**Done when:** Recent calls render correctly, scroll works, status codes are color-coded.

---

## T09: Auto-refresh engine with change detection

**Depends on:** T04, T05, T06

Implement the 15s auto-refresh loop:
- `setInterval` fetching both API endpoints
- Compare response JSON with previous to detect changes
- Pulse animation (brief border flash) on cards/rows that changed
- Configurable interval via `?refresh=N` URL parameter
- Pause auto-refresh when browser tab is hidden (visibilitychange API)
- Cleanup: replace DOM elements instead of appending (prevent memory leak)

**Done when:** Dashboard updates every 15s, changed elements flash briefly, no memory growth over 100 refresh cycles.

---

## T10: Disconnected state and error handling

**Depends on:** T09

Handle fetch failures gracefully:
- Show "Disconnected" banner with red background when fetch fails
- Banner shows last successful update timestamp
- Auto-hide banner when connection restores
- Retry with exponential backoff (15s -> 30s -> 60s, reset on success)
- Prevent stale data from persisting (gray out cards after 60s without update)

**Done when:** Killing the dispatcher causes banner to appear within 15s; restarting it causes banner to disappear; stale workers gray out.

---

## T11: Visual polish for booth readability

**Depends on:** T04, T05, T06

Ensure booth/demo readability:
- Minimum font size 16px for body text, 24px for metric numbers
- High contrast: all text passes WCAG AA against dark background
- Tab indicators clearly visible
- Phase badges and status badges use bold text with adequate padding
- Test at 1920x1080 resolution at simulated 3m viewing distance (scale browser to 50%)
- Add subtle CSS animations for tab transitions

**Done when:** All text readable at 50% browser zoom, no color contrast issues, badges clearly distinguishable.

---

## T12: Integration tests for dashboard API

**Depends on:** T02, T03

Add `tests/test_dashboard_api.py`:
- Test `/dashboard/api/tasks` returns correct schema with mock board data
- Test `/dashboard/api/infra` returns correct schema with mock heartbeat data
- Test `/dashboard` serves HTML with correct Content-Type
- Test dashboard port 8082 binding
- Test graceful response when no workers registered (empty arrays, zero counts)
- Test heartbeat with new resource fields is stored correctly

**Done when:** All tests pass, covering both populated and empty fleet scenarios.

---

## T13: End-to-end validation and documentation

**Depends on:** T10, T11, T12

Final integration pass:
- Start dispatcher with mock workers, verify both tabs render correctly
- Verify 15s refresh cycle works for 5 minutes without errors
- Add dashboard section to README.md: how to access, port config, URL params
- Add `DISPATCHER_DASHBOARD_PORT` env var support (default 8082)
- Verify HTML file size < 50KB (single file constraint)

**Done when:** Dashboard runs end-to-end with mock data, documented in README, file size verified.
