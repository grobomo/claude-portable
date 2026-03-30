# CCC Client -- Summary

## What was done

1. Created `scripts/ccc-client.sh` -- pure bash CLI client for the CCC dispatcher API
2. Created `scripts/SKILL.md` -- Claude Code skill definition for discoverability

## Commands implemented

- `submit <description>` -- POST /task, prints task ID
- `status <task-id>` -- GET /task/{id}, shows full task details
- `poll <task-id>` -- blocks with periodic GET /task/{id} until terminal state
- `cancel <task-id>` -- DELETE /task/{id}
- `workers` -- GET /api/workers, tabular fleet status
- `tasks [state]` -- GET /tasks, optional state filter

## Key design decisions

- Pure bash + curl + jq (no Python dependency)
- Uses array-based curl options to correctly handle Bearer token with spaces
- `-k` flag for self-signed certs on private IPs
- Connection failure detection via HTTP code 000
- Poll uses SECONDS builtin for accurate timeout tracking
- Exit codes: 0=success, 1=error/fail/cancel, 2=timeout (poll only)
