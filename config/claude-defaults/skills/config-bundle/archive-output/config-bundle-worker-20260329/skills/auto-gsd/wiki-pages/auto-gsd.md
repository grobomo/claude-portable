---
title: Auto-GSD - Automatic Task Tracking
space_key: ~622a1696db58c100687da202
parent_id: 1983613169
---

# Auto-GSD

Automatic task tracking and autonomous decision-making for Claude Code.

## Overview

Auto-GSD ensures every task has defined completion criteria before execution, and enables Claude to work autonomously by auto-answering questions based on context.

## Components

| Hook | Event | Purpose |
|------|-------|---------|
| auto-gsd.js | UserPromptSubmit | Creates .planning/ structure |
| gsd-gate.js | PreToolUse | Blocks Write/Edit until PLAN.md exists |
| autonomous-decision.js | PreToolUse | Auto-answers questions |
| preference-learner.js | UserPromptSubmit | Learns from corrections |
| gsd-verifier-check.js | PostToolUse | Exits autonomous mode on completion |

## Workflow

1. **User Request** → auto-gsd.js creates .planning/ if needed
2. **Claude Plans** → Writes PLAN.md with goal + success criteria
3. **Claude Executes** → gsd-gate.js allows Write/Edit after PLAN.md exists
4. **Questions Arise** → autonomous-decision.js auto-answers using context
5. **Task Complete** → gsd-verifier-check.js disables autonomous mode

## File Structure

```
.planning/
├── ROADMAP.md          # Mode marker
├── STATE.md            # Completed tasks
├── config.json         # Settings
└── quick/
    └── 001-task-name/
        ├── 001-PLAN.md
        └── 001-SUMMARY.md
```

## Autonomous Mode

- **Enabled by default** on session start
- Reads GSD context (PLAN.md, STATE.md) + user preferences
- Calls `claude -p` to decide best option
- Learns from user corrections
- **Only exits** when GSD verifier confirms completion

## Manual Control

```bash
~/.claude/hooks/autonomous-mode.sh status
~/.claude/hooks/autonomous-mode.sh off
~/.claude/hooks/autonomous-mode.sh on
```

## Related

- [GSD Skill Documentation](/wiki/spaces/~622a1696db58c100687da202/pages/GSD)
- [Claude Code Hooks](/wiki/spaces/~622a1696db58c100687da202/pages/Hooks)
