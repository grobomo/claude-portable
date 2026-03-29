# Blueprint Auto-Enable

- mcp-manager auto-injects `client_id` and auto-enables blueprint-extra
- client_id is just a label (project name), not a secret
- Full workflow docs in `blueprint-extra-mcp/CLAUDE.md`
- If blueprint seems broken, check `call.ts` middleware, not blueprint itself
