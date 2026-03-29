"""
Clawdbot EC2 Orchestrator Lambda

Manages EC2 Spot instance lifecycle for cost-optimized Clawdbot deployment.

Actions:
- start: Launch EC2 Spot instance with Clawdbot
- stop: Gracefully terminate instance (syncs to S3 first)
- status: Return current state and public IP
- scheduled_start: Called by CloudWatch at start of active hours
- scheduled_stop: Called by CloudWatch at end of active hours
- idle_check: Check CPU utilization and shutdown if idle

Environment Variables:
- STACK_NAME: CloudFormation stack name
- CONFIG_PARAM: SSM parameter path for config
- STATE_BUCKET: S3 bucket for state persistence
"""

import json
import os
import boto3
import base64
from datetime import datetime, timedelta

ec2 = boto3.client('ec2')
ssm = boto3.client('ssm')
s3 = boto3.client('s3')
cloudwatch = boto3.client('cloudwatch')

STACK_NAME = os.environ['STACK_NAME']
CONFIG_PARAM = os.environ['CONFIG_PARAM']
STATE_BUCKET = os.environ['STATE_BUCKET']

# Amazon Linux 2023 ARM64 AMI (latest via SSM)
AMI_SSM_PARAM = '/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64'


def get_config():
    """Load configuration from SSM Parameter Store."""
    response = ssm.get_parameter(Name=CONFIG_PARAM)
    return json.loads(response['Parameter']['Value'])


def get_instance():
    """Find running Clawdbot instance managed by this stack."""
    response = ec2.describe_instances(
        Filters=[
            {'Name': 'tag:ManagedBy', 'Values': [STACK_NAME]},
            {'Name': 'instance-state-name', 'Values': ['pending', 'running', 'stopping']}
        ]
    )
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            return instance
    return None


def get_ami_id():
    """Get latest Amazon Linux 2023 ARM64 AMI ID from SSM."""
    response = ssm.get_parameter(Name=AMI_SSM_PARAM)
    return response['Parameter']['Value']


