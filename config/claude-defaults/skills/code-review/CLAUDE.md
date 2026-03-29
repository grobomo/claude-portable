# code-review/

Automated config consistency and secret scanning skill for Claude Code.

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | Skill definition, triggers, output format |
| `setup.js` | Installs routing instruction, checks dependencies |
| `review.js` | Main review engine (Node.js, no deps) |

## How It Works

`review.js` runs 3 categories of checks:

1. **Config consistency** -- phantom MCP tool refs, path drift (same-name files with different hashes), dead file references in docs
2. **Secret scanning** -- regex patterns for tokens/keys/passwords in config files, cross-references with credential-manager keyring
3. **Security delegation** -- defers to external MCP tools (gitleaks, semgrep, nuclei) or falls back to security-scan skill

Output is JSON to stdout. Claude reads the JSON and formats it as a structured report.

## Dependencies

- `setup-utils.js` (shared) -- for routing instruction install, backup/restore
- `credential-manager` (optional) -- cross-reference found secrets with keyring
- `security-scan` (optional) -- fallback vuln pattern scanning

## Testing

```bash
node ~/.claude/skills/code-review/review.js ~/.claude/instructions    # small scope
node ~/.claude/skills/code-review/review.js ~/.claude/skills          # medium scope
node ~/.claude/skills/code-review/review.js --config-only             # config checks only
node ~/.claude/skills/code-review/review.js --secrets-only            # secrets only
```

Full `~/.claude/` scan can be slow due to plugins/repos subdirectories.
