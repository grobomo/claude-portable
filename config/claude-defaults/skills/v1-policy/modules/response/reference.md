# Response Management Reference

Centralized reference for suspicious object blocklist, exception (allow) list,
and endpoint response settings.

## Console Navigation

```
V1 Console > Threat Intelligence > Suspicious Object Management (left sidebar)
```

| Page | Path | Purpose |
|------|------|---------|
| Suspicious Objects | Threat Intelligence > Suspicious Object Management | Blocklist management |
| Exception List | Threat Intelligence > Exception List | Allow list |
| Response Management | Response Management > Response Tasks | Track response actions |

## Blocklist Object Types

| Type | Example | Effect |
|------|---------|--------|
| url | http://potato.com/ | Block URL access across all products |
| domain | joeltest.org | Block domain resolution |
| ip | 192.168.1.100 | Block IP communication |
| fileSha1 | abc123... | Block file by SHA-1 hash |
| fileSha256 | def456... | Block file by SHA-256 hash |
| senderMailAddress | bad@evil.com | Block email sender |

## Scan Actions

| Action | Effect |
|--------|--------|
| block | Actively prevent access/execution |
| log | Record the event but allow access |

## Current Blocklist (joeltest.org, 2026-03-02)

| Object | Type | Action | Risk | Expires |
|--------|------|--------|------|---------|
| http://potato.com/ | url | block | high | Never |
| joelworkk@gmail.com | senderMailAddress | log | high | 2026-03-12 |
| joel@joeltest.org | senderMailAddress | log | high | Never |
| joeltest.org | domain | block | high | Never |
| success.trendmicro.com/... | url | (check) | (check) | (check) |

## Response Settings

| Setting | Current | Purpose |
|---------|---------|---------|
| endpointActionException | disabled | Custom exceptions for endpoint response actions |
| isolatedTrafficException | enabled | Allow specific traffic for isolated endpoints |

## V1 API Operations (Full CRUD)

| Operation | Purpose |
|-----------|---------|
| `list_blocklist` | List all suspicious objects |
| `add_to_blocklist` | Add IOC to blocklist |
| `delete_response_suspicious_objects_delete` | Remove from blocklist |
| `list_exceptions` | List exception (allow) list |
| `list_response_setting_status` | Get response settings |
| `list_response_endpoint_action_exceptions` | Get endpoint action exclusions |
| `list_response_isolated_traffic_exceptions` | Get isolation traffic exceptions |
| `list_response_tasks` | List response task history |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Block not taking effect | Check expiration date, verify product integration |
| Too broad a block | Use more specific IOC type (URL vs domain) |
| Need to allow blocked item | Add to exception list, or remove from blocklist |
| Response task failed | Check endpoint connectivity, agent version |
