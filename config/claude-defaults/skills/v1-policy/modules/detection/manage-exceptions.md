# Detection: Manage Exceptions

Add, edit, and delete detection exceptions to suppress false positives.

## List Exceptions

```bash
python .claude/skills/v1-api/executor.py list_dmm_exceptions
```

## Create Exception

```bash
python .claude/skills/v1-api/executor.py dmm_exceptions \
  description="<why this exception exists>" \
  criteria='[{"fieldType":"user_account","fieldName":"logonUser","fieldValues":["Administrator"],"matchType":"EXACT"}]' \
  scope='{"filters":[{"filterId":"<filter-id>","filterName":"<filter-name>"}]}'
```

### Field Types for Criteria

| fieldType | fieldName Examples | matchType |
|-----------|-------------------|-----------|
| user_account | logonUser, accountDomain | EXACT, PARTIAL |
| endpoint | endpointHostName, endpointIp | EXACT, PARTIAL |
| process | processName, processCmd | EXACT, PARTIAL |
| file | fileName, filePath | EXACT, PARTIAL |
| network | srcIp, dstIp, dstPort | EXACT |

## Delete Exception

```bash
python .claude/skills/v1-api/executor.py delete_dmm_exceptions_delete \
  exception_id=<id>
```

## Best Practices

- Always include a clear description explaining WHY the exception exists
- Scope exceptions to specific filters/models, not globally
- Use EXACT match when possible (PARTIAL is broader)
- Review exceptions quarterly -- remove stale ones
