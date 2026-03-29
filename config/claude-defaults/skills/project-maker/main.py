#!/usr/bin/env python3
"""
Project Manager - CRUD operations for Claude Code projects

Cross-platform (Windows, Mac, Linux). No hardcoded paths.

Usage:
    python main.py create [name]     # Create new project
    python main.py list              # List all projects
    python main.py info <name>       # Show project details
    python main.py delete <name>     # Delete project
    python main.py sync [name]       # Sync to git/wiki
    python main.py config            # Configure settings
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

# Cross-platform paths
HOME = Path.home()
CONFIG_DIR = HOME / '.claude-skills'
CONFIG_FILE = CONFIG_DIR / 'config.yaml'

# Project templates (embedded)
TEMPLATES = {
    'python': {
        'files': {
            'requirements.txt': '# Project dependencies\n',
            '{name}/__init__.py': '',
            'tests/__init__.py': '',
            'tests/test_main.py': 'import pytest\n\ndef test_placeholder():\n    assert True\n',
        },
        'gitignore': '__pycache__/\n*.py[cod]\n.env\n.venv/\nvenv/\n.pytest_cache/\n'
    },
    'node': {
        'files': {
            'package.json': '{{\n  "name": "{name}",\n  "version": "0.1.0"\n}}\n',
            'index.js': '// Entry point\n',
        },
        'gitignore': 'node_modules/\n.env\ndist/\n'
    },
    'mcp': {
        'files': {
            'server.py': '#!/usr/bin/env python3\nfrom mcp.server.fastmcp import FastMCP\n\nmcp = FastMCP("{name}")\n\n@mcp.tool()\ndef hello(name: str = "World") -> str:\n    return f"Hello, {{name}}!"\n\nif __name__ == "__main__":\n    mcp.run()\n',
            'requirements.txt': 'mcp\nfastmcp\n',
        },
        'gitignore': '__pycache__/\n.env\n.venv/\n'
    },
    'minimal': {
        'files': {},
        'gitignore': '.env\n*.log\n'
    },
}


def load_config():
    """Load user config."""
    config = {'project_folder': '', 'wiki_space': '', 'github_org': ''}
    if CONFIG_FILE.exists():
        try:
            import yaml
            data = yaml.safe_load(CONFIG_FILE.read_text())
            if data:
                config.update(data)
        except Exception:
            pass
    return config


def save_config(config):
    """Save user config."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import yaml
        CONFIG_FILE.write_text(yaml.dump(config, default_flow_style=False))
    except ImportError:
        lines = [f"{k}: {v}" for k, v in config.items()]
        CONFIG_FILE.write_text('\n'.join(lines))


def prompt(msg, default=''):
    """Prompt with default."""
    if default:
        result = input(f"{msg} [{default}]: ").strip()
        return result if result else default
    return input(f"{msg}: ").strip()


def prompt_yes_no(msg, default='y'):
    """Yes/no prompt."""
    suffix = '[Y/n]' if default.lower() == 'y' else '[y/N]'
    result = input(f"{msg} {suffix}: ").strip().lower()
    if not result:
        return default.lower() == 'y'
    return result in ('y', 'yes')


def detect_project_folder():
    """Try to detect user's project folder."""
    candidates = []

    # Check OneDrive paths first (Windows)
    for onedrive in HOME.glob('OneDrive*'):
        candidates.append(onedrive / 'Documents' / 'ProjectsCL')
        candidates.append(onedrive / 'Documents' / 'Projects')

    candidates.extend([
        HOME / 'Projects',
        HOME / 'projects',
        HOME / 'Developer',
        HOME / 'dev',
        HOME / 'Documents' / 'Projects',
    ])

    for path in candidates:
        if path.exists() and path.is_dir():
            return path

    return HOME / 'Projects'


def list_projects(project_folder):
    """List all projects in the project folder."""
    projects = []
    folder = Path(project_folder)

    if not folder.exists():
        return projects

    for item in folder.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            proj_info = {
                'name': item.name,
                'path': item,
                'has_git': (item / '.git').exists(),
                'has_claude_md': (item / 'CLAUDE.md').exists(),
            }
            projects.append(proj_info)

    return projects


