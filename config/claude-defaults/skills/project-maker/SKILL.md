---

name: project-maker
description: Initialize new project scaffolding with standard structure
keywords:
  - initialize
  - scaffold
  - projects
  - details
  - python
  - gitwiki
  - creates
  - lists
  - removes

---

# Project Maker

CRUD operations for Claude Code projects in your projects folder.

## Natural Language

Just say things like:
- "create a new project for my todo app"
- "list my projects"
- "delete the old-test project"

A hook automatically detects these phrases and guides Claude to use project-maker.

## Usage

```bash
python main.py create [name]     # Create new project
python main.py list              # List all projects
python main.py info <name>       # Show project details
python main.py delete <name>     # Delete project
python main.py sync <name>       # Sync to git/wiki
python main.py config            # Configure settings
```

## Commands

### create
Creates a new project:
- Prompts for project name and template
- Creates folder in projects directory
- Initializes git repo
- Creates CLAUDE.md
- Optionally creates GitHub repo (via `gh` CLI)
- Optionally creates wiki page

### list
Lists all projects in your projects folder:
- Shows git status
- Shows if has CLAUDE.md

### info
Shows detailed project information:
- Path and components
- Git remote URL

### delete
Removes a project:
- Requires typing project name to confirm
- Permanently deletes folder

### sync
Syncs project to git and wiki:
- Commits and pushes changes
- Updates wiki page (if configured)

### config
Configures settings:
- Projects folder location
- Wiki space
- GitHub org/username

## Templates

- **python** - Python project with tests
- **node** - Node.js project
- **mcp** - MCP server (FastMCP)
- **minimal** - Just CLAUDE.md and .gitignore

## Cross-Platform

Works on Windows, Mac, and Linux. No hardcoded paths.

## Configuration

User settings stored in `~/.claude-skills/config.yaml`:

```yaml
project_folder: /path/to/your/projects
wiki_space: ~username
github_org: your-username
```

Auto-detects project folder on first run.

## Difference from skill

| Feature | project | skill |
|---------|---------|-------|
| Location | New folder in projects dir | `.claude/skills/` in current project |
| Git | New repo | Existing project repo |
| Wiki | New page | Updates project page |
| Use case | New standalone project | Add capability to existing project |
