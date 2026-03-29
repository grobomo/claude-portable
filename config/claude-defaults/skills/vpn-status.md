---
name: vpn-status
description: Check VPN connection status, review logs, and verify scheduled task
triggers:
  - vpn status
  - check vpn
  - vpn logs
  - vpn monitor status
---

# VPN Status Skill

Check VPN monitor health and connection status.

## Quick Check

```bash
powershell.exe -ExecutionPolicy Bypass -File "/home/claude\OneDrive - TrendMicro\Documents\ProjectsCL\vpn-monitor\vpn-status.ps1"
```

## Options

```bash
# Last 24 hours (default)
.\vpn-status.ps1

# Last 48 hours
.\vpn-status.ps1 -Hours 48
```

## What It Shows

- Current VPN connection status
- Network adapter statistics (Rx/Tx bytes)
- Log summary: connections, disconnects, errors
- Gaps in monitoring (>20 min = task didn't run)
- Scheduled task status

## Files

```
vpn-monitor/
├── vpn-check.ps1         # Check script (called by task)
├── vpn-check-hidden.vbs  # VBS wrapper (no window flash)
├── vpn-status.ps1        # Status review script
├── vpn-monitor.log       # Activity log
├── install-task.bat      # Install 15-min scheduled task
└── autofill_email.py     # Login automation
```

## Scheduled Task

- **Name:** VPN Monitor Check
- **Interval:** Every 15 minutes
- **Execution:** Completely hidden (VBS wrapper)

## Reinstall Task

Run as admin:
```
.\install-task.bat
```
