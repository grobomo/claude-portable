# Response: Audit Status

Check blocklist entries, exception list, and response settings.

## Commands

```bash
# Suspicious objects blocklist
python .claude/skills/v1-api/executor.py list_blocklist

# Exception (allow) list
python .claude/skills/v1-api/executor.py list_exceptions

# Response settings
python .claude/skills/v1-api/executor.py list_response_setting_status

# Endpoint action exclusions
python .claude/skills/v1-api/executor.py list_response_endpoint_action_exceptions

# Isolation traffic exceptions
python .claude/skills/v1-api/executor.py list_response_isolated_traffic_exceptions

# Response task history
python .claude/skills/v1-api/executor.py list_response_tasks
```

## Health Check Criteria

| Check | Healthy | Unhealthy |
|-------|---------|-----------|
| Blocklist items | Documented, not expired | Undocumented or all expired |
| Exception list | Empty or minimal | Many broad exceptions |
| Response settings | Configured per policy | All disabled |
| Expired blocks | Cleaned up | Stale entries accumulating |
