# Dashboard Plan

## Goal
Create a single-file dark-themed dashboard (scripts/dashboard.html) with two tabs: Tasks and Infra Health. Auto-refresh every 15s, fetching from /api/tasks, /api/workers, /api/stats.

## Success Criteria
1. Single HTML file at scripts/dashboard.html with all CSS+JS inline
2. Dark theme (#1a1a2e bg, #e0e0e0 text), large fonts
3. Auto-refresh every 15 seconds
4. Tasks tab: table with Status badge, Task ID, Description, Worker, Duration, Last Activity
5. Status badges: green=completed, yellow=dispatched/running, red=failed, gray=pending
6. Sort: running first, then pending, completed, failed
7. Infra Health tab: worker cards with name, status dot, uptime, tasks completed, current task
8. Click worker card expands: live stdout (from /api/workers/{id}/live), last file, last commit, CPU/memory bars, zombie count
9. Fleet summary bar: total workers, idle/busy, tasks today, success rate
10. PR to main
