#!/bin/bash
# AWS Multi-purpose Management Script
# Handles Windows/Git Bash file:// path issues. Uses default AWS CLI profile for region/creds.

set -e

usage() {
    echo "AWS Skill - Uses default AWS CLI profile (no --profile, no --region)"
    echo ""
    echo "CloudFormation:"
    echo "  cf deploy STACK TEMPLATE [--iam]  Deploy/update stack (handles spaces)"
    echo "  cf status STACK                   Stack status"
    echo "  cf list                           List all stacks"
    echo "  cf delete STACK                   Delete stack"
    echo "  cf outputs STACK                  Show stack outputs"
    echo "  cf events STACK                   Show recent events"
    echo ""
    echo "EC2:  ec2 list | ec2 start|stop ID"
    echo "S3:   s3 list | s3 delete BUCKET"
    echo "Other: cost [daily] | ssm-run ID CMD | whoami | resources"
    exit 1
}

# Convert path to safe file:// URI (handles spaces in OneDrive paths)
safe_file_uri() {
    local input_path="$1"
    local base
    base=$(basename "$input_path")
    if [[ "$input_path" == *" "* ]]; then
        local safe tmpdir
        safe=$(echo "$base" | tr ' ' '_')
        tmpdir="$HOME/.claude/tmp"
        mkdir -p "$tmpdir"
        cp "$input_path" "$tmpdir/$safe"
        local win_tmp
        win_tmp=$(echo "$tmpdir/$safe" | sed 's|^/c/|C:/|; s|^/d/|D:/|; s|^/e/|E:/|')
        echo "file://$win_tmp"
    else
        local win
        win=$(echo "$input_path" | sed 's|^/c/|C:/|; s|^/d/|D:/|; s|^/e/|E:/|')
        echo "file://$win"
    fi
}

cmd_cf() {
    case "${1:-}" in
        deploy) shift; cmd_cf_deploy "$@" ;;
        status) cmd_cf_status "$2" ;;
        list)   cmd_cf_list ;;
        delete) cmd_cf_delete "$2" ;;
        outputs) cmd_cf_outputs "$2" ;;
        events) cmd_cf_events "$2" ;;
        *) echo "Usage: aws.sh cf [deploy|status|list|delete|outputs|events]"; exit 1 ;;
    esac
}

cmd_cf_deploy() {
    local stack_name="$1"
    local template_path="$2"
    shift 2 || true
    [ -z "$stack_name" ] && { echo "Usage: aws.sh cf deploy STACK TEMPLATE [--iam]"; exit 1; }
    [ -z "$template_path" ] && { echo "Usage: aws.sh cf deploy STACK TEMPLATE [--iam]"; exit 1; }
    [ ! -f "$template_path" ] && { echo "Error: Template not found: $template_path"; exit 1; }

    local file_uri
    file_uri=$(safe_file_uri "$template_path")

    local caps=""
    for arg in "$@"; do
        case "$arg" in
            --iam) caps="--capabilities CAPABILITY_NAMED_IAM" ;;
        esac
    done

    local stack_status
    stack_status=$(aws cloudformation describe-stacks --stack-name "$stack_name" \
        --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "DOES_NOT_EXIST")

    if [ "$stack_status" = "DOES_NOT_EXIST" ]; then
        echo "Creating stack: $stack_name"
        aws cloudformation create-stack \
            --stack-name "$stack_name" \
            --template-body "$file_uri" \
            $caps
        echo "Waiting for CREATE_COMPLETE..."
        aws cloudformation wait stack-create-complete --stack-name "$stack_name"
    else
        echo "Updating stack: $stack_name (current: $stack_status)"
        aws cloudformation update-stack \
            --stack-name "$stack_name" \
            --template-body "$file_uri" \
            $caps || echo "(No updates needed)"
    fi
    echo ""
    cmd_cf_status "$stack_name"
    echo ""
    cmd_cf_outputs "$stack_name"
}

cmd_cf_status() {
    local stack="$1"
    [ -z "$stack" ] && { echo "Usage: aws.sh cf status STACK"; exit 1; }
    aws cloudformation describe-stacks --stack-name "$stack" \
        --query 'Stacks[0].[StackName,StackStatus,CreationTime]' --output table
}

cmd_cf_list() {
    echo "=== CloudFormation Stacks ==="
    aws cloudformation list-stacks \
        --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE CREATE_IN_PROGRESS UPDATE_IN_PROGRESS ROLLBACK_COMPLETE CREATE_FAILED \
        --query 'StackSummaries[].[StackName,StackStatus,CreationTime]' --output table
}

cmd_cf_delete() {
    local stack="$1"
    [ -z "$stack" ] && { echo "Usage: aws.sh cf delete STACK"; exit 1; }
    echo "Deleting stack: $stack"
    aws cloudformation delete-stack --stack-name "$stack"
    echo "Delete initiated."
}

cmd_cf_outputs() {
    local stack="$1"
    [ -z "$stack" ] && return
    aws cloudformation describe-stacks --stack-name "$stack" \
        --query 'Stacks[0].Outputs[].[OutputKey,OutputValue]' --output table 2>/dev/null || true
}

