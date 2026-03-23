#!/usr/bin/env python3
"""
cpp -- Claude Portable launcher.

Manages EC2 instances with stop/start lifecycle:
  cpp                  Connect to a running/stopped instance, or launch new
  cpp --name dev       Use/create a named instance
  cpp --new            Always launch a fresh instance
  cpp list             List all managed instances
  cpp stop [name]      Stop an instance (keeps state, no cost)
  cpp kill [name]      Terminate an instance permanently
  cpp kill --all       Terminate everything
"""
import argparse
import json
import os
import subprocess
import sys
import time

PROJECT_TAG = "claude-portable"

# ── Config ───────────────────────────────────────────────────────────────────

def load_config():
    """Load config from cpp.config.json (next to this script, or ~/.claude/)."""
    defaults = {
        "region": "us-east-2",
        "instance_type": "t3.large",
        "max_instances": 3,
        "key_name": "claude-portable-key",
        "idle_timeout_minutes": 30,
        "disk_size_gb": 40,
        "repo_url": "https://github.com/grobomo/claude-portable.git",
        "spot": False,
        "auto_sync_interval_seconds": 60,
        "auto_stop_on_idle": True,
    }
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "cpp.config.json"),
        os.path.expanduser("~/.claude/cpp.config.json"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path) as f:
                    user = json.load(f)
                defaults.update(user)
                defaults["_config_path"] = path
            except Exception:
                pass
            break
    # Env var overrides
    if os.environ.get("AWS_DEFAULT_REGION"):
        defaults["region"] = os.environ["AWS_DEFAULT_REGION"]
    if os.environ.get("CLAUDE_PORTABLE_INSTANCE_TYPE"):
        defaults["instance_type"] = os.environ["CLAUDE_PORTABLE_INSTANCE_TYPE"]
    return defaults

CFG = load_config()
REGION = CFG["region"]
KEY_NAME = CFG["key_name"]
INSTANCE_TYPE = CFG["instance_type"]

# ── AWS helpers ──────────────────────────────────────────────────────────────

def aws(*args, parse_json=True):
    cmd = ["aws"] + list(args) + ["--region", REGION, "--output", "json"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        if parse_json:
            return None
        return r.stderr
    if not r.stdout.strip():
        return {} if parse_json else ""
    return json.loads(r.stdout) if parse_json else r.stdout.strip()

def find_ssh_key():
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, ".ssh", f"{KEY_NAME}.pem"),
        os.path.join(home, "archive", ".ssh", "claude-portable.pem"),
        os.path.join(home, "archive", ".ssh", f"{KEY_NAME}.pem"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None

def get_instances(name_filter=None):
    """Get all claude-portable managed instances."""
    filters = [
        {"Name": "tag:Project", "Values": [PROJECT_TAG]},
        {"Name": "instance-state-name", "Values": ["running", "stopped", "pending"]},
    ]
    if name_filter:
        filters.append({"Name": "tag:Name", "Values": [f"cpp-{name_filter}"]})

    result = aws("ec2", "describe-instances",
                 "--filters", json.dumps(filters))
    if not result:
        return []

    instances = []
    for res in result.get("Reservations", []):
        for inst in res.get("Instances", []):
            tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
            instances.append({
                "id": inst["InstanceId"],
                "state": inst["State"]["Name"],
                "ip": inst.get("PublicIpAddress", ""),
                "type": inst["InstanceType"],
                "name": tags.get("Name", ""),
                "label": tags.get("Name", "").replace("cpp-", ""),
                "launched": inst.get("LaunchTime", ""),
            })
    return instances

def find_available(name=None):
    """Find a running or stopped instance to connect to."""
    instances = get_instances(name)
    # Prefer running, then stopped
    running = [i for i in instances if i["state"] == "running"]
    stopped = [i for i in instances if i["state"] == "stopped"]
    if running:
        return running[0]
    if stopped:
        return stopped[0]
    return None

def start_instance(instance_id):
    """Start a stopped instance and wait for IP."""
    print(f"  Starting {instance_id}...")
    aws("ec2", "start-instances", "--instance-ids", instance_id)
    # Wait for running
    subprocess.run(["aws", "ec2", "wait", "instance-running",
                     "--instance-ids", instance_id, "--region", REGION],
                    check=True)
    # Get public IP
    result = aws("ec2", "describe-instances", "--instance-ids", instance_id)
    ip = result["Reservations"][0]["Instances"][0].get("PublicIpAddress", "")
    return ip

def wait_for_container(ip, ssh_key, timeout=300):
    """Wait until Docker container is running."""
    start = time.time()
    while time.time() - start < timeout:
        r = subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
             "-o", "LogLevel=ERROR", "-i", ssh_key, f"ubuntu@{ip}",
             "docker ps --filter name=claude-portable --format '{{.Status}}'"],
            capture_output=True, text=True)
        if r.stdout.strip().startswith("Up"):
            return True
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(5)
    return False

