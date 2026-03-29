# CEGP: Create Gateway Policy

Create inbound/outbound scanning rules for the CEGP email gateway.

## Policy Types

| Direction | Purpose | Key Settings |
|-----------|---------|-------------|
| Inbound | Scan incoming mail before delivery | AntiVirus, AntiSpam, ContentFilter, DDA sandbox |
| Outbound | Scan outgoing mail | DLP, AntiVirus, ContentFilter |

## Current Policies (joeltest.org)

CEGP has default global policies active:
- Global Inbound Policy (Virus) -- AntiVirus scanning
- Global Inbound Policy (Spam) -- AntiSpam with URLDDAScan
- Global Outbound Policy (Virus) -- AntiVirus bypass on outbound

Check detection activity:
```bash
# See what scanners are firing and their actions
python .claude/skills/v1-api/executor.py search_email_logs hours=720 limit=1000
# Look at scannerDetails.policyScanResults for policy names and actions
```

## Create New Policy Workflow

```
1. Navigate to Email Gateway > Policy Management
   mcpm call blueprint browser_lookup query="Policy Management"
   # OR: Email Security > Policies

2. Click "Add Policy"
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_lookup query="Add Policy"
   mcpm call blueprint browser_click selector="<add-button>"

3. Select direction (Inbound/Outbound)

4. Configure scanning modules:
   - AntiVirus: engine, action on detection, DDA sandbox enable
   - AntiSpam: detection level, URL scanning, sender filtering
   - Content Filtering: blocked extensions, size limits
   - DLP (outbound): compliance templates, custom rules

5. Set policy scope (domain, sender/recipient filters)

6. Save and verify
   mcpm call blueprint browser_lookup query="Save"
```

## Scanner Module Reference

From 30-day detection data on joeltest.org:

| Scanner | Total Scans | Clean | Sandbox | Quarantine |
|---------|-------------|-------|---------|------------|
| ContentFilter | 850 | 850 | 0 | 0 |
| GeneralFilter | 606 | 606 | 0 | 0 |
| AntiSpam | 464 | 440 | 20 | 4 |
| AntiVirus | 376 | 373 | 3 | 0 |
| Correlated Intelligence | 210 | 210 | 0 | 0 |
| DlpFilter | 10 | 10 | 0 | 0 |

AntiSpam is doing the most detection work (24 non-clean actions).
