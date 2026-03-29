# Endpoint: Audit Status

Check endpoint inventory, policy assignments, agent versions, and sensor health.

## Commands

```bash
# Full endpoint inventory with policies and licenses
python .claude/skills/v1-api/executor.py list_endpoints top=100

# Version control policies
python .claude/skills/v1-api/executor.py list_policies

# Available agent update versions
python .claude/skills/v1-api/executor.py list_endpoint_security_version_control_policies_agent_update_policies

# Sensor statistics
python .claude/skills/v1-api/executor.py list_search_sensor_statistics

# Detailed endpoint info (single)
python .claude/skills/v1-api/executor.py get_endpoint endpoint_id=<agentGuid>
```

## Health Check Criteria

| Check | Healthy | Unhealthy |
|-------|---------|-----------|
| Security policy assigned | Named policy | (none) or blank |
| License allocated | EDR or EDR+Advanced | (none) |
| Agent version | n or n-1 | n-2 or older |
| Component version | upToDate | outdatedVersion |
| EPP status | on | off |
| Last connected | Within 24h | Days/weeks ago |
| Isolation status | off (unless intentional) | on (check if expected) |

## Quick Summary Script

```bash
# One-liner to summarize all endpoints
python .claude/skills/v1-api/executor.py list_endpoints top=100 2>&1 | \
  python -c "import sys,json; d=json.load(sys.stdin); [print(f\"{e['endpointName']:20s} {e.get('osPlatform','?'):8s} {e.get('securityPolicy','(none)'):45s} {','.join(e.get('creditAllocatedLicenses',[]))}\") for e in d.get('items',[])]"
```
