---



name: network-scan
description: Scan local network for active devices using nmap via WSL. Use when user says "scan network", "find devices", or "who's on my network".
keywords:
  - network
  - nmap
  - devices
  - subnet
  - hosts
  - specific
  - less
  - accurate


---

# Network Scanner

Thorough network scan for active hosts using nmap from WSL (avoids Windows security false positives).

## Usage

```bash
# Scan default network (auto-detect)
python scan.py

# Scan specific subnet
python scan.py 192.168.1.0/24

# Quick scan (less accurate)
python scan.py --quick

# Extra thorough (slower)
python scan.py --thorough
```

## Scan Methods

| Mode | Techniques | Time |
|------|------------|------|
| **quick** | ICMP echo only | ~5s |
| **normal** | ICMP echo/timestamp + TCP SYN 22,80,443 | ~10s |
| **thorough** | All ICMP + TCP SYN/ACK to common ports + UDP | ~60s |

## Output

```
Active Hosts (16 found):
  10.0.0.1    (0.002s latency)
  10.0.0.2    (0.006s latency)
  10.0.0.5    (0.002s latency)
  ...
```

## Requirements

- WSL with Ubuntu
- nmap installed: `sudo apt install nmap`
