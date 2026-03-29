---



name: claude-backup
description: Backup and restore Claude Code hooks, settings, and skills
keywords:
  - backup
  - reinstall
  - snapshot
  - claudeskillsclaude-backupbackupsh
  - latest
  - specific
  - backups
  - claude


---

# Claude Backup Skill

Backup and restore Claude Code configuration + MCP servers.

## Usage

```bash
~/.claude/skills/claude-backup/backup.sh           # backup
~/.claude/skills/claude-backup/backup.sh restore   # restore latest
~/.claude/skills/claude-backup/backup.sh restore <name>  # restore specific
~/.claude/skills/claude-backup/backup.sh list      # list backups
```

## What's Backed Up

```
~/.claude/
├── settings.json      # hooks, model prefs
├── CLAUDE.md          # global instructions
├── hooks/             # hook scripts, skill-registry
└── skills/            # custom skills

mcp-manager/
├── servers.yaml       # MCP server configs
├── .env               # env vars
├── capabilities-cache.yaml
└── managed-servers/   # managed server data
```

## Auto-Backup

Runs automatically on SessionStart, SessionEnd, and PreCompact. Keeps last 10.

Location: `~/.claude/backups/`