cmd_cf_events() {
    local stack="$1"
    [ -z "$stack" ] && { echo "Usage: aws.sh cf events STACK"; exit 1; }
    aws cloudformation describe-stack-events --stack-name "$stack" \
        --query 'StackEvents[:15].[Timestamp,LogicalResourceId,ResourceStatus,ResourceStatusReason]' --output table
}

cmd_ec2_list() {
    echo "=== EC2 Instances ==="
    aws ec2 describe-instances \
        --query 'Reservations[*].Instances[*].[InstanceId,Tags[?Key==`Name`].Value|[0],State.Name,PublicIpAddress,InstanceType]' \
        --output table
}

cmd_ec2_list_all_regions() {
    local filter="${1:-running}"
    echo "=== EC2 Instances (all regions, state=$filter) ==="
    local regions
    regions=$(aws ec2 describe-regions --query 'Regions[].RegionName' --output text)
    for region in $regions; do
        local result
        result=$(aws ec2 describe-instances --region "$region" \
            --filters "Name=instance-state-name,Values=$filter" \
            --query 'Reservations[].Instances[].[InstanceId,InstanceType,Tags[?Key==`Name`].Value|[0],State.Name,PrivateIpAddress,PublicIpAddress]' \
            --output text 2>/dev/null)
        if [ -n "$result" ]; then
            echo ""
            echo "--- $region ---"
            echo "$result"
        fi
    done
}

cmd_ec2_action() {
    local action="$1" id="$2"
    [ -z "$id" ] && { echo "Usage: aws.sh ec2 $action ID"; exit 1; }
    aws ec2 "${action}-instances" --instance-ids "$id"
    echo "Instance $id: $action initiated"
}

cmd_s3_list() {
    echo "=== S3 Buckets ==="
    aws s3api list-buckets --query 'Buckets[*].Name' --output table
}

cmd_s3_delete() {
    local bucket="$1"
    [ -z "$bucket" ] && { echo "Usage: aws.sh s3 delete BUCKET"; exit 1; }
    aws s3 rb "s3://$bucket" --force
}

cmd_cost() {
    local gran="${1:-MONTHLY}"
    [ "$gran" = "daily" ] && gran="DAILY"
    local sd ed
    if date --version >/dev/null 2>&1; then
        sd=$(date -d "30 days ago" +%Y-%m-%d)
    else
        sd=$(date -v-30d +%Y-%m-%d 2>/dev/null || date +%Y-%m-%d)
    fi
    ed=$(date +%Y-%m-%d)
    echo "=== AWS Cost ($gran) ==="
    aws ce get-cost-and-usage \
        --time-period "Start=$sd,End=$ed" \
        --granularity "$gran" \
        --metrics "UnblendedCost" \
        --query 'ResultsByTime[*].[TimePeriod.Start,Total.UnblendedCost.Amount]' \
        --output table 2>/dev/null || echo "Cost Explorer not enabled."
}

cmd_lambda_list() {
    aws lambda list-functions \
        --query 'Functions[*].[FunctionName,Runtime,MemorySize]' --output table
}

cmd_lambda_logs() {
    local name="$1"
    [ -z "$name" ] && { echo "Usage: aws.sh lambda logs NAME"; exit 1; }
    aws logs tail "/aws/lambda/$name" --since 1h
}

cmd_whoami() {
    aws sts get-caller-identity
    echo "Region: $(aws configure get region)"
}

cmd_resources() {
    echo "=== AWS Resources ==="
    echo "S3: $(aws s3api list-buckets --query 'length(Buckets)' 2>/dev/null)"
    echo "EC2: $(aws ec2 describe-instances --query 'length(Reservations[*].Instances[*][])' --output text 2>/dev/null)"
    echo "CF: $(aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE --query 'length(StackSummaries)' 2>/dev/null)"
    echo "Lambda: $(aws lambda list-functions --query 'length(Functions)' 2>/dev/null)"
}

cmd_ssm_run() {
    local id="$1"; shift
    local cmd="$*"
    [ -z "$id" ] && { echo "Usage: aws.sh ssm-run ID COMMAND"; exit 1; }
    aws ssm send-command \
        --instance-ids "$id" \
        --document-name "AWS-RunShellScript" \
        --parameters "commands=[\"$cmd\"]" \
        --query 'Command.CommandId' --output text
}

case "${1:-}" in
    cf) shift; cmd_cf "$@" ;;
    ec2)
        case "${2:-}" in
            list) cmd_ec2_list ;;
            list-all-regions) cmd_ec2_list_all_regions "${3:-running}" ;;
            start|stop) cmd_ec2_action "$2" "$3" ;;
            *) echo "Usage: aws.sh ec2 [list|list-all-regions [state]|start|stop ID]"; exit 1 ;;
        esac ;;
    s3)
        case "${2:-}" in
            list) cmd_s3_list ;;
            delete) cmd_s3_delete "$3" ;;
            *) echo "Usage: aws.sh s3 [list|delete BUCKET]"; exit 1 ;;
        esac ;;
    cost) cmd_cost "$2" ;;
    lambda)
        case "${2:-}" in
            list) cmd_lambda_list ;;
            logs) cmd_lambda_logs "$3" ;;
            *) echo "Usage: aws.sh lambda [list|logs NAME]"; exit 1 ;;
        esac ;;
    ssm-run) shift; cmd_ssm_run "$@" ;;
    whoami) cmd_whoami ;;
    resources) cmd_resources ;;
    *) usage ;;
esac
