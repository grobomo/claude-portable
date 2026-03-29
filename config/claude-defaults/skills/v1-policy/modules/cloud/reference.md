# Cloud Account Management Reference

Centralized reference for connected cloud accounts (AWS, Azure, GCP),
features, and cloud security posture management (CSPM).

## Console Navigation

```
V1 Console > Cloud Security > Cloud Accounts (left sidebar)
```

| Page | Path | Purpose |
|------|------|---------|
| Cloud Accounts | Cloud Security > Cloud Accounts | Connected AWS/Azure/GCP |
| Cloud Posture | Cloud Security > Cloud Posture | CSPM compliance checks |
| Cloud Assets | Attack Surface Risk Management > Cloud Assets | Inventory of cloud resources |

## Connected Accounts (joeltest.org, 2026-03-02)

### AWS

| Field | Value |
|-------|-------|
| Account ID | 623338024321 |
| Name | joel lab |
| Role ARN | arn:aws:iam::623338024321:role/Vision-One-VisionOneRole-MECKZ8HjVCic |
| State | outdated (needs CF stack update) |
| Features | file-storage-security (17 regions), cloud-audit-log-monitoring |
| Parent Stack | Vision-One (us-west-2) |
| Last Synced | 2026-03-02 |

### Azure

Not connected (404 response -- no Azure subscriptions registered).

### GCP

Not connected (no GCP projects registered).

## Features

Features are capabilities enabled per cloud account:

| Feature | Purpose | Regions |
|---------|---------|---------|
| file-storage-security | Scan S3/Blob storage for malware | Per-region deployment |
| cloud-audit-log-monitoring | Ingest CloudTrail/Activity logs | Global |
| cloud-conformity | CSPM compliance checking | Global |
| cloud-trail-management | CloudTrail management | Global |

## V1 API Operations

| Operation | Purpose |
|-----------|---------|
| `list_aws_accounts` | List connected AWS accounts |
| `get_aws_account` | Get single AWS account details |
| `cam_aws_accounts_generate_cfn_template_links` | Generate CloudFormation onboarding template |
| `cam_aws_accounts_generate_terraform_package` | Generate Terraform onboarding template |
| `list_azure_accounts` | List connected Azure subscriptions |
| `get_azure_account` | Get Azure subscription details |
| `list_gcp_accounts` | List connected GCP projects |
| `get_gcp_account` | Get GCP project details |
| `list_cloud_assets` | List all cloud assets |
| `get_cloud_asset` | Get cloud asset details |
| `get_cloud_asset_risks` | Get risk indicators for cloud asset |
| `list_cspm_accounts` | List CSPM-enabled accounts |
| `get_cspm_checks` | Get CSPM compliance check results |
| `list_cloud_risk_management_services` | List supported cloud services for risk management |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Account state "outdated" | Update CloudFormation stack to latest template |
| Features not available | Check V1 license for cloud security entitlements |
| No cloud assets visible | Verify IAM role permissions, check sync status |
| CSPM checks empty | Enable cloud-conformity feature on the account |
| Audit logs missing | Verify CloudTrail is enabled and IAM role has read access |
