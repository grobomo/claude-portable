# Enable Email Sensor

Cross-product workflow that enables CECP's inline scanning sensor on Exchange Online.
This is a prerequisite for CECP to generate detection events in V1 email activity logs.

## Current State (2026-03-02)

All 6 joeltest.org accounts have sensor detection DISABLED:

| Account | Sensor | Policy Status | Mail Service |
|---------|--------|---------------|-------------|
| joel@joeltest.org | Disabled | Partially enabled | Exchange Online |
| mike@joeltest.org | Disabled | Partially enabled | Exchange Online |
| steve@Joeltester.onmicrosoft.com | Disabled | Partially enabled | Exchange Online |
| yama@joeltest.org | Disabled | Partially enabled | Exchange Online |
| support@joeltest.org | Disabled | Partially enabled | Exchange Online |

**Impact:** CECP generated only 2 email events in 30 days (vs CEGP's 142).
Without the sensor enabled, CECP can see the accounts but isn't actively scanning.

## Why This Matters

- CECP provides a second layer of detection ON TOP of Microsoft's native EOP
- When sensor is enabled, CECP's inline scanning catches threats EOP misses
- All CECP detections flow into V1's `search_email_logs` API -- no MS Graph needed
- Without sensor: CECP is connected but blind

## Prerequisites

- Blueprint MCP running
- V1 console open in Chrome Incognito
- Admin access to V1 console

## Verify Current State (API)

```bash
python .claude/skills/v1-api/executor.py list_email_asset_inventory_email_accounts
```

Look for `sensorDetectionStatus` field on each account.

## Enable Sensor Workflow (Browser Automation)

```
1. Navigate to Email & Collaboration Security
   mcpm call blueprint browser_lookup query="Email & Collaboration Security"
   mcpm call blueprint browser_click selector="<result>"
   mcpm call blueprint browser_evaluate code="await new Promise(r => setTimeout(r, 3000))"

2. Go to Settings / Service Management
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_lookup query="Settings"
   mcpm call blueprint browser_click selector="<settings-link>"
   mcpm call blueprint browser_evaluate code="await new Promise(r => setTimeout(r, 2000))"

3. Find Email Sensor / Inline Protection toggle
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_lookup query="Email Sensor"
   # OR
   mcpm call blueprint browser_lookup query="Inline Protection"

4. Enable the sensor
   mcpm call blueprint browser_click selector="<toggle>"

5. Confirm / Save
   mcpm call blueprint browser_lookup query="Save"
   mcpm call blueprint browser_click selector="<save-button>"

6. Wait for propagation (5-15 minutes)

7. Verify via API
   python .claude/skills/v1-api/executor.py list_email_asset_inventory_email_accounts
   # sensorDetectionStatus should now be "Enabled"
```

## Documentation

```bash
# CECP overview and sensor docs
python .claude/skills/trend-docs/executor.py "trend-vision-one-cemp-intro" --max-pages 2
python .claude/skills/trend-docs/executor.py "trend-vision-one-how-works" --max-pages 2

# Protection modes (inline vs API scanning)
python .claude/skills/trend-docs/executor.py "cloud-app-security-online-help-protection-modes-for" --max-pages 2
```

## Post-Enable Verification

After enabling, within 15-30 minutes:

```bash
# Should see CECP events appearing
python .claude/skills/v1-api/executor.py search_email_logs hours=1

# Should see both CEGP and CECP as pname values
# CEGP: gateway_realtime_accepted_mail_traffic
# CECP: exo_inline_realtime_accepted_mail_traffic
```

## Notes

- Enabling the sensor does NOT change mail flow -- CEGP (gateway) still handles MX routing
- CECP sensor adds inline scanning AFTER EOP and BEFORE delivery to mailbox
- Both products can detect independently -- double coverage on the same email
- Sensor applies to ALL accounts in the connected Exchange Online organization
