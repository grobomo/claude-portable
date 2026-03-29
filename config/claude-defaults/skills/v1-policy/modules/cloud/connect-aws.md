# Cloud: Connect AWS Account

Connect an AWS account to V1 via CloudFormation stack.

## Generate Template

```bash
# Generate CloudFormation template links
python .claude/skills/v1-api/executor.py cam_aws_accounts_generate_cfn_template_links

# Or generate Terraform package
python .claude/skills/v1-api/executor.py cam_aws_accounts_generate_terraform_package
```

## Deploy CloudFormation Stack

```bash
# Deploy the generated template
aws cloudformation create-stack \
  --stack-name Vision-One \
  --template-url <url-from-api> \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-2 \
  --profile joeltest
```

## Update Existing Stack (Fix "outdated" State)

The joel lab account shows state=outdated. To fix:

```bash
# 1. Generate fresh template
python .claude/skills/v1-api/executor.py cam_aws_accounts_generate_cfn_template_links

# 2. Update the existing stack
aws cloudformation update-stack \
  --stack-name Vision-One \
  --template-url <new-url> \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-west-2 \
  --profile joeltest

# 3. Verify account state
python .claude/skills/v1-api/executor.py list_aws_accounts
```

## Enable Features

Features are enabled during stack creation or via stack update:
- `file-storage-security`: S3 malware scanning (per-region)
- `cloud-audit-log-monitoring`: CloudTrail log ingestion
- `cloud-conformity`: CSPM compliance checking

## Verify Connection

```bash
# Check account appears and state is "active"
python .claude/skills/v1-api/executor.py list_aws_accounts

# Check features are enabled
python .claude/skills/v1-api/executor.py get_aws_account account_id=623338024321
```
