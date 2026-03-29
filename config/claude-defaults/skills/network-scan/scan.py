#!/usr/bin/env python3
"""
Network Scanner - Find active devices on local network using nmap via WSL.
Runs from WSL to avoid Windows security false positives.
"""
import subprocess
import sys
import re
from datetime import datetime

def get_default_network():
    """Get the default network from Windows ipconfig."""
    try:
        result = subprocess.run(['ipconfig'], capture_output=True, text=True)
        lines = result.stdout.split('\n')

        current_adapter = ""
        for i, line in enumerate(lines):
            if "adapter" in line.lower():
                current_adapter = line.strip()
            if "Default Gateway" in line and line.strip().endswith(('.1', '.254')):
                # Found a gateway, get the IP from previous lines
                gateway = line.split(':')[-1].strip()
                if gateway and not gateway.startswith('fe80'):
                    # Derive network from gateway (assume /24)
                    parts = gateway.split('.')
                    if len(parts) == 4:
                        return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
    except Exception:
        pass
    return "10.0.0.0/24"  # Default fallback

def run_scan(network, mode="normal"):
    """Run nmap scan via WSL."""

    # Build nmap command based on mode
    if mode == "quick":
        cmd = f"sudo nmap -sn -PE {network}"
    elif mode == "thorough":
        cmd = f"sudo nmap -sn -PE -PP -PM -PS21,22,23,25,80,443,3389,8080 -PA80,443 -PU53,67,123 --max-retries 3 -T3 {network}"
    else:  # normal
        cmd = f"sudo nmap -sn -PE -PP -PS22,80,443 -PA80 --max-retries 2 -T3 {network}"

    print(f"Scanning {network} ({mode} mode)...")
    print(f"Command: {cmd}\n")

    try:
        result = subprocess.run(
            ['wsl', '-d', 'Ubuntu', '--', 'bash', '-c', cmd],
            capture_output=True, text=True, timeout=300
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        print("Scan timed out after 5 minutes")
        return ""
    except Exception as e:
        print(f"Error: {e}")
        return ""

def parse_results(output):
    """Parse nmap output into list of hosts."""
    hosts = []
    lines = output.split('\n')

    for i, line in enumerate(lines):
        match = re.search(r'Nmap scan report for (?:(\S+) \()?(\d+\.\d+\.\d+\.\d+)', line)
        if match:
            hostname = match.group(1) or ""
            ip = match.group(2)
            host = {'ip': ip, 'hostname': hostname, 'latency': '?'}

            # Next line has latency
            if i + 1 < len(lines):
                latency_match = re.search(r'\(([0-9.]+)s latency\)', lines[i + 1])
                if latency_match:
                    host['latency'] = latency_match.group(1)

            hosts.append(host)

    return hosts

def main():
    mode = "normal"
    network = None

    for arg in sys.argv[1:]:
        if arg == "--quick":
            mode = "quick"
        elif arg == "--thorough":
            mode = "thorough"
        elif '/' in arg:
            network = arg

    if not network:
        network = get_default_network()

    print(f"=" * 50)
    print(f"Network Scan - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"=" * 50)

    output = run_scan(network, mode)
    hosts = parse_results(output)

    print(f"\nActive Hosts ({len(hosts)} found):")
    print("-" * 40)

    for host in sorted(hosts, key=lambda x: [int(p) for p in x['ip'].split('.')]):
        latency = host.get('latency', '?')
        hostname = f"  ({host['hostname']})" if host.get('hostname') else ""
        print(f"  {host['ip']:15} {latency:>6}s{hostname}")

    print("-" * 40)
    print(f"Total: {len(hosts)} hosts up")

if __name__ == "__main__":
    main()
