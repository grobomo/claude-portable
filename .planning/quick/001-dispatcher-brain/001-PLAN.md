# Dispatcher Brain

## Goal
Build a persistent dispatcher-brain.py that replaces laptop-based fleet management. Long-running Python process using AWS Bedrock (claude-sonnet-4-6) with tool_use, running forever inside the dispatcher container.

## Success Criteria
1. Single file: scripts/dispatcher-brain.py
2. Uses boto3 bedrock-runtime invoke_model with tool_use
3. Infinite loop: check inbox -> think -> act -> remember -> sleep 30s
4. Conversation history persists to /tmp/brain-history.json (truncate at 100k tokens)
5. 3 inbox sources: dispatcher API queue, altarr/boothapp issues, grobomo/hackathon26 issues
6. 10 tools implemented as Python functions
7. System prompt with fleet management personality
8. Health endpoint: GET /api/brain-status
9. Runs as background daemon (added to golden-entrypoint.sh or similar)
10. Test: runs 60s, checks inbox, logs idle, health endpoint works