def create_claude_md(project_path, name):
    """Create CLAUDE.md for the project."""
    content = f"""# {name.replace('-', ' ').title()}

## Project Structure

```
{name}/
├── CLAUDE.md          # This file
├── .gitignore
└── ...
```

## Getting Started

```bash
# Setup
python -m venv .venv
source .venv/bin/activate  # or .venv\\Scripts\\activate on Windows
pip install -r requirements.txt
```

## TODO

- [ ] Initial setup
- [ ] Add core functionality
"""
    (project_path / 'CLAUDE.md').write_text(content)


# ============ CRUD Operations ============

def cmd_create(args, config):
    """Create a new project."""
    name = args[0] if args else prompt("Project name (e.g., my-app, data-pipeline)")
    if not name:
        print("Project name required.")
        return

    name = name.lower().replace(' ', '-').replace('_', '-')
    project_path = Path(config['project_folder']) / name

    if project_path.exists():
        print(f"Project '{name}' already exists at {project_path}")
        return

    # Template selection
    print(f"\nTemplates: {', '.join(TEMPLATES.keys())}")
    template_name = prompt("Template", "python")

    if template_name not in TEMPLATES:
        print(f"Template '{template_name}' not found.")
        return

    template = TEMPLATES[template_name]

    # Create project folder
    project_path.mkdir(parents=True, exist_ok=True)
    print(f"\nCreated: {project_path}")

    # Create template files
    for file_path, content in template.get('files', {}).items():
        file_path = file_path.replace('{name}', name)
        content = content.replace('{name}', name)
        full_path = project_path / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

    # Create .gitignore
    (project_path / '.gitignore').write_text(template.get('gitignore', '.env\n'))

    # Create CLAUDE.md
    create_claude_md(project_path, name)

    # Initialize git
    try:
        subprocess.run(['git', 'init'], cwd=project_path, capture_output=True)
        subprocess.run(['git', 'add', '.'], cwd=project_path, capture_output=True)
        subprocess.run(['git', 'commit', '-m', f'Initial commit for {name}'], cwd=project_path, capture_output=True)
        print("  Initialized git repo")
    except Exception as e:
        print(f"  Git init failed: {e}")

    # Create GitHub repo
    if config.get('github_org') and prompt_yes_no("Create GitHub repo?"):
        try:
            repo_name = f"{config['github_org']}/{name}"
            subprocess.run([
                'gh', 'repo', 'create', repo_name,
                '--private', '--source', '.', '--push'
            ], cwd=project_path)
            print(f"  Created GitHub repo: {repo_name}")
        except Exception as e:
            print(f"  GitHub creation failed: {e}")

    # Create wiki page
    if config.get('wiki_space') and prompt_yes_no("Create wiki page?"):
        create_wiki_page(name, project_path, config['wiki_space'])

    print(f"\nProject '{name}' created!")
    print(f"  cd {project_path}")


def cmd_list(args, config):
    """List all projects."""
    projects = list_projects(config['project_folder'])

    if not projects:
        print(f"No projects found in {config['project_folder']}")
        return

    print(f"\nProjects in {config['project_folder']}:\n")

    for p in sorted(projects, key=lambda x: x['name']):
        status = []
        if p.get('has_git'):
            status.append("git")
        if p.get('has_claude_md'):
            status.append("claude")

        status_str = f" ({', '.join(status)})" if status else ""
        print(f"  {p['name']}{status_str}")

    print(f"\nTotal: {len(projects)} projects")


def cmd_info(args, config):
    """Show project details."""
    if not args:
        print("Usage: python main.py info <project-name>")
        return

    name = args[0]
    project_path = Path(config['project_folder']) / name

    if not project_path.exists():
        print(f"Project '{name}' not found.")
        return

    print(f"\n=== {name} ===\n")
    print(f"Path: {project_path}")

    # Check components
    print("\nComponents:")
    for item in ['CLAUDE.md', '.gitignore', '.git', 'requirements.txt', 'package.json']:
        path = project_path / item
        status = "OK" if path.exists() else "--"
        print(f"  [{status}] {item}")

    # Check git status
    if (project_path / '.git').exists():
        try:
            result = subprocess.run(
                ['git', 'remote', '-v'],
                cwd=project_path, capture_output=True, text=True
            )
            if result.stdout:
                print(f"\nRemote: {result.stdout.split()[1]}")
        except Exception:
            pass


