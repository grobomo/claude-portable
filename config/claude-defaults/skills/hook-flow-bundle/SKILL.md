---



name: hook-flow-bundle
description: Export and install Claude Code hook/skill workflows as portable bundles
keywords:
  - bundle
  - workflow
  - portable
  - package
  - claude


---

# Workflow Bundle

Portable Claude Code workflow - hooks, skills, MCP configs, and GSD in one package.

## What's Included

```
workflow-bundle/
├── hooks/                    # All custom hooks
│   ├── skill-mcp-claudemd-injector.js  # Unified context injector
│   ├── auto-gsd.js                     # GSD integration
│   ├── hook-logger.js                  # Shared logging
│   └── preference-learner.js           # User preference tracking
├── registries/
│   ├── skill-registry.json   # Skill keywords
│   └── servers-template.yaml # MCP server template
├── config/
│   └── hooks-config.json     # Hook configuration for settings.json
└── gsd/                      # GSD workflow package
```

## Commands

### Export Current Workflow
```bash
node export-workflow.js
```
Creates `workflow-export-YYYYMMDD.zip` with your current hooks, registries, and configs.

### Install on Fresh System
```bash
node install-workflow.js [bundle.zip]
```
Installs hooks, registries, and updates settings.json.

### Verify Installation
```bash
node health-check.js
```
Verifies all components are properly installed.

## Quick Start (Fresh Install)

```bash
# 1. Clone/download this skill
# 2. Run installer
cd ~/.claude/skills/workflow-bundle
node install-workflow.js

# 3. Verify
node health-check.js
```

## Manual Installation

If you prefer manual setup:

1. Copy `hooks/*` to `~/.claude/hooks/`
2. Copy `registries/skill-registry.json` to `~/.claude/hooks/`
3. Merge `config/hooks-config.json` into `~/.claude/settings.json`
4. Edit `servers-template.yaml` with your MCP server paths
