# Injector Manager Skill

Manages the unified `skill-mcp-claudemd-injector` hook that provides context injection.

## What It Does

The injector hook runs on every prompt and injects relevant context:

| Module | Source | Output |
|--------|--------|--------|
| **claudemd** | `~/.claude/CLAUDE.md` | Global instructions |
| **skill** | `skill-registry.json` + keyword match | Skill documentation |
| **mcp** | `servers.yaml` + keyword match | MCP server suggestions |

## Setup

Run `/injector-setup` to:
1. Verify hook file exists and is executable
2. Verify hook is registered in settings.json
3. Verify registries exist (skill-registry.json, servers.yaml)
4. Test hook execution

## Files

```
~/.claude/hooks/
├── skill-mcp-claudemd-injector.js  # The unified hook
├── skill-registry.json              # Skill keywords
└── hooks.log                        # Logs (check with: tail ~/.claude/hooks/hooks.log)

MCP/mcp-manager/
└── servers.yaml                     # MCP server keywords
```

## Log Format

Each module logs separately:
```
[skill-mcp-claudemd-injector:claudemd] injected global CLAUDE.md
[skill-mcp-claudemd-injector:skill] injected 2 skills: hooks, v1-api
[skill-mcp-claudemd-injector:mcp] suggested 1 MCPs: v1-lite
```

## Troubleshooting

```bash
# Check if hook fires
tail -20 ~/.claude/hooks/hooks.log | grep injector

# Test hook manually
echo '{"prompt":"test hooks"}' | node ~/.claude/hooks/skill-mcp-claudemd-injector.js

# Verify settings.json has hook
grep "skill-mcp-claudemd-injector" ~/.claude/settings.json
```
