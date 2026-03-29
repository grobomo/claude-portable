# Claude Report Skill - Implementation Plan

## Goal
Create a comprehensive inventory tool for Claude Code MCPs, skills, and hooks with security awareness.

## Features
1. **Full home folder scan** - no exclusions
2. **Follow references** - if config points to file, scan that file
3. **Tree view output** - grouped by category and status
4. **Table summaries** - hook flow, tool descriptions
5. **Security flags** - suspicious patterns, orphaned files, external URLs
6. **Dual output** - console + markdown report file
7. **Cross-platform** - Windows, Mac, Linux

## Files to Create
1. `SKILL.md` - skill documentation and keywords
2. `main.py` - main entry point
3. `scanners/mcp_scanner.py` - find MCP servers
4. `scanners/skill_scanner.py` - find skills
5. `scanners/hook_scanner.py` - find hooks
6. `reporters/tree_reporter.py` - tree view output
7. `reporters/table_reporter.py` - table summaries
8. `reporters/markdown_reporter.py` - MD file output
9. `utils/path_utils.py` - cross-platform path handling
10. `utils/security_checks.py` - flag suspicious patterns

## Scan Strategy
- Walk entire $HOME directory
- Match patterns: server.py, SKILL.md, *.js hooks, settings.json, .mcp.json
- Parse configs to find referenced files
- Recursively scan referenced paths
- Classify: registered vs unregistered, active vs archived

## Security Flags
- Files outside ~/.claude/ or known MCP paths
- Scripts with http/https URLs
- Base64 encoded strings
- eval() or exec() calls
- Recent modifications (last 24h)
- Missing files (referenced but not found)
