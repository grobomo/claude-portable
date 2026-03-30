---

name: ccc-client
description: Submit tasks to the CCC dispatcher fleet, check status, poll for completion, cancel tasks, and view worker status. Pure bash client -- no Python needed.
keywords:
  - ccc
  - client
  - submit
  - task
  - dispatch
  - workers
  - fleet
  - poll
  - status
  - cancel

---

# CCC Client

CLI client for the CCC dispatcher API. Submit tasks, monitor progress, manage the fleet.

## When to Use

Trigger on: "submit task to ccc", "check task status", "fleet workers", "ccc client", "dispatch task", "poll task"

## Quick Reference

```bash
# Submit a task
bash scripts/ccc-client.sh submit "refactor the auth module"

# Check status
bash scripts/ccc-client.sh status <task-id>

# Block until done (exits 0 on success, 1 on fail/cancel, 2 on timeout)
bash scripts/ccc-client.sh poll <task-id>

# Cancel
bash scripts/ccc-client.sh cancel <task-id>

# Show workers
bash scripts/ccc-client.sh workers

# List tasks (optionally filter by state)
bash scripts/ccc-client.sh tasks
bash scripts/ccc-client.sh tasks running
```

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `CCC_API_URL` | `https://16.58.49.156` | Dispatcher API base URL |
| `CCC_API_TOKEN` | (empty) | Bearer token for auth |
| `CCC_POLL_INTERVAL` | `5` | Seconds between poll checks |
| `CCC_POLL_TIMEOUT` | `300` | Max seconds to wait in poll mode |

## Dependencies

- `curl` -- HTTP requests
- `jq` -- JSON parsing

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error or task failed/cancelled |
| 2 | Poll timeout |

## API Endpoints Used

| Command | Method | Endpoint |
|---------|--------|----------|
| submit | POST | `/task` |
| status | GET | `/task/{id}` |
| poll | GET | `/task/{id}` (repeated) |
| cancel | DELETE | `/task/{id}` |
| workers | GET | `/api/workers` |
| tasks | GET | `/tasks[?status=STATE]` |