def launch_new(name=None):
    """Launch a new on-demand EC2 instance."""
    # Enforce max instances
    existing = get_instances()
    active = [i for i in existing if i["state"] in ("running", "stopped", "pending")]
    max_inst = CFG.get("max_instances", 3)
    if len(active) >= max_inst:
        print(f"  ERROR: Max instances ({max_inst}) reached. Stop or kill one first.")
        print(f"  Running: {[i['label'] for i in active]}")
        print(f"  Use: cpp stop <name> or cpp kill <name>")
        sys.exit(1)

    label = name or f"box-{int(time.time()) % 10000}"
    instance_name = f"cpp-{label}"
    print(f"  Launching new instance: {instance_name}")

    # Use golden AMI if available, otherwise latest Ubuntu 24.04
    golden_ami = CFG.get("golden_ami", "")
    if golden_ami:
        # Verify it still exists
        check = aws("ec2", "describe-images", "--image-ids", golden_ami)
        if check and check.get("Images"):
            ami_id = golden_ami
            print(f"  Using golden AMI: {ami_id}")
        else:
            golden_ami = ""

    if not golden_ami:
        ami_result = aws("ec2", "describe-images",
                         "--owners", "amazon",
                         "--filters",
                         json.dumps([
                             {"Name": "name", "Values": ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]},
                             {"Name": "architecture", "Values": ["x86_64"]},
                         ]),
                         "--query", "Images | sort_by(@, &CreationDate) | [-1].ImageId",
                         parse_json=False)
        ami_id = ami_result.strip().strip('"')
        print(f"  Using base Ubuntu AMI: {ami_id} (run build-ami.sh for faster launches)")

    # Find or create security group
    sg = aws("ec2", "describe-security-groups",
             "--filters", json.dumps([{"Name": "group-name", "Values": ["cpp-sg"]}]))
    if sg and sg.get("SecurityGroups"):
        sg_id = sg["SecurityGroups"][0]["GroupId"]
    else:
        sg_result = aws("ec2", "create-security-group",
                        "--group-name", "cpp-sg",
                        "--description", "Claude Portable SSH access")
        sg_id = sg_result["GroupId"]
        for port in [22, 2222]:
            aws("ec2", "authorize-security-group-ingress",
                "--group-id", sg_id,
                "--protocol", "tcp", "--port", str(port), "--cidr", "0.0.0.0/0")

    # Ensure key pair exists
    if not aws("ec2", "describe-key-pairs", "--key-names", KEY_NAME):
        print(f"  Creating SSH key pair: {KEY_NAME}")
        home = os.path.expanduser("~")
        pem_path = os.path.join(home, ".ssh", f"{KEY_NAME}.pem")
        os.makedirs(os.path.dirname(pem_path), exist_ok=True)
        result = aws("ec2", "create-key-pair", "--key-name", KEY_NAME,
                      "--query", "KeyMaterial", parse_json=False)
        with open(pem_path, "w") as f:
            f.write(result.strip().strip('"').replace("\\n", "\n"))
        os.chmod(pem_path, 0o600)

    # Build user-data script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(script_dir, ".env")
    env_vars = {}
    if os.path.isfile(env_path):
        for line in open(env_path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip()

    repo_url = env_vars.get("REPO_URL", "https://github.com/grobomo/claude-portable.git")
    gh_token = env_vars.get("GITHUB_TOKEN", "")

    if golden_ami:
        # Golden AMI: Docker + container already built. Just write .env and start.
        userdata = f"""#!/bin/bash -xe
exec > /var/log/claude-portable-init.log 2>&1

cd /opt/claude-portable
cat > .env << 'ENVEOF'
"""
        for k, v in env_vars.items():
            userdata += f"{k}={v}\n"
        userdata += """ENVEOF

docker compose -f docker-compose.yml -f docker-compose.remote.yml up -d
"""
    else:
        # Base AMI: full install from scratch
        userdata = f"""#!/bin/bash -xe
exec > /var/log/claude-portable-init.log 2>&1

apt-get update -y
apt-get install -y ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable" > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
systemctl enable --now docker
usermod -aG docker ubuntu

export HOME=/root
cd /opt
git clone {repo_url} claude-portable
cd claude-portable

cat > .env << 'ENVEOF'
"""
        for k, v in env_vars.items():
            userdata += f"{k}={v}\n"
        userdata += """ENVEOF

docker compose -f docker-compose.yml -f docker-compose.remote.yml build
docker compose -f docker-compose.yml -f docker-compose.remote.yml up -d
"""

    import base64
    userdata_b64 = base64.b64encode(userdata.encode()).decode()

    # Launch instance (on-demand, stoppable)
    result = aws("ec2", "run-instances",
                 "--image-id", ami_id,
                 "--instance-type", INSTANCE_TYPE,
                 "--key-name", KEY_NAME,
                 "--security-group-ids", sg_id,
                 "--user-data", userdata,
                 "--block-device-mappings", json.dumps([{
                     "DeviceName": "/dev/sda1",
                     "Ebs": {"VolumeSize": CFG.get("disk_size_gb", 40), "VolumeType": "gp3", "DeleteOnTermination": True}
                 }]),
                 "--tag-specifications", json.dumps([{
                     "ResourceType": "instance",
                     "Tags": [
                         {"Key": "Name", "Value": instance_name},
                         {"Key": "Project", "Value": PROJECT_TAG},
                     ]
                 }]),
                 "--instance-initiated-shutdown-behavior", "stop")

    instance_id = result["Instances"][0]["InstanceId"]
    print(f"  Instance: {instance_id}")

    # Wait for running
    print(f"  Waiting for EC2...", end="", flush=True)
    subprocess.run(["aws", "ec2", "wait", "instance-running",
                     "--instance-ids", instance_id, "--region", REGION], check=True)
    print(" up!")

    # Get IP
    desc = aws("ec2", "describe-instances", "--instance-ids", instance_id)
    ip = desc["Reservations"][0]["Instances"][0].get("PublicIpAddress", "")

    return {"id": instance_id, "ip": ip, "name": instance_name, "label": label, "state": "running"}

def push_credentials(ip, ssh_key):
    """Push fresh auth credentials to the container."""
    # Try OAuth credentials
    creds_candidates = [
        os.path.expanduser("~/.claude/.credentials.json"),
        os.path.join(os.environ.get("USERPROFILE", ""), ".claude", ".credentials.json"),
    ]
    for creds_file in creds_candidates:
        if os.path.isfile(creds_file):
            creds = open(creds_file).read().strip()
            subprocess.run([
                "ssh", "-o", "StrictHostKeyChecking=no", "-o", "LogLevel=ERROR",
                "-i", ssh_key, f"ubuntu@{ip}",
                f"docker exec claude-portable bash -c 'cat > /home/claude/.claude/.credentials.json << CREDEOF\n{creds}\nCREDEOF'"
            ], capture_output=True)
            return "oauth"

    # Try API key from .env
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(script_dir, ".env")
    if os.path.isfile(env_path):
        for line in open(env_path):
            if line.startswith("ANTHROPIC_API_KEY="):
                key = line.strip().split("=", 1)[1]
                if key:
                    subprocess.run([
                        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "LogLevel=ERROR",
                        "-i", ssh_key, f"ubuntu@{ip}",
                        f"docker exec claude-portable bash -c 'echo export ANTHROPIC_API_KEY={key} >> /home/claude/.bashrc'"
                    ], capture_output=True)
                    return "api_key"
    return None

def start_idle_monitor(ip, ssh_key):
    """Start the idle monitor on the EC2 host (not in container)."""
    if not CFG.get("auto_stop_on_idle", True):
        return
    timeout = CFG.get("idle_timeout_minutes", 30)
    # Run idle monitor on the EC2 host (has access to instance metadata + aws cli)
    subprocess.run([
        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "LogLevel=ERROR",
        "-i", ssh_key, f"ubuntu@{ip}",
        f"nohup docker exec -d -e AWS_DEFAULT_REGION={REGION} claude-portable "
        f"/opt/claude-portable/scripts/idle-monitor.sh {timeout} &>/dev/null &"
    ], capture_output=True)

def setup_instance(ip, ssh_key, label):
    """Configure trust, identity, AWS creds on instance."""
    cmds = [
        # Trusted directories
        'docker exec -u root claude-portable python3 -c "'
        'import json; p=\\"/home/claude/.claude/settings.local.json\\"; '
        'exec(\\\"try:\\n d=json.load(open(p))\\nexcept:\\n d={}\\n'
        'd[\\\\\\\"trustedDirectories\\\\\\\"]=[\\\\\\\"/workspace\\\\\\\",\\\\\\\"/home/claude\\\\\\\",\\\\\\\"/tmp\\\\\\\"]\\n'
        'd[\\\\\\\"hasCompletedOnboarding\\\\\\\"]=True\\n'
        'json.dump(d,open(p,\\\\\\\"w\\\\\\\"),indent=2)\\\")'
        '"',
        # Instance identity
        f"docker exec claude-portable bash -c 'echo export CLAUDE_PORTABLE_ID={label} >> /home/claude/.bashrc'",
    ]
    # AWS credentials for state-sync
    try:
        ak = subprocess.run(["aws", "configure", "get", "aws_access_key_id"],
                            capture_output=True, text=True).stdout.strip()
        sk = subprocess.run(["aws", "configure", "get", "aws_secret_access_key"],
                            capture_output=True, text=True).stdout.strip()
        rg = subprocess.run(["aws", "configure", "get", "region"],
                            capture_output=True, text=True).stdout.strip()
        if ak and sk:
            cmds.append(
                f"docker exec claude-portable bash -c 'mkdir -p /home/claude/.aws && "
                f'printf "[default]\\naws_access_key_id = {ak}\\naws_secret_access_key = {sk}\\nregion = {rg}\\n" '
                f"> /home/claude/.aws/credentials'"
            )
    except Exception:
        pass

    for cmd in cmds:
        subprocess.run(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "LogLevel=ERROR",
             "-i", ssh_key, f"ubuntu@{ip}", cmd],
            capture_output=True)

