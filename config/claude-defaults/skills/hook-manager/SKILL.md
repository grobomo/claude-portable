---
name: hook-manager
description: "Create and manage Claude Code hooks. Replaced by hook-runner (grobomo/hook-runner)."
keywords:
  - hook
  - hooks
  - pretooluse
  - posttooluse
  - stop
  - matcher
  - enforcement
---

# Hook Manager

**Replaced by [hook-runner](~/.claude/hooks/README.md)** (`grobomo/hook-runner`).

All hook code lives in `~/.claude/hooks/`. See the README there for architecture, module contract, and how to add new modules.

Quick reference:
- Runners: `run-stop.js`, `run-pretooluse.js`, `run-posttooluse.js`
- Modules: `run-modules/<Event>/*.js`
- Config: `~/.claude/settings.json` `hooks` section