def get_userdata(config):
    """
    Generate EC2 userdata bootstrap script.

    This script runs on first boot to:
    1. Install Node.js 22 and system packages
    2. Create clawdbot user
    3. Install Clawdbot globally
    4. Sync config from S3
    5. Install any enabled addons
    6. Create systemd service
    7. Set up S3 sync cron and Spot interruption handler
    """
    bucket = config['bucket']

    return f'''#!/bin/bash
set -ex

# Log everything to file for debugging
exec > >(tee /var/log/clawdbot-bootstrap.log) 2>&1

echo "=== Clawdbot Bootstrap Starting ==="
echo "Timestamp: $(date)"
echo "Instance: $(curl -s http://169.254.169.254/latest/meta-data/instance-id)"

# -----------------------------------------------------------------------------
# Install System Dependencies
# -----------------------------------------------------------------------------
echo ">>> Installing Node.js 22..."
curl -fsSL https://rpm.nodesource.com/setup_22.x | bash -
dnf install -y nodejs git jq

# Verify Node version
node -v

# -----------------------------------------------------------------------------
# Create Clawdbot User
# -----------------------------------------------------------------------------
echo ">>> Creating clawdbot user..."
useradd -m -s /bin/bash clawdbot || true

# -----------------------------------------------------------------------------
# Install Clawdbot
# -----------------------------------------------------------------------------
echo ">>> Installing Clawdbot..."
npm install -g clawdbot@latest

# Verify install
which clawdbot
clawdbot --version || true

# Create directories
mkdir -p /home/clawdbot/.clawdbot
mkdir -p /home/clawdbot/.local/share
chown -R clawdbot:clawdbot /home/clawdbot

# -----------------------------------------------------------------------------
# Sync Config from S3
# -----------------------------------------------------------------------------
echo ">>> Syncing config from S3..."
aws s3 sync s3://{bucket}/config/ /home/clawdbot/.clawdbot/ --quiet || true
aws s3 sync s3://{bucket}/local-share/ /home/clawdbot/.local/share/ --quiet || true
chown -R clawdbot:clawdbot /home/clawdbot

# -----------------------------------------------------------------------------
# Install Addons
# -----------------------------------------------------------------------------
echo ">>> Checking for addons..."
ADDONS=$(aws s3 ls s3://{bucket}/addons/ 2>/dev/null | awk '{{print $2}}' | tr -d '/' || true)

for addon in $ADDONS; do
    if aws s3 ls "s3://{bucket}/addons/$addon/install.sh" &>/dev/null; then
        echo ">>> Installing addon: $addon"
        aws s3 cp "s3://{bucket}/addons/$addon/install.sh" "/tmp/$addon-install.sh"
        chmod +x "/tmp/$addon-install.sh"
        STATE_BUCKET="{bucket}" bash "/tmp/$addon-install.sh" || true
        rm -f "/tmp/$addon-install.sh"
    fi
done

# -----------------------------------------------------------------------------
# Create Systemd Service
# -----------------------------------------------------------------------------
echo ">>> Creating Clawdbot systemd service..."
cat > /etc/systemd/system/clawdbot.service << 'EOFSERVICE'
[Unit]
Description=Clawdbot Gateway
After=network.target

[Service]
Type=simple
User=clawdbot
WorkingDirectory=/home/clawdbot
ExecStart=/usr/bin/clawdbot gateway start
ExecStopPost=/bin/bash -c 'aws s3 sync /home/clawdbot/.clawdbot/ s3://{bucket}/config/ --quiet; aws s3 sync /home/clawdbot/.local/share/ s3://{bucket}/local-share/ --quiet'
Restart=always
RestartSec=10
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
EOFSERVICE

# -----------------------------------------------------------------------------
# Create S3 Sync Cron (every 5 minutes)
# -----------------------------------------------------------------------------
echo ">>> Setting up S3 sync cron..."
cat > /etc/cron.d/clawdbot-sync << 'EOFCRON'
*/5 * * * * clawdbot aws s3 sync /home/clawdbot/.clawdbot/ s3://{bucket}/config/ --quiet 2>/dev/null
*/5 * * * * clawdbot aws s3 sync /home/clawdbot/.local/share/ s3://{bucket}/local-share/ --quiet 2>/dev/null
EOFCRON

# -----------------------------------------------------------------------------
# Spot Interruption Handler
# -----------------------------------------------------------------------------
echo ">>> Setting up Spot interruption handler..."
cat > /usr/local/bin/clawdbot-shutdown.sh << 'EOFSHUTDOWN'
#!/bin/bash
echo "$(date) - Spot interruption detected, syncing state..."
sudo -u clawdbot aws s3 sync /home/clawdbot/.clawdbot/ s3://{bucket}/config/ --quiet
sudo -u clawdbot aws s3 sync /home/clawdbot/.local/share/ s3://{bucket}/local-share/ --quiet
systemctl stop clawdbot
echo "$(date) - Graceful shutdown complete"
EOFSHUTDOWN
chmod +x /usr/local/bin/clawdbot-shutdown.sh

cat > /etc/systemd/system/spot-interruption-handler.service << 'EOFSPOT'
[Unit]
Description=EC2 Spot Interruption Handler
After=network.target

[Service]
Type=simple
ExecStart=/bin/bash -c 'while true; do if curl -s -f -m 2 http://169.254.169.254/latest/meta-data/spot/instance-action > /dev/null 2>&1; then /usr/local/bin/clawdbot-shutdown.sh; sleep 120; fi; sleep 5; done'
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOFSPOT

# -----------------------------------------------------------------------------
# Start Services
# -----------------------------------------------------------------------------
echo ">>> Starting services..."
systemctl daemon-reload
systemctl enable clawdbot spot-interruption-handler
systemctl start spot-interruption-handler
systemctl start clawdbot

# Wait and verify
sleep 5
systemctl status clawdbot --no-pager || true

echo "=== Clawdbot Bootstrap Complete ==="
echo "Timestamp: $(date)"
echo ""
echo "Next steps:"
echo "1. SSH to this instance"
echo "2. Run: sudo -u clawdbot clawdbot models auth paste-token --provider anthropic"
echo "3. Paste your Claude setup token"
'''