def connect(ip, ssh_key, label):
    """SSH into the instance -- Claude auto-starts via bashrc."""
    print(f"\n  Connecting to {label} ({ip})...\n")
    # Try opening in new Windows Terminal tab
    try:
        subprocess.run(["wt.exe", "-w", "0", "new-tab", "--title", f"{label} ({ip})",
                        "ssh", "-o", "StrictHostKeyChecking=no", "-i", ssh_key,
                        f"ubuntu@{ip}", "-t",
                        "docker exec -it claude-portable bash -l"],
                       check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        # Fallback: SSH in current terminal
        os.execvp("ssh", [
            "ssh", "-o", "StrictHostKeyChecking=no", "-i", ssh_key,
            f"ubuntu@{ip}", "-t",
            "docker exec -it claude-portable bash -l"
        ])

# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_connect(args):
    ssh_key = find_ssh_key()
    if not ssh_key:
        print("ERROR: No SSH key found. Run setup.sh first.")
        sys.exit(1)

    name = args.name
    print("=" * 45)
    print("  cpp -- Claude Portable")
    print("=" * 45)

    if not args.new:
        inst = find_available(name)
        if inst:
            if inst["state"] == "stopped":
                print(f"\n  Found stopped instance: {inst['name']}")
                ip = start_instance(inst["id"])
                inst["ip"] = ip
                print(f"  IP: {ip}")
                print(f"  Waiting for container...", end="", flush=True)
                if not wait_for_container(ip, ssh_key, timeout=120):
                    # Container might need restart after stop
                    subprocess.run([
                        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "LogLevel=ERROR",
                        "-i", ssh_key, f"ubuntu@{ip}",
                        "cd /opt/claude-portable && docker compose -f docker-compose.yml -f docker-compose.remote.yml up -d"
                    ], capture_output=True)
                    wait_for_container(ip, ssh_key, timeout=180)
                print(" ready!")
            else:
                print(f"\n  Found running instance: {inst['name']} ({inst['ip']})")

            # Push fresh creds and connect
            push_credentials(inst["ip"], ssh_key)
            connect(inst["ip"], ssh_key, inst["label"])
            return

    # Launch new
    print()
    inst = launch_new(name)
    print(f"  Waiting for container (~3-5 min)...", end="", flush=True)
    if not wait_for_container(inst["ip"], ssh_key, timeout=420):
        print(f"\n  Container not ready. Check: ssh -i {ssh_key} ubuntu@{inst['ip']} 'tail /var/log/claude-portable-init.log'")
        sys.exit(1)
    print(" ready!")

    setup_instance(inst["ip"], ssh_key, inst["label"])
    push_credentials(inst["ip"], ssh_key)
    start_idle_monitor(inst["ip"], ssh_key)
    connect(inst["ip"], ssh_key, inst["label"])

def cmd_list(args):
    instances = get_instances()
    if not instances:
        print("No managed instances.")
        return
    print(f"\n{'NAME':<20} {'ID':<22} {'STATE':<10} {'IP':<16} {'TYPE':<12}")
    print(f"{'-'*20} {'-'*22} {'-'*10} {'-'*16} {'-'*12}")
    for i in instances:
        print(f"{i['label']:<20} {i['id']:<22} {i['state']:<10} {i.get('ip',''):<16} {i['type']:<12}")
    print()

def cmd_stop(args):
    name = args.name
    if name:
        instances = get_instances(name)
    else:
        instances = [i for i in get_instances() if i["state"] == "running"]

    if not instances:
        print("No running instances to stop.")
        return

    for inst in instances:
        # Push state before stopping
        ssh_key = find_ssh_key()
        if ssh_key and inst.get("ip"):
            print(f"  Syncing state for {inst['name']}...")
            subprocess.run([
                "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
                "-o", "LogLevel=ERROR", "-i", ssh_key, f"ubuntu@{inst['ip']}",
                "docker exec -e CLAUDE_PORTABLE_ID={} -e AWS_DEFAULT_REGION={} claude-portable /opt/claude-portable/scripts/state-sync.sh push".format(
                    inst["label"], REGION)
            ], capture_output=True, timeout=30)

        print(f"  Stopping {inst['name']} ({inst['id']})...")
        aws("ec2", "stop-instances", "--instance-ids", inst["id"])
    print("  Done.")

def cmd_kill(args):
    if args.all:
        instances = get_instances()
    elif args.name:
        instances = get_instances(args.name)
    else:
        print("Usage: cpp kill <name> or cpp kill --all")
        return

    if not instances:
        print("No instances to terminate.")
        return

    for inst in instances:
        print(f"  Terminating {inst['name']} ({inst['id']})...")
        aws("ec2", "terminate-instances", "--instance-ids", inst["id"])
    print("  Done.")

def cmd_config(args):
    config_path = CFG.get("_config_path", "not found")
    print(f"\n  Config: {config_path}\n")
    for k, v in sorted(CFG.items()):
        if k.startswith("_"):
            continue
        print(f"  {k:<35} {json.dumps(v)}")
    print()

# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Claude Portable launcher", prog="cpp")
    sub = parser.add_subparsers(dest="command")

    # Default: connect
    parser.add_argument("--name", "-n", help="Instance name")
    parser.add_argument("--new", action="store_true", help="Always launch fresh instance")

    p_list = sub.add_parser("list", help="List instances")
    p_stop = sub.add_parser("stop", help="Stop instance(s)")
    p_stop.add_argument("name", nargs="?", help="Instance name (default: all running)")
    p_kill = sub.add_parser("kill", help="Terminate instance(s)")
    p_kill.add_argument("name", nargs="?", help="Instance name")
    p_kill.add_argument("--all", action="store_true", help="Terminate all")
    p_config = sub.add_parser("config", help="Show current config")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "stop":
        cmd_stop(args)
    elif args.command == "kill":
        cmd_kill(args)
    elif args.command == "config":
        cmd_config(args)
    else:
        cmd_connect(args)

if __name__ == "__main__":
    main()
