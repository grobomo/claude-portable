# Rule File Hygiene

- One topic per rule file. Never dump multiple unrelated gotchas into one file.
- Name files descriptively: `token-handling.md`, `rone-portal.md`, not `session-gotchas.md`.
- Path-scope rules to the project they apply to (`.claude/rules/` in project dir, not `~/.claude/rules/`) unless truly global.
- Before creating a rule, check if an existing rule covers the topic — update it instead of creating a duplicate.
- Keep rules under 20 lines. If longer, split into multiple files.