def start_instance(config):
    """
    Launch new EC2 Spot instance.

    Returns dict with instance_id, public_ip, and status.
    """
    ami_id = get_ami_id()
    userdata = get_userdata(config)

    # Determine subnet
    subnet_id = config.get('subnet_id')
    if not subnet_id:
        # Find a public subnet in default VPC
        vpcs = ec2.describe_vpcs(Filters=[{'Name': 'isDefault', 'Values': ['true']}])
        if vpcs['Vpcs']:
            vpc_id = vpcs['Vpcs'][0]['VpcId']
            subnets = ec2.describe_subnets(
                Filters=[
                    {'Name': 'vpc-id', 'Values': [vpc_id]},
                    {'Name': 'map-public-ip-on-launch', 'Values': ['true']}
                ]
            )
            if subnets['Subnets']:
                subnet_id = subnets['Subnets'][0]['SubnetId']

    # Build instance parameters
    instance_params = {
        'ImageId': ami_id,
        'InstanceType': config['instance_type'],
        'KeyName': config['key_pair'],
        'SecurityGroupIds': [config['security_group']],
        'IamInstanceProfile': {'Arn': config['instance_profile']},
        'UserData': base64.b64encode(userdata.encode()).decode(),
        'MinCount': 1,
        'MaxCount': 1,
        'TagSpecifications': [{
            'ResourceType': 'instance',
            'Tags': [
                {'Key': 'Name', 'Value': f'{STACK_NAME}-instance'},
                {'Key': 'ManagedBy', 'Value': STACK_NAME}
            ]
        }]
    }

    if subnet_id:
        instance_params['SubnetId'] = subnet_id

    # Use Spot if configured
    if config.get('use_spot', True):
        instance_params['InstanceMarketOptions'] = {
            'MarketType': 'spot',
            'SpotOptions': {
                'SpotInstanceType': 'one-time',
                'InstanceInterruptionBehavior': 'terminate'
            }
        }

    # Launch instance
    response = ec2.run_instances(**instance_params)
    instance_id = response['Instances'][0]['InstanceId']

    # Wait for running state
    waiter = ec2.get_waiter('instance_running')
    waiter.wait(InstanceIds=[instance_id], WaiterConfig={'Delay': 5, 'MaxAttempts': 24})

    # Get public IP
    instance = ec2.describe_instances(InstanceIds=[instance_id])
    public_ip = instance['Reservations'][0]['Instances'][0].get('PublicIpAddress', 'pending')

    return {
        'instance_id': instance_id,
        'public_ip': public_ip,
        'status': 'starting'
    }


def stop_instance(instance):
    """
    Terminate instance gracefully.

    The instance will sync state to S3 via systemd ExecStopPost before terminating.
    """
    instance_id = instance['InstanceId']

    # Terminate (triggers ExecStopPost which syncs to S3)
    ec2.terminate_instances(InstanceIds=[instance_id])

    return {
        'instance_id': instance_id,
        'status': 'terminating'
    }


def get_instance_metrics(instance_id):
    """
    Get average CPU utilization over last 30 minutes.

    Used for idle detection - returns None if no data available.
    """
    response = cloudwatch.get_metric_statistics(
        Namespace='AWS/EC2',
        MetricName='CPUUtilization',
        Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
        StartTime=datetime.utcnow() - timedelta(minutes=30),
        EndTime=datetime.utcnow(),
        Period=300,  # 5 minute periods
        Statistics=['Average']
    )

    if response['Datapoints']:
        return sum(d['Average'] for d in response['Datapoints']) / len(response['Datapoints'])
    return None


def handler(event, context):
    """
    Main Lambda handler.

    Dispatches to appropriate action based on event['action'].
    """
    action = event.get('action', 'status')
    config = get_config()
    instance = get_instance()

    if action == 'start':
        if instance:
            return {
                'status': 'already_running',
                'instance_id': instance['InstanceId'],
                'public_ip': instance.get('PublicIpAddress', 'pending')
            }
        return start_instance(config)

    elif action == 'stop':
        if not instance:
            return {'status': 'not_running'}
        return stop_instance(instance)

    elif action == 'status':
        if not instance:
            return {'status': 'stopped'}
        return {
            'status': instance['State']['Name'],
            'instance_id': instance['InstanceId'],
            'public_ip': instance.get('PublicIpAddress', 'pending'),
            'launch_time': instance['LaunchTime'].isoformat()
        }

    elif action == 'scheduled_start':
        if instance:
            return {'status': 'already_running'}
        return start_instance(config)

    elif action == 'scheduled_stop':
        if not instance:
            return {'status': 'not_running'}
        return stop_instance(instance)

    elif action == 'idle_check':
        if not instance:
            return {'status': 'not_running'}

        avg_cpu = get_instance_metrics(instance['InstanceId'])
        idle_threshold = 5.0  # Shutdown if avg CPU < 5%

        if avg_cpu is not None and avg_cpu < idle_threshold:
            return {
                'action': 'shutdown_idle',
                'avg_cpu': avg_cpu,
                **stop_instance(instance)
            }

        return {
            'status': 'active',
            'avg_cpu': avg_cpu,
            'instance_id': instance['InstanceId']
        }

    else:
        return {'error': f'Unknown action: {action}'}
