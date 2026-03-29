# Mobile Security: Audit Status

Check mobile security deployment health and policy state.

## API-Based Checks

```bash
# Mobile activity logs (the only API available)
python .claude/skills/v1-api/executor.py search_mobile_logs hours=24 limit=10
```

## Browser-Based Checks

```
1. Navigate to Mobile Security > Overview
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_lookup query="Mobile Security"
   mcpm call blueprint browser_click selector="<mobile-menu>"
   mcpm call blueprint browser_take_screenshot
   -> Shows: enrolled devices, active threats, policy status

2. Check Device Inventory
   Navigate to Mobile Security > Device Inventory
   mcpm call blueprint browser_take_screenshot
   -> Shows: enrolled devices, OS, compliance status

3. Check Security Policies
   Navigate to Mobile Security > Policies
   mcpm call blueprint browser_take_screenshot
   -> Shows: active policies, assigned groups

4. Check Threat Detection
   Navigate to Mobile Security > Threat Detection
   mcpm call blueprint browser_take_screenshot
   -> Shows: detected threats, blocked apps, network attacks
```

## Health Check Criteria

| Check | Healthy | Unhealthy |
|-------|---------|-----------|
| Device enrollment | Devices enrolled and reporting | No enrolled devices |
| Security policies | Active policies assigned | No policies configured |
| Threat detection | Scanning active | Detection disabled |
| Mobile logs | Events in last 24h | No events (if devices exist) |
| App control | Allowlist/blocklist configured | Not configured |
| Device compliance | Rules set and enforced | Not configured |
