# Auto-GSD Skill

## Core Philosophy

**SLOW AND ACCURATE > FAST AND WRONG**

The purpose of auto-gsd is to FORCE Claude to use GSD tracking for ALL work.
Claude naturally wants to skip steps to be "helpful" and "fast" - this is wrong.
Every task must have a PLAN.md with success criteria BEFORE any tool execution.

## Non-Negotiable Rules

1. **ANY tool use requires GSD** - No exceptions for "small" tasks
2. **PLAN.md must exist before execution** - gsd-gate.js blocks tools until it does
3. **No skipping for convenience** - Remove all "skip if < 10 chars" type logic
4. **Verify completion against criteria** - Not just "I ran the commands"

## What Claude Must Do

BEFORE any task:
1. Create `.planning/quick/NNN-slug/`
2. Write `NNN-PLAN.md` with explicit success criteria
3. Only THEN execute tools

AFTER task:
1. Write `NNN-SUMMARY.md` documenting what was done
2. Verify each success criterion was met
3. Update `STATE.md` completion table

## Why This Exists

Claude's failure modes without enforcement:
- Declares work "done" without verification
- Skips planning because "it's obvious"
- Runs commands without defining success criteria
- Loses track of what was actually accomplished
- Context resets lose all progress tracking

## Hooks

| File | Event | Purpose |
|------|-------|---------|
| auto-gsd.js | UserPromptSubmit | Create .planning/ structure |
| gsd-gate.js | PreToolUse | BLOCK tools until PLAN.md exists |
| gsd-verifier-check.js | PostToolUse | Verify criteria were met |

## State Files

```
.planning/
├── ROADMAP.md          # Project marker
├── STATE.md            # Completed tasks table
├── config.json         # GSD settings
└── quick/
    └── NNN-task-name/
        ├── NNN-PLAN.md     # BEFORE: criteria
        └── NNN-SUMMARY.md  # AFTER: verification
```

## Config

`.planning/config.json`:
```json
{
  "mode": "yolo",
  "depth": "quick",
  "workflow": {
    "verifier": true
  }
}
```

`mode: yolo` means no user confirmations, NOT "skip GSD tracking"
