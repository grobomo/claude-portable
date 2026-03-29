# hook-runner

Modular hook runner system for Claude Code. One runner per event type, modules in folders. Replaces the old hook-manager skill.

## Architecture

```
hooks/
├── run-stop.js                          # Stop event runner
├── run-pretooluse.js                    # PreToolUse event runner
├── run-posttooluse.js                   # PostToolUse event runner
├── run-modules/
│   ├── Stop/
│   │   └── auto-continue.js            # Keep Claude working, don't stop to ask
│   ├── PreToolUse/
│   │   └── enforcement-gate.js         # Git repo + clean tree + TODO.md checks
│   └── PostToolUse/
│       └── rule-hygiene.js             # Validates rule files are granular
└── archive/                             # Old versions (never delete)
```

## How It Works

Each `run-*.js` runner:
1. Reads stdin synchronously (`fs.readFileSync(0)`)
2. Loads all `.js` files from `run-modules/<Event>/`
3. Calls each module with parsed input
4. First deny/block wins
5. If all return `null`, action is allowed

## Module Contract

```javascript
module.exports = function(input) {
  // input fields depend on event type (see Event Types below)
  if (problem) {
    return { decision: "deny", reason: "Why it's blocked" };
  }
  return null; // pass
};
```

Modules must be synchronous. No async/await, no Promises. Use `require()` not `import`.

## Event Types

| Event | Runner | Matcher? | stdin Fields | Block Key |
|-------|--------|----------|-------------|-----------|
| Stop | run-stop.js | No | `session_id, stop_hook_active, last_assistant_message` | `"block"` |
| PreToolUse | run-pretooluse.js | Yes | `session_id, tool_name, tool_input` | `"deny"` |
| PostToolUse | run-posttooluse.js | Yes | `session_id, tool_name, tool_input, tool_response` | `"block"` |

Runners handle output wrapping (PreToolUse adds `hookSpecificOutput`).

## Adding a Module

1. Create `run-modules/<Event>/your-module.js`
2. Export a sync function matching the contract
3. Modules run alphabetically — prefix with `01-` for ordering
4. If the event has no runner yet, copy any `run-*.js` and change the path

## settings.json

```json
{
  "hooks": {
    "Stop": [{"hooks": [{"type": "command", "command": "node \"$HOME/.claude/hooks/run-stop.js\"", "timeout": 5}]}],
    "PreToolUse": [
      {"matcher": "Edit", "hooks": [{"type": "command", "command": "node \"$HOME/.claude/hooks/run-pretooluse.js\"", "timeout": 5}]},
      {"matcher": "Write", "hooks": [{"type": "command", "command": "node \"$HOME/.claude/hooks/run-pretooluse.js\"", "timeout": 5}]}
    ],
    "PostToolUse": [
      {"matcher": "Write", "hooks": [{"type": "command", "command": "node \"$HOME/.claude/hooks/run-posttooluse.js\"", "timeout": 5}]},
      {"matcher": "Edit", "hooks": [{"type": "command", "command": "node \"$HOME/.claude/hooks/run-posttooluse.js\"", "timeout": 5}]}
    ]
  }
}
```
