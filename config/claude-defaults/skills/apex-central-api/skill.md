---
name: apex-central-api
description: Trend Micro Apex Central on-premises API wrapper
keywords:
  - apex
  - on-prem
  - legacy
---

# Apex Central API Skill

Query Trend Micro Apex Central APIs for endpoint management, threat detection, and security operations.

## Authentication

Requires Application ID and API Key from Apex Central console.

**Environment variables:**
```bash
export APEX_CENTRAL_URL="https://your-instance.manage.trendmicro.com"
export APEX_CENTRAL_APP_ID="your-application-id"
export APEX_CENTRAL_API_KEY="your-api-key"
```

Or create `.env` file in skill directory.

## Usage

```
/apex-central-api list-agents
/apex-central-api get-agent <agent_id>
/apex-central-api list-servers
/apex-central-api list-suspicious-objects
/apex-central-api add-suspicious-object <type> <value>
/apex-central-api delete-suspicious-object <type> <value>
/apex-central-api isolate-endpoint <guid>
/apex-central-api restore-endpoint <guid>
/apex-central-api scan-endpoint <guid>
```

## API Categories

| Category | Operations |
|----------|------------|
| Agents | list, get, isolate, restore, scan |
| Servers | list, get |
| Suspicious Objects | list, add, delete |
| Investigations | create, list, get |
| Policies | list, get, update |
| Logs | query, export |

## Examples

### List all agents
```python
from executor import ApexCentralAPI
api = ApexCentralAPI()
agents = api.list_agents()
print(f"Found {len(agents)} agents")
```

### Add to suspicious objects list
```python
api.add_suspicious_object(
    type="file_sha1",
    value="abc123...",
    description="Known malware"
)
```

### Isolate an endpoint
```python
api.isolate_endpoint(
    agent_guid="12345-67890-abcdef",
    reason="Suspected compromise"
)
```

## Error Handling

- `401`: Invalid credentials or expired token
- `403`: Insufficient permissions
- `404`: Resource not found
- `429`: Rate limited

## Resources

- [API Documentation](https://automation.trendmicro.com/apex-central/api/)
- [Getting Started](https://automation.trendmicro.com/apex-central/Guides/Getting-Started/)
