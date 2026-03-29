---
id: code-review
name: code-review
description: Automated config consistency checks, secret scanning with credential-manager integration, and OWASP/CVE delegation to external security MCP servers.
keywords:
  - review
  - consistency
  - stale
  - phantom
  - drift
  - secrets
  - tokens
  - owasp
  - vulnerability
  - cve
  - references
enabled: true
---

# Code Review Skill

Automated review engine that catches config consistency issues, stale references, secret leaks, and security vulnerabilities across your Claude Code setup.

## Features

### Category 1: Config Consistency
- **Phantom tools** -- find `mcp__*__` references in docs/instructions that don't match real MCP tools
- **Path drift** -- find same-name files in different directories with different content (hash mismatch)
- **Embedded vs disk** -- compare instruction strings in setup.js files with on-disk .md files
- **Dead references** -- find file paths mentioned in instructions/docs that don't exist on disk
- **DRY violations** -- find identical path arrays/strings duplicated across JS/PY files

### Category 2: Secret Scanning (credential-manager integration)
- **Config file secrets** -- scan .claude.json, servers.yaml, CLAUDE.md, instructions, setup.js for tokens/keys
- **Cross-reference keyring** -- check if found secrets have a credential-manager entry; suggest migration if not
- **Env file audit** -- delegate to `credentials audit` for .env scanning
- **Headers/auth in YAML** -- check servers.yaml `headers:` and `env:` for plaintext Bearer tokens
- **Git history check** -- find secrets that were ever committed (even if since removed)

### Category 3: OWASP / CVE (delegates to external tools)
- If `gitleaks-mcp` running: deep git history secret scan
- If `semgrep-mcp` running: SAST + SCA + secrets (5000+ rules)
- If `nuclei-mcp` running: OWASP Top 10 + CVE template scan
- If none running: fall back to `security-scan` skill for basic vuln patterns
- Dedup all findings across tools, normalize severity levels

## Usage

```
/code-review                          # Review ~/.claude/ config
/code-review /path/to/project         # Review a specific project
/code-review --secrets-only           # Only scan for secrets
/code-review --config-only            # Only check config consistency
```

## Output Format

```
=== CODE REVIEW REPORT ===

[CONFIG] 3 issues found
  CRITICAL  mcpm-reload-flow.md:20 references non-existent tool mcp__mcp-manager__reload
  WARNING   servers.yaml exists in 2 locations, content differs (hash mismatch)
  INFO      setup.js:59 embedded instruction differs from mcp-management.md:52

[SECRETS] 2 issues found
  CRITICAL  servers.yaml:193 plaintext Bearer token in headers.Authorization
            -> Not in credential store. Run: credential-manager store svc/AUTH_TOKEN
  WARNING   .claude.json had plaintext JWT (removed in commit abc, still in git history)

[SECURITY] 1 issue found (via security-scan)
  WARNING   scanner.py found eval() usage in hooks/archive/old-hook.js:42

=== ACTIONS ===
  1. Fix 1 phantom tool reference
  2. Migrate 1 plaintext secret to credential store
  3. Archive 1 stale config copy
```

## Workflow

1. Claude runs `node ~/.claude/skills/code-review/review.js [target-path]`
2. review.js outputs JSON report to stdout
3. Claude reads the JSON, formats it as the report above
4. Claude can auto-fix config issues (phantom tools, dead refs) or suggest credential-manager commands for secrets

## Files

- `SKILL.md` - This documentation
- `setup.js` - Routing instruction installer + optional security MCP registration
- `review.js` - Main review engine (Node.js, no deps)
