---

name: rule-manager
description: "Manage context-aware rule files - list, add, remove, enable, disable, match. Part of super-manager."
keywords:
  - rule
  - rules
  - context
  - frontmatter
  - matching
  - context-aware
  - match
  - part

---

# Rule Manager

Manage context-aware rule .md files with YAML frontmatter. Part of super-manager.

## What Are Rules?

Markdown files in `~/.claude/rule-book/` that contain contextual guidance. Each has YAML frontmatter with keywords - when a prompt matches keywords, the rule content is injected as context.

### Frontmatter Format

```yaml
---
id: bash-scripting
name: Bash Scripting Safety
keywords: [bash, script, heredoc, js, javascript]
enabled: true
priority: 10
action: Use heredoc pattern for inline JS
---
# Content here...
```

### Fields

| Field | Required | Description |
|-------|----------|-------------|
| id | No | Unique identifier (derived from filename if missing) |
| name | No | Human-readable name |
| keywords | **Yes** | Array of trigger words/phrases for matching |
| enabled | No | Default true |
| priority | No | Lower = higher priority |
| action | **Recommended** | Short phrase shown in TUI describing what tool to use (e.g. "Use wiki-api skill", "Use credential-manager skill"). Shown as `-> action` in the `[SM] Loaded` line so user sees at a glance what tool the rule recommends. |

## WHY This System Exists

### The Core Problem: Claude Forgets Everything Between Sessions

Every new Claude Code session starts with zero memory. The user has to re-teach the same lessons over and over: "use the CLI tool not a custom script", "don't assume things are broken -- try them first", "never ask me to do manual steps". Rules are how those lessons persist. When the user corrects Claude, a rule gets written so that correction sticks FOREVER -- not just for the current session.

### How It Works

Rules are markdown files in `~/.claude/rule-book/` with YAML frontmatter containing keywords. When a user prompt matches keywords, the hook (`sm-userpromptsubmit.js`) injects the full rule content into Claude's context. Stop rules (`sm-stop.js`) check Claude's response text against regex patterns and block if matched.

This means:
- **UserPromptSubmit rules** fire BEFORE Claude thinks -- they guide the approach
- **Stop rules** fire AFTER Claude responds -- they catch bad habits
- **PreToolUse rules** fire before a tool call -- they block dangerous actions

### Why Not Just Put Everything in CLAUDE.md?

Claude Code natively loads ALL .md files from `~/.claude/rules/` on every prompt (~50KB wasted context). Rules in `~/.claude/rule-book/` are only injected when keywords match, so Claude gets only the rules relevant to the current task.

**CLAUDE.md** = static project facts (IPs, URLs, architecture, TODOs). Small, always loaded.
**rule-book/** = behavioral rules, routing, corrections. Keyword-matched, only loaded when relevant.

### The "Always Document WHY" Rule

Every rule file must explain WHY it exists, not just WHAT to do. When Claude understands the reason behind a rule, it follows the spirit even in edge cases the rule doesn't explicitly cover.

### Creating Rules

1. Read the RULE-GUIDELINES and writing-rules rules first (in `rule-book/UserPromptSubmit/`)
2. Always include `min_matches` in frontmatter (default is 2 if omitted)
3. Pick keywords from words the user would actually type, not abstract concepts
4. Write rules in `rule-book/`, NEVER in `rules/` (native loading = wasted context)

## Setup

Rule-manager auto-installs via three layers:
1. `super-manager/setup.js` calls `rule-manager/setup.js` on initial install
2. `sm-sessionstart.js` checks rule-book dirs + CLAUDE.md marker on every session
3. `rule-manager/setup.js` can be run directly: `node ~/.claude/skills/rule-manager/setup.js`

Setup creates:
- `~/.claude/rule-book/UserPromptSubmit/` - keyword-matched rules
- `~/.claude/rule-book/Stop/` - response-checked rules
- `~/.claude/rule-book/PreToolUse/` - pre-tool gate rules
- `~/.claude/rule-book/archive/` and `backups/`
- CLAUDE.md section explaining rule-book architecture (marker-based, idempotent)

## Commands

```bash
# List all rules
python ~/.claude/super-manager/super_manager.py rules list

# Add a new rule
python ~/.claude/super-manager/super_manager.py rules add RULE_ID

# Remove (archives, never deletes)
python ~/.claude/super-manager/super_manager.py rules remove RULE_ID

# Enable/disable
python ~/.claude/super-manager/super_manager.py rules enable RULE_ID
python ~/.claude/super-manager/super_manager.py rules disable RULE_ID

# Verify all rules healthy
python ~/.claude/super-manager/super_manager.py rules verify

# Test keyword matching
python ~/.claude/super-manager/super_manager.py rules match "some prompt text"
```

## Architecture

Single directory -- `~/.claude/rule-book/`:

```
~/.claude/rule-book/
  UserPromptSubmit/   # Injected when prompt keywords match (sm-userpromptsubmit.js)
  Stop/               # Checked against response text (sm-stop.js)
  PreToolUse/         # Checked before tool calls (sm-pretooluse.js)
  archive/            # Removed/disabled rules
  backups/            # Timestamped backups before changes
```

State files (logs, caches, README.md, templates) stay in `~/.claude/rules/` -- only .md rule files moved to rule-book/.

### Hook Integration

| Hook | Reads from | Purpose |
|------|-----------|---------|
| sm-userpromptsubmit.js | rule-book/UserPromptSubmit/ | Keyword match -> inject rule content |
| sm-stop.js | rule-book/Stop/ | Pattern match on Claude response text |
| sm-pretooluse.js | rule-book/PreToolUse/ | Gate/block tool calls |

## Dependency

Part of **super-manager** (`~/.claude/super-manager/`).
