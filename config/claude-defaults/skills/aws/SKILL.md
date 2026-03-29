---

name: aws
description: AWS CLI wrapper with correct path handling for Windows/Git Bash. CF, EC2, S3, Lambda, costs.
keywords:
  - aws
  - ec2
  - s3
  - lambda
  - cloudformation
  - billing
  - cost

---

# AWS Skill

Manage AWS resources with correct command formatting for Windows + Git Bash.

## CRITICAL RULES (Claude MUST follow)

1. **NEVER use `--profile` or `--region`** - default AWS CLI profile has both configured
2. **file:// paths with spaces BREAK** - use the `cf` command which handles this
3. **Use this skill's helper scripts** - don't build raw AWS CLI commands

## CloudFormation (most common)

```bash
# Deploy a stack (handles path spaces automatically)
~/.claude/skills/aws/aws.sh cf deploy STACK_NAME /path/to/template.yaml

# Deploy with capabilities
~/.claude/skills/aws/aws.sh cf deploy STACK_NAME /path/to/template.yaml --iam

# Stack status
~/.claude/skills/aws/aws.sh cf status STACK_NAME

# List stacks
~/.claude/skills/aws/aws.sh cf list

# Delete stack
~/.claude/skills/aws/aws.sh cf delete STACK_NAME

# Stack outputs
~/.claude/skills/aws/aws.sh cf outputs STACK_NAME

# Stack events (troubleshoot failures)
~/.claude/skills/aws/aws.sh cf events STACK_NAME
```

## EC2

```bash
~/.claude/skills/aws/aws.sh ec2 list                          # Default region only
~/.claude/skills/aws/aws.sh ec2 list-all-regions               # All regions (running)
~/.claude/skills/aws/aws.sh ec2 list-all-regions stopped       # All regions (stopped)
~/.claude/skills/aws/aws.sh ec2 start INSTANCE_ID
~/.claude/skills/aws/aws.sh ec2 stop INSTANCE_ID
```

## S3

```bash
~/.claude/skills/aws/aws.sh s3 list
~/.claude/skills/aws/aws.sh s3 delete BUCKET_NAME
```

## Other

```bash
~/.claude/skills/aws/aws.sh cost              # Monthly costs
~/.claude/skills/aws/aws.sh cost daily         # Daily breakdown
~/.claude/skills/aws/aws.sh lambda list        # Lambda functions
~/.claude/skills/aws/aws.sh lambda logs NAME   # Lambda logs
~/.claude/skills/aws/aws.sh whoami             # Account info
~/.claude/skills/aws/aws.sh resources          # Resource summary
```

## Path Handling (why this skill exists)

On Windows with Git Bash, AWS CLI `--template-body file://` fails with spaces in paths.
The `cf deploy` command automatically:
1. Detects if path has spaces
2. Copies template to `~/.claude/tmp/` with safe name
3. Uses `file://` with the space-free path

This avoids the `Unable to load paramfile` errors permanently.
