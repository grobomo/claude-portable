# Idle Timeout Source of Truth

- `DEFAULT_IDLE_TIMEOUT` lives in `mcp-manager/src/utils.ts` (3600000ms = 1hr)
- All consumers import from utils.ts — never hardcode the value
- If timeout seems wrong, check utils.ts not the consuming files
