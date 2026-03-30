# CCC Client Script

## Goal
Build `scripts/ccc-client.sh` -- a pure bash CLI client for the CCC dispatcher API. Also create a SKILL.md for Claude Code skill sharing.

## Success Criteria
1. `ccc-client.sh submit "task description"` submits a task and prints the task ID
2. `ccc-client.sh status <id>` shows task status
3. `ccc-client.sh poll <id>` blocks until task reaches terminal state
4. `ccc-client.sh cancel <id>` cancels a task
5. `ccc-client.sh workers` shows fleet worker status
6. CCC_API_URL env var defaults to https://16.58.49.156
7. CCC_API_TOKEN env var used for auth header
8. No Python dependency -- pure bash + curl + jq
9. SKILL.md exists for Claude Code skill integration
