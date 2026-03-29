# Build Output Paths

- mcp-manager tsup outputs to `build/` (--out-dir build)
- `package.json` main and start must point to `build/`, not `dist/`
- After changing build config, verify package.json paths match
