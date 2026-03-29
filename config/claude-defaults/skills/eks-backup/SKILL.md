# EKS Backup Skill

Back up any EKS/RONE namespace to S3 with Secrets Manager. Generates all files needed: CloudFormation, K8s CronJob, backup/restore scripts.

## Triggers

- "backup eks namespace", "backup rone namespace", "eks backup", "k8s backup"
- "set up backups for namespace X"
- "backup and restore for kubernetes"

## Usage

```
/eks-backup init <project-dir> --namespace <ns> --accounts <profile1,profile2>
/eks-backup apply <project-dir>    # Deploy CF + K8s resources
/eks-backup status <project-dir>   # Check backup health
/eks-backup restore <project-dir>  # Restore from S3
```

## What It Generates

In `<project-dir>/`:
- `backup-config.yaml` — single source of truth for accounts, namespace, bucket names
- `cloudformation/backup.yaml` — S3 bucket + Secrets Manager + IAM user (per account)
- `k8s/backup-cronjob.yaml` — CronJob that runs backup.py on schedule
- `backup.py` — syncs PVC data to S3, secrets to Secrets Manager
- `restore.py` — pulls everything back from AWS
- `deploy.sh` — orchestrates CF deploy + K8s apply + secret injection

## Config File

All AWS account IDs, profiles, and bucket names come from ONE file: `backup-config.yaml`.
Every other file reads from it. Change the account, everything updates.

```yaml
namespace: my-namespace
aws_accounts:
  - profile: default
    account_id: "123456789012"
    region: us-east-2
  - profile: hackathon
    account_id: "987654321098"
    region: us-east-1
bucket_prefix: "my-app-backup"
secret_name: "my-app/graph-refresh-token"
backup_schedule: "0 */6 * * *"
pvc_name: my-app-data
data_paths:
  - messages
  - mentions
  - state.json
token_source: "~/.msgraph/tokens.json"
```
