# CEGP: Audit Status

Check CEGP domain configuration, detection stats, and gateway health.

## Commands

```bash
# Domain configuration status
python .claude/skills/v1-api/executor.py list_email_asset_inventory_email_domains

# Recent detection activity
python .claude/skills/v1-api/executor.py search_email_logs hours=168 limit=500
# Filter for CEGP: pname="Cloud Email Gateway Protection"
# Filter for CEGP scan type: gateway_realtime_accepted_mail_traffic

# Full email report generation
python .tmp/email_report.py <week_json> <month_json> reports/email-report.pdf
```

## Health Check Criteria

| Check | Healthy | Unhealthy |
|-------|---------|-----------|
| Domain inbound config | Completed | Configuration required |
| Domain outbound config | Completed | Configuration required |
| Key features status | Fully enabled | Partially enabled |
| Email events in logs | Regular flow | No events |
| Sandbox (DDA) | Submissions > 0 | No sandbox activity |
| Quarantine actions | Proportional to volume | 0 (might mean too permissive) |

## Detection Effectiveness Metrics

Key ratios to track:

| Metric | Formula | joeltest.org (30d) |
|--------|---------|-------------------|
| Detection rate | emails_with_threats / total_emails | 18.8% |
| Quarantine rate | quarantined / total_emails | 2.8% |
| Sandbox submission rate | sandbox_scans / total_emails | 3.4x |
| False positive rate | restored_from_quarantine / quarantined | Check restore_email logs |

## Comparison: CEGP vs CECP

| Metric | CEGP | CECP |
|--------|------|------|
| Events (30d) | 142 | 2 |
| % of total | 98.6% | 1.4% |
| Scan type | gateway_realtime_accepted_mail_traffic | exo_inline_realtime_accepted_mail_traffic |
| Root cause of gap | Active, fully configured | Sensor disabled on all accounts |

**Action:** Enable CECP sensor (see `../enable-email-sensor.md`) to get dual-layer coverage.
