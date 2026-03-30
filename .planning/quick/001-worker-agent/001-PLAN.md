# Worker Agent HTTP Server

## Goal
Create `scripts/worker-agent.py` -- a lightweight HTTP server (stdlib only) on port 8090 that exposes Claude process metrics, output logs, activity tracking, and container health.

## Success Criteria
1. GET /status returns JSON {pid, cpu_percent, memory_mb, running_seconds, task_id, state: idle|busy}
2. GET /output returns last 200 lines from /tmp/claude-output.log
3. GET /activity returns {last_stdout_time, last_file_modified, last_git_commit, zombie_count}
4. GET /health returns {disk_free_gb, container_uptime_hours, total_tasks, error_count}
5. Runs as daemon: `python3 scripts/worker-agent.py &`
6. No external dependencies (stdlib http.server only)
7. PR to main on grobomo/claude-portable
