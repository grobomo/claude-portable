# Auto-GSD

Automatic task tracking and autonomous decision-making for Claude Code.

## Features

- **Auto-tracking**: Every task gets a PLAN.md before execution
- **Completion criteria**: Success criteria defined upfront
- **Autonomous mode**: Claude auto-answers questions using context
- **Preference learning**: Learns from user corrections

## Installation

Copy hooks to `~/.claude/hooks/`:
```bash
cp hooks/*.js ~/.claude/hooks/
cp hooks/*.sh ~/.claude/hooks/
```

Add to `~/.claude/settings.json`:
```json
{
  "hooks": {
    "UserPromptSubmit": [{"matcher": "*", "hooks": [
      {"type": "command", "command": "node ~/.claude/hooks/auto-gsd.js"},
      {"type": "command", "command": "node ~/.claude/hooks/preference-learner.js"}
    ]}],
    "PreToolUse": [
      {"matcher": "Write|Edit", "hooks": [
        {"type": "command", "command": "node ~/.claude/hooks/gsd-gate.js"}
      ]},
      {"matcher": "AskUserQuestion", "hooks": [
        {"type": "command", "command": "node ~/.claude/hooks/autonomous-decision.js"}
      ]}
    ],
    "PostToolUse": [{"matcher": "Task", "hooks": [
      {"type": "command", "command": "node ~/.claude/hooks/gsd-verifier-check.js"}
    ]}]
  }
}
```

## How It Works

```
User Request
     │
     ▼
┌────────────────┐
│  auto-gsd.js   │ Creates .planning/ if missing
└────────────────┘
     │
     ▼
┌────────────────┐
│  gsd-gate.js   │ Blocks Write/Edit until PLAN.md exists
└────────────────┘
     │
     ▼
┌────────────────┐
│ autonomous-    │ Auto-answers questions using claude -p
│ decision.js    │ Reads GSD context + user preferences
└────────────────┘
     │
     ▼
┌────────────────┐
│ gsd-verifier-  │ Disables autonomous mode when complete
│ check.js       │
└────────────────┘
```

## Files Created Per Task

```
.planning/
├── ROADMAP.md          # Project mode marker
├── STATE.md            # Completed tasks table
├── config.json         # GSD settings
└── quick/
    └── 001-task-name/
        ├── 001-PLAN.md     # Goal + success criteria
        └── 001-SUMMARY.md  # What was accomplished
```

## Autonomous Mode

**Default: ENABLED** on session start.

### Decision Flow
1. Claude calls AskUserQuestion
2. `autonomous-decision.js` intercepts
3. Reads: GSD PLAN.md, STATE.md, user_preferences.json
4. Calls `claude -p` to decide best option
5. Outputs decision, blocks question
6. Claude proceeds with decided answer

### Exiting Autonomous Mode
Only when GSD verifier agent confirms task complete.

### Learning
If user corrects ("no", "wrong", etc.), `preference-learner.js` saves the correction for future decisions.

### Manual Control
```bash
~/.claude/hooks/autonomous-mode.sh status  # Check state
~/.claude/hooks/autonomous-mode.sh off     # Disable
~/.claude/hooks/autonomous-mode.sh on      # Enable
```

## Configuration

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

## License

MIT
