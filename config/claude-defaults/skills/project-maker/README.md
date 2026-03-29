# project-maker

Claude Code skill for creating and managing projects.

## Features

- **CRUD operations** for Claude Code projects
- Multiple project templates (Python, Node, MCP, minimal)
- Automatic git repo and GitHub creation
- Wiki page creation
- Cross-platform support

## Installation

No installation required - this skill is part of the claude-skills meta-repo.

## Usage

### Natural Language

Just say things like:
- "create a new project for my todo app"
- "list my projects"
- "delete the old-test project"

### Commands

```bash
python main.py create [name]   # Create new project
python main.py list            # List all projects
python main.py info <name>     # Show details
python main.py delete <name>   # Delete project
python main.py sync <name>     # Sync to git/wiki
python main.py config          # Configure settings
```

## Templates

- **python** - Python project with tests and requirements.txt
- **node** - Node.js project with package.json
- **mcp** - MCP server using FastMCP
- **minimal** - Just CLAUDE.md and .gitignore

## Configuration

Settings stored in `~/.claude-skills/config.yaml`:

```yaml
project_folder: /path/to/your/projects
wiki_space: ~username
github_org: your-username
```

## Repository

https://github.com/${TMEMU_ACCOUNT}/project-maker

## License

Private - internal use only.
