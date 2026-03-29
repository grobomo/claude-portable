# skill-maker

Claude Code skill for creating and managing skills.

## Features

- **CRUD operations** for Claude Code skills
- Automatic git repo and GitHub creation
- Credential scanning from existing MCP servers and skills
- Template-based skill creation
- Natural language detection via hooks

## Installation

No installation required - this skill is part of the claude-skills meta-repo.

## Usage

### Natural Language

Just say things like:
- "create a new skill for the Slack API"
- "list all skills"
- "delete the old-api skill"

### Commands

```bash
python main.py create [name]   # Create new skill with git repo
python main.py list            # List all skills
python main.py info <name>     # Show skill details
python main.py update <name>   # Refresh APIs
python main.py delete <name>   # Delete skill
python main.py sync [name]     # Sync to git/wiki
```

## Templates

- **api** - REST API wrapper with YAML configs (default)
- **browser** - Browser automation skill
- **launcher** - Application launcher
- **workflow** - Multi-step workflow

## What Gets Created

When you create a new skill:
1. Skill folder from template
2. README.md
3. Local git repository
4. GitHub repository (optional)
5. Submodule in claude-skills meta-repo (optional)

## Repository

https://github.com/${TMEMU_ACCOUNT}/skill-maker

## License

Private - internal use only.
