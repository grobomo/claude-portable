---

name: claude-report
description: Generate inventory reports for MCP servers, skills, and hooks
keywords:
  - report
  - inventory
  - reports

---

# Claude Report

Generate interactive HTML inventory of Claude Code MCPs, skills, and hooks with security awareness.

## Usage

```bash
python main.py [--output report.html] [--quick]
```

## Options
- `--output FILE` - Output file path (default: claude_report_YYYYMMDD_HHMMSS.html)
- `--quick` - Skip full home scan, only check known locations
- `--json` - Output JSON instead of HTML
- `--md` - Output legacy markdown instead of HTML
- `--no-open` - Don't auto-open report in browser
- `--console-only` - Only print summary to console, no file

## Default Output: Interactive HTML

Self-contained dark-themed HTML page with:
- Stats bar (MCP count, skill count, hook count, warning count)
- Expandable sections for MCP Servers, Skills, Hooks, Security Flags
- Color-coded badges (running/stopped/disabled/active/archived/orphaned)
- Hook event flow visualization
- Auto-opens in default browser after generation

Style matches hook-flow-report.html (dark #0d1117 background, blue/green/amber/purple badges).

## What It Scans

- All MCP server definitions (server.py, .mcp.json, servers.yaml)
- All skill definitions (SKILL.md, skill-registry.json)
- All hook scripts (*.js in hook paths, settings.json hooks config)
- All referenced files from configs

## Security Checks

Flags: files outside expected locations, external URLs, base64/encoded content,
eval()/exec() calls, recently modified files (24h), orphaned references.
