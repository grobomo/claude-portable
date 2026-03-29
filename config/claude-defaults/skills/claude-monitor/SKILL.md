---
keywords:
  - claude
---

# Claude Monitor

Cross-platform process monitor for Claude Code sessions. Maps process trees, measures CPU/RAM, detects orphan processes, audits npm cache, and classifies tab state (ACTIVE vs IDLE).

## Usage

```bash
# Full report (default 5-second sample)
node ~/.claude/skills/claude-monitor/monitor.js

# Quick snapshot (1-second sample)
node ~/.claude/skills/claude-monitor/monitor.js --sample 1

# JSON output (for piping/logging)
node ~/.claude/skills/claude-monitor/monitor.js --json

# Security audit only (npx cache + orphan detection)
node ~/.claude/skills/claude-monitor/monitor.js --security

# Continuous monitoring (repeats every N seconds)
node ~/.claude/skills/claude-monitor/monitor.js --watch 10

# Save report to file
node ~/.claude/skills/claude-monitor/monitor.js --out ~/Downloads/claude-monitor-report.txt
```

## What It Reports

| Section | Details |
|---------|---------|
| **Tab Process Trees** | claude.exe -> mcp-manager -> blueprint/servers -> bash shells |
| **CPU per Tab** | Sampled over configurable window, broken into kernel/user |
| **CPU per Child** | Shows which child process is burning CPU |
| **RAM per Tab** | Total working set including children |
| **Tab State** | ACTIVE (bash children running) vs IDLE (no active children) |
| **Orphan Processes** | node/npm/npx not under any Claude tab |
| **NPX Cache Audit** | Lists all cached packages with dates, flags unknown ones |
| **Summary** | Total CPU, total RAM, idle tab count, alerts |

## Cross-Platform Support

| Platform | Process Enumeration | CPU Measurement |
|----------|-------------------|-----------------|
| Windows | wmic / PowerShell | KernelModeTime + UserModeTime delta |
| macOS | ps -eo pid,ppid,pcpu,rss,comm | ps cpu% (instantaneous) |
| Linux | /proc/[pid]/stat | jiffies delta from /proc |

## Known Packages (Security Allowlist)

The security audit checks npx cache against a known-good list. Unknown packages are flagged for review. The allowlist covers common MCP servers, Claude SDK, build tools, and test frameworks.

## Triggers

- `monitor claude` / `claude processes` / `cpu usage` / `process tree`
- `security audit` / `npm audit` / `orphan processes`
