---



name: skill-maker
description: Create new skills from templates. Use when user says "make a skill", "create a skill", or "new skill for X".
keywords:
  - skill
  - template
  - maker
  - scaffold
  - skills
  - details
  - refresh
  - python
  - gitwiki
  - creates
  - lists


---

# Skill Maker

CRUD operations for Claude Code skills.

## Templates

| Template | Use For |
|----------|---------|
| **api** | REST API wrappers (YAML configs + executor) |
| **browser** | HTML/browser UIs (server.py + generate.py) |
| **workflow** | Python workflows (main.py with steps) |
| **launcher** | Simple command launchers |

## When User Says "Make a Skill"

1. Parse what they want: `"make a skill to poop skittles"` -> name: `poop-skittles`
2. Determine template:
   - API/integration -> `api`
   - UI/viewer/editor -> `browser`
   - Multi-step process -> `workflow`
   - Simple launcher -> `launcher`
3. Run: `python main.py create <name>`
4. Select template when prompted
5. If new template type needed, create in `templates/` first

## Usage

```bash
python main.py create [name]     # Create new skill
python main.py list              # List all skills
python main.py info <name>       # Show skill details
python main.py update <name>     # Update skill (refresh APIs)
python main.py delete <name>     # Delete skill
python main.py sync [name]       # Sync to git/wiki
```

## Commands

### create
Creates a new skill from template:
- Prompts for skill name and template type
- For API skills: researches key patterns with Claude
- Scans existing MCP servers and skills for credentials
- Asks permission before scanning/using found keys
- Stores documentation URL in `reference/DOCS.md`
- Commits to git

### list
Lists all skills in the project with status:
- Shows if configured (has .env)
- Shows operation count for API skills

### info
Shows detailed information about a skill:
- Path and components
- Operation count
- Documentation URL

### update
Updates an existing skill:
- Runs `refresh_api.py --apply` for API skills
- Runs `analyze_userstories.py` for user story analysis
- Commits changes to git

### delete
Removes a skill:
- Requires typing skill name to confirm
- Removes from git and pushes

### sync
Syncs skills to git and wiki:
- Commits and pushes changes
- Updates wiki page (if configured)

## Templates

- **api** - REST API wrapper with YAML configs (default)

## Pre-Publish Sanitization (MANDATORY)

When creating skills intended for sharing or marketplace publishing, scan ALL files
for personal/machine-specific content before committing.

### Scan command

```bash
grep -rn "/home/claude\|/home/claude\|OneDrive - TrendMicro\|joel-ginsberg\|joeltest\|${USER_NAME}" <dir> \
  --include="*.py" --include="*.js" --include="*.json" --include="*.md" \
  --include="*.sh" --include="*.yaml" --include="*.yml"
```

### What to fix

| Pattern | Replace with |
|---------|-------------|
| Hardcoded home paths (`/home/claude/...`) | `os.path.join(os.homedir(), ...)` or `$HOME/...` |
| Org-specific paths (`OneDrive - OrgName/...`) | Dynamic discovery via `glob` patterns |
| Personal GitHub usernames | `grobomo` or generic placeholder |
| Personal namespaces, account IDs | Generic placeholders (`my-namespace`, `my-account`) |

### Registry files must be empty templates

Runtime-populated files (registries, caches) must ship as empty templates:
```json
{"hooks": [], "version": "1.0"}
```

If the scan finds ANY hits, fix them before publishing. Personal paths break every other machine.

## Cross-Platform

Works on Windows, Mac, and Linux. No hardcoded paths.

## Configuration

User settings stored in `~/.claude-skills/config.yaml`:
- `wiki_space` - Confluence space key for wiki sync
- `github_org` - GitHub org/user for repos
