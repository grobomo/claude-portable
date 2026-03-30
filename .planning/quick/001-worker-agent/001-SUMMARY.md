# Worker Agent -- Summary

## What was done
Created `scripts/worker-agent.py` -- stdlib HTTP server on port 8090 with 4 endpoints for Claude process monitoring.

## Endpoints
| Endpoint | Returns |
|----------|---------|
| GET /status | pid, cpu_percent, memory_mb, running_seconds, task_id, state |
| GET /output | Last 200 lines from /tmp/claude-output.log |
| GET /activity | last_stdout_time, last_file_modified, last_git_commit, zombie_count |
| GET /health | disk_free_gb, container_uptime_hours, total_tasks, error_count |

## PR
https://github.com/grobomo/claude-portable/pull/53

## Design decisions
- Used stdlib `http.server` (no Flask) to keep zero external deps
- CPU% measured by sampling /proc/PID/stat twice 200ms apart
- Memory from VmRSS in /proc/PID/status
- File scan skips hidden dirs and .git for performance
- Zombie count scans /proc/*/status State field
- Error counter is in-memory (resets on restart)
