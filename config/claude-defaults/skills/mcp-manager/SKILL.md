---



name: mcp-manager
description: "Manage MCP servers via mcpm MCP tools. All operations go through mcpm directly."
keywords:
  - mcp
  - servers
  - reload
  - yaml
  - mcpm
  - blueprint
---

# MCP Manager

All MCP server operations go through **mcpm MCP tools** directly. Do NOT use super_manager.py for MCP.

## Auto-Installation (IMPORTANT - read first)

If `mcp__mcp-manager__mcpm` tool is NOT available, mcp-manager is not registered as an MCP server. Fix it:

```bash
node "$HOME/.claude/skills/mcp-manager/setup.js"
```

This auto-detects the mcp-manager build and creates `.mcp.json` in the current project directory. Then tell the user:

> Run `/mcp` in Claude Code to load mcp-manager. After that, all mcpm tools will be available.

If setup.js says "build not found", the user needs to build mcp-manager first:
```bash
cd "ProjectsCL1/MCP/mcp-manager" && npm run build
```
Then re-run setup.js.

## Operations (via mcpm MCP tools)

| Operation | mcpm Tool | Description |
|-----------|-----------|-------------|
| List servers | `list_servers` | Show all servers and status |
| Start server | `start` | Start a server by name |
| Stop server | `stop` | Stop a running server |
| Reload config | `reload` | Hot reload servers.yaml + .mcp.json |
| Add server | `add` | Add new server to registry + project |
| Remove server | `remove` | Remove server from registry + project |

## Configuration Files

| File | Purpose |
|------|---------|
| `servers.yaml` | Central registry (all server definitions) |
| `.mcp.json` | Project server list (which servers this project uses) |

## Architecture

```
mcpm (MCP server)           <-- does ALL the work
  |-- list_servers
  |-- start / stop / reload
  |-- add / remove

super-manager               <-- read-only awareness only
  |-- status: shows MCP count in dashboard
  |-- doctor: checks mcpm is installed
```

super-manager does NOT manage MCP servers. It verifies mcpm exists and shows MCP counts in the status dashboard. All actual MCP operations are delegated to mcpm.

## Troubleshooting: mcpm Tool Not Available

If the mcp-manager skill loads but you cannot call `mcp__mcp-manager__mcpm`, mcp-manager crashed on startup.

### Step 1: Verify the crash

Run manually to see the error:
```bash
cd "ProjectsCL1/MCP/mcp-manager" && node build/index.js
```

### Step 2: Common crashes and fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `Dynamic require of "X" is not supported` | Node 24+ strict ESM breaks bundled CJS packages | Add package to `external` in `build.mjs`, then `node build.mjs` |
| `Cannot find module` | Missing dependency | `npm install` in mcp-manager dir |
| `EADDRINUSE` | Port conflict | Kill stale process or restart session |

### Step 3: Rebuild if needed

```bash
cd "ProjectsCL1/MCP/mcp-manager" && node build.mjs
```

### Step 4: Reconnect WITHOUT restarting session

User runs `/mcp` in Claude Code CLI. This reconnects mcp-manager with the fixed build. No session restart needed.

### Step 5: Verify

```
mcp__mcp-manager__mcpm operation=list_servers
```

All 6 project servers should appear.

## Troubleshooting: v1-lite 403 AccessDenied

v1-lite uses credential-manager for API key. If you get 403:

1. Check credential exists: `python -c "import keyring; print(bool(keyring.get_password('claude-code', 'v1-lite/V1_API_KEY')))"`
2. Check .env has credential prefix: `V1_API_KEY=credential:v1-lite/V1_API_KEY`
3. After editing server.py, must restart: `mcpm stop v1-lite && mcpm start v1-lite`
