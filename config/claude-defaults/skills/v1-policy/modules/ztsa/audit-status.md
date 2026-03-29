# ZTSA: Audit Status

Check ZTSA deployment health and policy state.

## API-Based Checks

```bash
# ZTSA network activity (confirms traffic is flowing)
python .claude/skills/v1-api/executor.py search_network_logs hours=24 limit=10

# Endpoints with SAM (check agent list for ZTSA module)
python .claude/skills/v1-api/executor.py list_endpoints top=100
```

## Browser-Based Checks

```
1. Navigate to Zero Trust Secure Access > Overview
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_lookup query="Zero Trust"
   mcpm call blueprint browser_click selector="<ztsa-menu>"

2. Screenshot the dashboard
   mcpm call blueprint browser_take_screenshot
   → Shows: connected users, active sessions, blocked attempts

3. Check Secure Access Module status
   Navigate to Zero Trust Secure Access > Secure Access Module
   mcpm call blueprint browser_take_screenshot
   → Shows: deployed SAMs, connection status, versions

4. Check Private Access Connectors
   Navigate to Zero Trust Secure Access > Private Access Connectors
   mcpm call blueprint browser_take_screenshot
   → Shows: connector health, last heartbeat, version
```

## Health Check Criteria

| Check | Healthy | Unhealthy |
|-------|---------|-----------|
| SAM connected | Online, recent heartbeat | Offline or stale |
| Connector status | Running, green | Error or disconnected |
| ZTSA logs | Events in last hour | No events in 24h |
| Access rules | Rules configured and active | No rules or all disabled |
| User sync | AD/Entra sync recent | Sync failed or stale |