def cmd_delete(args, config):
    """Delete a project."""
    if not args:
        print("Usage: python main.py delete <project-name>")
        return

    name = args[0]
    project_path = Path(config['project_folder']) / name

    if not project_path.exists():
        print(f"Project '{name}' not found.")
        return

    # Confirm deletion
    print(f"\nWARNING: This will permanently delete {project_path}")
    confirm = input(f"Type '{name}' to confirm: ").strip()

    if confirm != name:
        print("Deletion cancelled.")
        return

    shutil.rmtree(project_path)
    print(f"Project '{name}' deleted.")


def cmd_sync(args, config):
    """Sync project to git and wiki."""
    if not args:
        print("Usage: python main.py sync <project-name>")
        return

    name = args[0]
    project_path = Path(config['project_folder']) / name

    if not project_path.exists():
        print(f"Project '{name}' not found.")
        return

    print(f"\nSyncing {name}...")

    # Git sync
    if (project_path / '.git').exists():
        try:
            subprocess.run(['git', 'add', '.'], cwd=project_path)
            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=project_path, capture_output=True, text=True
            )

            if result.stdout.strip():
                subprocess.run(['git', 'commit', '-m', 'Update'], cwd=project_path)
                subprocess.run(['git', 'push'], cwd=project_path)
                print("  Pushed to git.")
            else:
                print("  No changes to commit.")
        except Exception as e:
            print(f"  Git sync failed: {e}")

    # Wiki sync
    if config.get('wiki_space'):
        print("  Wiki sync: TODO")


def cmd_config(args, config):
    """Configure settings."""
    print("Project Manager Configuration\n")

    # Project folder
    detected = detect_project_folder()
    current = config.get('project_folder') or str(detected)
    print("Where do you keep your projects?")
    config['project_folder'] = prompt("Projects folder", current)

    # Validate/create folder
    folder = Path(config['project_folder'])
    if not folder.exists():
        if prompt_yes_no(f"Create '{folder}'?"):
            folder.mkdir(parents=True, exist_ok=True)

    # Wiki space
    print("\nConfluence wiki space (optional)")
    config['wiki_space'] = prompt("Wiki space", config.get('wiki_space', ''))

    # GitHub org
    print("\nGitHub org/username (optional)")
    config['github_org'] = prompt("GitHub org", config.get('github_org', ''))

    save_config(config)
    print(f"\nConfig saved to: {CONFIG_FILE}")


def create_wiki_page(name, project_path, wiki_space):
    """Create Confluence wiki page for project."""
    print("Creating wiki page...")
    try:
        skill_dir = Path(__file__).parent.parent / 'wiki-api'
        if skill_dir.exists():
            sys.path.insert(0, str(skill_dir))
            from executor import execute, load_operations
            load_operations()

            content = f"<h1>{name.replace('-', ' ').title()}</h1><p>Created: {datetime.now().strftime('%Y-%m-%d')}</p>"
            result = execute('create', {
                'space_key': wiki_space,
                'title': name.replace('-', ' ').title(),
                'content': content
            })

            if 'error' not in result:
                print(f"  Created wiki page: {result.get('id', '')}")
                return

        print("  Wiki skill not available")
    except Exception as e:
        print(f"  Wiki creation failed: {e}")


# ============ Main ============

COMMANDS = {
    'create': cmd_create,
    'new': cmd_create,
    'list': cmd_list,
    'ls': cmd_list,
    'info': cmd_info,
    'show': cmd_info,
    'delete': cmd_delete,
    'rm': cmd_delete,
    'sync': cmd_sync,
    'push': cmd_sync,
    'config': cmd_config,
    'setup': cmd_config,
}


def print_help():
    """Print help message."""
    print(__doc__)
    print("Commands:")
    print("  create [name]    Create new project")
    print("  list             List all projects")
    print("  info <name>      Show project details")
    print("  delete <name>    Delete project")
    print("  sync <name>      Sync to git/wiki")
    print("  config           Configure settings")


def main():
    # Load config
    config = load_config()

    # Auto-setup if no project folder
    if not config.get('project_folder'):
        config['project_folder'] = str(detect_project_folder())

    args = sys.argv[1:]

    if not args or args[0] in ('-h', '--help', 'help'):
        print_help()
        return

    cmd = args[0].lower()
    cmd_args = args[1:]

    if cmd in COMMANDS:
        COMMANDS[cmd](cmd_args, config)
    else:
        print(f"Unknown command: {cmd}")
        print("Run 'python main.py help' for usage.")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
