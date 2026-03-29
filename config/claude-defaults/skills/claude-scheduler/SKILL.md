---
name: claude-scheduler
description: Cross-platform task scheduler with adaptive backoff. Runs recurring commands via OS scheduler (schtasks/launchd/systemd).
keywords: [schedule, cron, recurring, timer, periodic, weekly, daily, automate, scheduled, task, backoff]
user_invocable: false
---

# Claude Scheduler

Cross-platform recurring task runner for Claude Code.

## What It Does

- Registers tasks with commands and intervals
- Installs OS-level scheduler (Windows schtasks, macOS launchd, Linux systemd user timer)
- Adaptive backoff: 3 consecutive failures -> stop task + warn user
- SessionStart hook integration: warns when a stopped task needs attention

## Files

```
claude-scheduler/
├── SKILL.md        # This file
├── scheduler.py    # Task runner + CLI
├── install.py      # OS scheduler installer
├── tasks.json      # Task registry
└── state.json      # Runtime state (auto-created)
```

## CLI

```bash
python scheduler.py list                          # List tasks + status
python scheduler.py add --name "X" --command "Y" --interval weekly
python scheduler.py remove <task-id>
python scheduler.py status                        # Backoff state, last/next run
python scheduler.py reset <task-id>               # Clear stopped state
python scheduler.py run <task-id>                 # Run one task now
python scheduler.py run-all                       # Run all due tasks (OS calls this)
```

## Intervals

- `hourly` = 60 min
- `daily` = 1440 min
- `weekly` = 10080 min
- `<number>` = custom minutes

## Backoff Policy

| Consecutive Errors | Action |
|-------------------|--------|
| 1 | Retry next cycle |
| 2 | Retry next cycle |
| 3 | STOP + warn via SessionStart |

Reset with: `python scheduler.py reset <task-id>`

## Install OS Scheduler

```bash
python install.py install     # Register with OS
python install.py uninstall   # Remove from OS
python install.py status      # Check registration
```
