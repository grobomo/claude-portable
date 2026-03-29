# Response: Manage Exception (Allow) List

Manage the exception list that allows objects otherwise blocked by suspicious object rules.

## List Exceptions

```bash
python .claude/skills/v1-api/executor.py list_exceptions
```

## Current State

Exception list is empty (0 items as of 2026-03-02).

## Add Exception

Exceptions are added via the V1 console:

```
1. Navigate to Threat Intelligence > Exception List
   mcpm call blueprint browser_lookup query="Exception List"
   mcpm call blueprint browser_click selector="<result>"

2. Click "Add Exception"
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_lookup query="Add"
   mcpm call blueprint browser_click selector="<add-button>"

3. Enter the object to allow (URL, domain, IP, hash, etc.)

4. Save
```

## Remove Exception

```bash
python .claude/skills/v1-api/executor.py delete_threatintel_suspicious_object_exceptions_delete \
  exception_id=<id>
```

## When to Use Exceptions vs Removing from Blocklist

| Scenario | Action |
|----------|--------|
| Object was blocked by mistake | Remove from blocklist |
| Object is on a Trend intel feed but is safe for you | Add to exception list |
| Temporary allow during investigation | Add exception with note, remove later |
