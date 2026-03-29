# CECP: Audit Status

Check CECP protection status, policy assignments, and detection activity via API.

## Commands

```bash
# Account-level: sensor status, policy assignments, mail service
python .claude/skills/v1-api/executor.py list_email_asset_inventory_email_accounts

# Domain-level: configuration status
python .claude/skills/v1-api/executor.py list_email_asset_inventory_email_domains

# Server-level: connected services
python .claude/skills/v1-api/executor.py list_email_asset_inventory_email_servers

# Recent CECP detection events
python .claude/skills/v1-api/executor.py search_email_logs hours=168 limit=500
# Filter for CECP: pname="Cloud Email and Collaboration Protection"
# Filter for CECP scan type: exo_inline_realtime_accepted_mail_traffic
```

## Health Check Criteria

| Check | Healthy | Unhealthy |
|-------|---------|-----------|
| sensorDetectionStatus | Enabled | Disabled |
| protectionPolicyStatus | Fully enabled | Partially enabled / Not configured |
| CECP events in logs | Regular flow (hourly) | 0-2 events in 30 days |
| scanType in logs | exo_inline_* present | Only gateway_realtime_* |

## Generating Detection Report

```bash
# Pull data and generate PDF report
python .tmp/email_report.py <week_json> <month_json> reports/email-report.pdf
```
