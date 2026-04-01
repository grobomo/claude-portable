# Dispatcher Brain -- Summary

## What was done
- Created `scripts/dispatcher-brain.py` -- single-file persistent AI agent using AWS Bedrock Converse API
- Added boto3 to Dockerfile pip install
- Added brain daemon startup to `dispatcher-daemon.sh` (runs as background process)
- Added brain health port (8081) to `docker-compose.dispatcher.yml`
- Created `tests/test_dispatcher_brain.py` -- validates startup, health endpoint, inbox collection

## Architecture
- Infinite loop: collect inbox -> call Bedrock with tool_use -> execute tools -> save history -> sleep 30s
- 3 inbox sources: dispatcher API (/api/tasks), GitHub issues (altarr/boothapp, grobomo/hackathon26)
- 10 tools: dispatch_task, merge_pr, check_fleet_health, register_worker, list_open_prs, send_teams_message, run_shell, comment_on_issue, close_issue, pull_latest
- Health endpoint: GET /api/brain-status on port 8081
- History persists to /tmp/brain-history.json, truncated at 100k tokens

## Model access note
Default model is `us.anthropic.claude-3-5-haiku-20241022-v1:0` (Haiku 3.5). The IAM role needs Bedrock model access enabled (marketplace subscription). Configurable via `BRAIN_MODEL_ID` env var -- upgrade to Sonnet 4 when IAM permissions are updated.

## Test results
All tests pass. Bedrock API call fails gracefully without model access (expected in test env).
