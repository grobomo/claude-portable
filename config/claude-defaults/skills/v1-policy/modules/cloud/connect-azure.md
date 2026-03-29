# Cloud: Connect Azure Subscription

Connect an Azure subscription to V1 for cloud security monitoring.

## Current State

No Azure subscriptions connected (2026-03-02).

## Connect via Console (Browser Required)

```
1. Navigate to Cloud Security > Cloud Accounts
   mcpm call blueprint browser_lookup query="Cloud Accounts"
   mcpm call blueprint browser_click selector="<result>"

2. Click "Add Account" > "Azure"
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_lookup query="Add"
   mcpm call blueprint browser_click selector="<add-button>"

3. Select Azure
   mcpm call blueprint browser_lookup query="Azure"
   mcpm call blueprint browser_click selector="<azure-option>"

4. Follow the onboarding wizard:
   - Provide Azure Subscription ID
   - Authorize V1 app registration in Azure AD
   - Select features to enable

5. Verify
   python .claude/skills/v1-api/executor.py list_azure_accounts
```

## Alternative: Terraform

```bash
# Generate Terraform package for Azure onboarding
# (not yet available in lab -- check API)
```

## Features Available for Azure

| Feature | Purpose |
|---------|---------|
| cloud-audit-log-monitoring | Azure Activity Log ingestion |
| cloud-conformity | CSPM compliance for Azure |
| file-storage-security | Blob Storage malware scanning |
