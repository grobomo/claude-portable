---
name: super-manager
description: Unified manager for Claude Code configuration - hooks, skills, MCP servers. Routes to sub-managers.
---

# Super Manager

Routes to the right sub-manager for configuration tasks.

## Sub-Managers

| Component | Project | What It Does |
|-----------|---------|-------------|
| Hooks | [hook-runner](~/.claude/hooks/) (`grobomo/hook-runner`) | Modular hook system |
| Skills | skill-manager | Skill inventory in `~/.claude/skills/` |
| MCP Servers | [mcp-manager](~/Documents/ProjectsCL1/MCP/mcp-manager/) | Server lifecycle via mcpm |
| Credentials | credential-manager | OS keyring for secrets |
| Rules | rule-manager | Context-aware rule files in `~/.claude/rules/` |

## Key Principles

- **One runner per event** — never add separate hook entries to settings.json
- **Modules are independent** — each .js file in run-modules/ is self-contained
- **First deny wins** — runner stops at first module that returns deny/block
- **Never delete, always archive** — old files go to archive/ with date stamp
- **Docs match reality** — if it's not on disk, it's not in the docs
