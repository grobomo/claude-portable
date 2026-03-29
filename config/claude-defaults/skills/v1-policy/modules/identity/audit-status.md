# Identity Security: Audit Status

Check identity security deployment health and risk posture.

## API-Based Checks

```bash
# Identity activity logs
python .claude/skills/v1-api/executor.py search_identity_logs hours=24 limit=10

# Domain accounts inventory
python .claude/skills/v1-api/executor.py list_domain_accounts

# High-risk users
python .claude/skills/v1-api/executor.py list_high_risk_users

# ASRM account compromise indicators
python .claude/skills/v1-api/executor.py list_asrm_account_compromise_indicators
```

## Browser-Based Checks

```
1. Navigate to Identity Security > Overview
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_lookup query="Identity Security"
   mcpm call blueprint browser_click selector="<identity-menu>"
   mcpm call blueprint browser_take_screenshot
   -> Shows: risk overview, compromised accounts, risky sign-ins

2. Check Identity Posture
   Navigate to Identity Security > Identity Posture
   mcpm call blueprint browser_take_screenshot
   -> Shows: password strength, MFA coverage, stale accounts

3. Check connector status
   Navigate to Identity Security > Settings
   mcpm call blueprint browser_take_screenshot
   -> Shows: connected identity sources, sync status
```

## Health Check Criteria

| Check | Healthy | Unhealthy |
|-------|---------|-----------|
| Identity source | Connected, sync recent | Disconnected or stale |
| Identity logs | Events in last hour | No events in 24h |
| High-risk users | Expected count | Unexpected spike |
| MFA coverage | >90% of accounts | <50% of accounts |
| Stale accounts | Monitored and flagged | Not configured |
| Privileged accounts | Identified and tracked | Unknown |
