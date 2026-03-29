# Cloud: Audit Status

Check connected cloud accounts, features, and sync state.

## Commands

```bash
# AWS accounts
python .claude/skills/v1-api/executor.py list_aws_accounts

# Azure subscriptions
python .claude/skills/v1-api/executor.py list_azure_accounts

# GCP projects
python .claude/skills/v1-api/executor.py list_gcp_accounts

# All cloud assets
python .claude/skills/v1-api/executor.py list_cloud_assets

# CSPM accounts and checks
python .claude/skills/v1-api/executor.py list_cspm_accounts
python .claude/skills/v1-api/executor.py get_cspm_checks
```

## Health Check Criteria

| Check | Healthy | Unhealthy |
|-------|---------|-----------|
| Account state | active | outdated (needs stack update) |
| Last synced | Within 24h | Days/weeks ago |
| Features enabled | file-storage + audit-log minimum | No features |
| CSPM | Checks running | No CSPM account |
| CloudTrail | Ingesting logs | No audit log monitoring |
