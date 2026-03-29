# CECP: Provision Service

Connect a cloud email/collaboration service to CECP for scanning.

## Supported Services

| Service | Auth Method | What CECP Scans |
|---------|-------------|-----------------|
| Exchange Online | OAuth app consent | Email (inline + API) |
| Gmail | Google Workspace admin | Email |
| SharePoint Online | OAuth app consent | Files |
| OneDrive for Business | OAuth app consent | Files |
| Microsoft Teams | OAuth app consent | Messages, files |
| Box | OAuth | Files |
| Dropbox | OAuth | Files |
| Google Drive | Google Workspace admin | Files |

## Current State (joeltest.org)

Exchange Online is connected (6 accounts visible) but sensor is disabled.
See `enable-email-sensor.md` for activation.

## Provision New Service Workflow

```
1. Navigate to Email & Collaboration Security > Settings > Service Connection
   mcpm call blueprint browser_lookup query="Service Connection"
   mcpm call blueprint browser_click selector="<result>"
   mcpm call blueprint browser_evaluate code="await new Promise(r => setTimeout(r, 3000))"

2. Click "Add Service Account" or "Grant Access"
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_lookup query="Grant Access"

3. Select service type (Exchange Online, Gmail, etc.)
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_click selector="<service-option>"

4. Complete OAuth consent flow
   # This opens a Microsoft/Google auth popup
   # User may need to complete MFA manually
   mcpm call blueprint browser_take_screenshot
   # Wait for consent to complete

5. Verify connection
   python .claude/skills/v1-api/executor.py list_email_asset_inventory_email_accounts
```

## Documentation

```bash
python .claude/skills/trend-docs/executor.py "trend-vision-one-gettingstarted-ecs" --max-pages 3
```
