# CECP: Assign Policy to Accounts

Assign a CECP scanning policy to email accounts or groups.

## Current Assignments

Check via API:
```bash
python .claude/skills/v1-api/executor.py list_email_asset_inventory_email_accounts
```

## Workflow

```
1. Navigate to Email & Collaboration Security > Email Asset Inventory
   mcpm call blueprint browser_lookup query="Email Asset Inventory"
   mcpm call blueprint browser_click selector="<result>"
   mcpm call blueprint browser_evaluate code="await new Promise(r => setTimeout(r, 3000))"

2. Select target accounts (checkboxes)
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_click selector="<account-checkbox>"

3. Click "Assign Policy"
   mcpm call blueprint browser_lookup query="Assign Policy"
   mcpm call blueprint browser_click selector="<assign-button>"
   mcpm call blueprint browser_evaluate code="await new Promise(r => setTimeout(r, 2000))"

4. Select policy from list
   mcpm call blueprint browser_lookup query="<policy-name>"
   mcpm call blueprint browser_click selector="<policy-option>"

5. Confirm
   mcpm call blueprint browser_lookup query="Confirm"
   mcpm call blueprint browser_click selector="<confirm>"

6. Verify via API
   python .claude/skills/v1-api/executor.py list_email_asset_inventory_email_accounts
```
