# ~/.claude Configuration Rules

## settings.json

- `mcpServers` is NOT a valid field in settings.json. MCP servers go in `.mcp.json` (project-level) or are managed by mcp-manager via `servers.yaml`.
- Do NOT modify `env` unless explicitly instructed.
- `enableAllProjectMcpServers: true` means all project `.mcp.json` servers are auto-approved.

## MCP Architecture

- `mcp-manager` is the single entry point. It's the only MCP in `.mcp.json`.
- mcp-manager reads `servers.yaml` for all backend servers (blueprint-extra, v1-lite, wiki-lite, etc.).
- mcp-manager handles: auto-start, idle timeout (default 1hr), start/stop/restart, tool proxying.
- Blueprint Extra (`blueprint-extra` in servers.yaml) is the browser automation server.

## Skills

- Skills live in `~/.claude/skills/<skill-name>/`
- Each skill has a `SKILL.md` with usage instructions.
- Credentials are stored via credential-manager (OS keyring), never in plaintext.
