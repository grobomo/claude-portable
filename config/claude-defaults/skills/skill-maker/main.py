#!/usr/bin/env python3
"""
Skill Manager - CRUD operations for Claude Code skills

Cross-platform (Windows, Mac, Linux). No hardcoded paths.

Usage:
    python main.py create [name]     # Create new skill
    python main.py list              # List all skills
    python main.py update <name>     # Update skill (re-sync APIs, etc)
    python main.py delete <name>     # Delete skill
    python main.py sync [name]       # Sync to git/wiki (all or specific)
    python main.py info <name>       # Show skill details
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

# Detect paths relative to this script
SKILL_DIR = Path(__file__).parent
PROJECT_ROOT = SKILL_DIR.parent.parent.parent
SKILLS_DIR = PROJECT_ROOT / '.claude' / 'skills'
TEMPLATES_DIR = SKILLS_DIR / 'templates'


def load_config():
    """Load user config."""
    config = {'wiki_space': '', 'github_org': ''}
    if CONFIG_FILE.exists():
        try:
            import yaml
            data = yaml.safe_load(CONFIG_FILE.read_text())
            if data:
                config.update(data)
        except Exception:
            pass
    return config


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


def get_templates():
    """List available templates."""
    templates = {}
    if TEMPLATES_DIR.exists():
        for folder in TEMPLATES_DIR.iterdir():
            if folder.is_dir() and not folder.name.startswith('_'):
                templates[folder.name.replace('-skill', '')] = folder
    return templates


def list_skills():
    """List all skills in the project."""
    skills = []
    excluded = {'templates', 'skill', 'project', '.git'}

    for folder in SKILLS_DIR.iterdir():
        if folder.is_dir() and folder.name not in excluded and not folder.name.startswith('.'):
            skill_info = {
                'name': folder.name,
                'path': folder,
                'has_env': (folder / '.env').exists(),
                'has_api_index': (folder / 'api_index').exists(),
            }

            # Count operations if API skill
            if skill_info['has_api_index']:
                api_index = folder / 'api_index'
                skill_info['operations'] = len([
                    f for f in api_index.iterdir()
                    if f.is_dir() and not f.name.startswith('_')
                ])

            skills.append(skill_info)

    return skills


def research_api_patterns(api_name):
    """Use Claude to research API key patterns."""
    print(f"\nResearching credential patterns for {api_name}...")

    prompt_text = f"""Research the {api_name} API authentication.

Output ONLY a YAML block:

```yaml
credential_patterns:
  api_key:
    - {api_name.upper()}_API_KEY
    - {api_name.upper()}_TOKEN
  username:
    - {api_name.upper()}_USERNAME
  base_url:
    - {api_name.upper()}_URL
documentation_url: "https://..."
```
"""

    try:
        result = subprocess.run(
            ['claude', '-p', prompt_text],
            capture_output=True, text=True, timeout=60
        )

        if result.returncode == 0 and '```yaml' in result.stdout:
            import yaml
            yaml_content = result.stdout.split('```yaml')[1].split('```')[0]
            return yaml.safe_load(yaml_content)
    except Exception as e:
        print(f"  Research failed: {e}")

    return {'credential_patterns': {'api_key': [f'{api_name.upper()}_API_KEY']}}


def scan_for_credentials(patterns):
    """Scan for existing credentials matching patterns."""
    found = []
    scan_paths = [PROJECT_ROOT.parent / 'mcp', SKILLS_DIR]

    pattern_map = {}
    for key, names in patterns.get('credential_patterns', {}).items():
        for name in names:
            pattern_map[name] = key

    for base_path in scan_paths:
        if not base_path.exists():
            continue

        for env_file in base_path.rglob('.env'):
            creds = {}
            source = env_file.parent.name

            try:
                for line in env_file.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"\'')
                        if key in pattern_map and value:
                            creds[pattern_map[key]] = value
            except Exception:
                continue

            if creds.get('api_key'):
                if 'mcp' in str(env_file):
                    source = f"mcp/{source}"
                found.append({'source': source, 'path': env_file, **creds})

    # Dedupe
    seen = set()
    unique = []
    for f in found:
        key = f.get('api_key', '')[:12]
        if key and key not in seen:
            seen.add(key)
            unique.append(f)

    return unique


def select_credentials(found_creds):
    """Prompt user to select credentials."""
    if not found_creds:
        return None

    print("\nFound existing credentials:")
    for i, cred in enumerate(found_creds, 1):
        key = cred.get('api_key', '')
        masked = key[:8] + "..." if len(key) > 8 else "****"
        print(f"  {i}. {cred['source']} ({masked})")
    print(f"  n. Enter new credentials")

    while True:
        choice = input("\nSelect [1]: ").strip().lower()
        if choice == '' or choice == '1':
            return found_creds[0]
        elif choice == 'n':
            return None
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(found_creds):
                return found_creds[idx]


# ============ CRUD Operations ============

def cmd_create(args):
    """Create a new skill."""
    name = args[0] if args else prompt("Skill name (e.g., slack-api, github-notify)")
    if not name:
        print("Skill name required.")
        return

    name = name.lower().replace(' ', '-').replace('_', '-')
    skill_path = SKILLS_DIR / name

    if skill_path.exists():
        print(f"Skill '{name}' already exists.")
        return

    # Template selection
    templates = get_templates()
    print(f"\nTemplates: {', '.join(templates.keys())}")
    template_name = prompt("Template", "api")

    if template_name not in templates:
        print(f"Template '{template_name}' not found.")
        return

    # Copy template
    shutil.copytree(templates[template_name], skill_path)
    print(f"\nCreated: {skill_path}")

    # Create README.md
    readme_content = f"""# {name}

Claude Code skill for {name.replace('-', ' ')}.

## Installation

```bash
cd .claude/skills/{name}
python setup.py
```

## Usage

See SKILL.md for detailed usage instructions.

## License

Private - internal use only.
"""
    (skill_path / 'README.md').write_text(readme_content)
    print("  Created README.md")

    # For API skills, research and scan
    if 'api' in template_name:
        api_name = name.replace('-api', '').replace('-', ' ').title()

        if prompt_yes_no(f"Research API patterns for '{api_name}'?"):
            patterns = research_api_patterns(api_name)
            doc_url = patterns.get('documentation_url', '')

            if doc_url:
                ref_dir = skill_path / 'reference'
                ref_dir.mkdir(exist_ok=True)
                (ref_dir / 'DOCS.md').write_text(f"# Documentation\n\n{doc_url}\n")
                print(f"  Saved doc URL: {doc_url}")

            if prompt_yes_no("Scan for existing credentials?"):
                found = scan_for_credentials(patterns)
                if found:
                    if prompt_yes_no(f"Found {len(found)} credential(s). Review?"):
                        selected = select_credentials(found)
                        if selected and prompt_yes_no(f"Use credentials from '{selected['source']}'?"):
                            env_content = f"# Imported from {selected['source']}\n"
                            for k, v in selected.items():
                                if k not in ('source', 'path'):
                                    env_content += f"{k.upper()}={v}\n"
                            (skill_path / '.env').write_text(env_content)
                            print("  Credentials imported.")

    # Create git repo for the skill
    config = load_config()
    github_org = config.get('github_org', '${TMEMU_ACCOUNT}')

    if prompt_yes_no("Create git repository?"):
        print("\nInitializing git repo...")
        subprocess.run(['git', 'init'], cwd=skill_path, capture_output=True)
        subprocess.run(['git', 'add', '.'], cwd=skill_path, capture_output=True)
        subprocess.run(['git', 'commit', '--no-verify', '-m', f'Initial commit: {name}'],
                      cwd=skill_path, capture_output=True)

        if prompt_yes_no("Create GitHub repository?"):
            repo_name = f"skill-{name}" if not name.startswith('skill-') else name
            desc = f"Claude Code skill: {name}"
            result = subprocess.run(
                ['gh', 'repo', 'create', f'{github_org}/{repo_name}',
                 '--private', '--source=.', '--push', f'--description={desc}'],
                cwd=skill_path, capture_output=True, text=True
            )
            if result.returncode == 0:
                print(f"  Created: https://github.com/{github_org}/{repo_name}")

                # Add as submodule to claude-skills meta-repo
                if prompt_yes_no("Add to claude-skills meta-repo?"):
                    subprocess.run(
                        ['git', 'submodule', 'add',
                         f'https://github.com/{github_org}/{repo_name}.git', name],
                        cwd=SKILLS_DIR, capture_output=True
                    )
                    subprocess.run(['git', 'add', '.'], cwd=SKILLS_DIR, capture_output=True)
                    subprocess.run(
                        ['git', 'commit', '--no-verify', '-m', f'Add {name} skill submodule'],
                        cwd=SKILLS_DIR, capture_output=True
                    )
                    subprocess.run(['git', 'push'], cwd=SKILLS_DIR, capture_output=True)
                    print("  Added to meta-repo.")
            else:
                print(f"  GitHub creation failed: {result.stderr}")

    print(f"\nSkill '{name}' created!")
    print(f"  cd {skill_path}")
    print("  python setup.py")


def cmd_list(args):
    """List all skills."""
    skills = list_skills()

    if not skills:
        print("No skills found.")
        return

    print(f"\nSkills in {SKILLS_DIR}:\n")

    for s in sorted(skills, key=lambda x: x['name']):
        status = []
        if s.get('has_env'):
            status.append("configured")
        if s.get('operations'):
            status.append(f"{s['operations']} ops")

        status_str = f" ({', '.join(status)})" if status else ""
        print(f"  {s['name']}{status_str}")

    print(f"\nTotal: {len(skills)} skills")


def cmd_info(args):
    """Show skill details."""
    if not args:
        print("Usage: python main.py info <skill-name>")
        return

    name = args[0]
    skill_path = SKILLS_DIR / name

    if not skill_path.exists():
        print(f"Skill '{name}' not found.")
        return

    print(f"\n=== {name} ===\n")
    print(f"Path: {skill_path}")

    # Check components
    print("\nComponents:")
    for item in ['setup.py', 'executor.py', '.env', 'api_index', 'SKILL.md', 'reference']:
        path = skill_path / item
        status = "OK" if path.exists() else "--"
        print(f"  [{status}] {item}")

    # Count operations
    api_index = skill_path / 'api_index'
    if api_index.exists():
        ops = [f for f in api_index.iterdir() if f.is_dir() and not f.name.startswith('_')]
        print(f"\nOperations: {len(ops)}")

    # Show doc URL if exists
    docs_file = skill_path / 'reference' / 'DOCS.md'
    if docs_file.exists():
        content = docs_file.read_text()
        if 'http' in content:
            url = 'http' + content.split('http')[1].split()[0].split('\n')[0]
            print(f"\nDocs: {url}")


def cmd_update(args):
    """Update a skill (refresh APIs, re-sync, etc)."""
    if not args:
        print("Usage: python main.py update <skill-name>")
        return

    name = args[0]
    skill_path = SKILLS_DIR / name

    if not skill_path.exists():
        print(f"Skill '{name}' not found.")
        return

    print(f"\nUpdating {name}...")

    # Check for refresh script (API skills)
    refresh_script = skill_path / 'refresh_api.py'
    if refresh_script.exists():
        if prompt_yes_no("Refresh API spec?"):
            subprocess.run(['python', str(refresh_script), '--apply'], cwd=skill_path)

    # Check for analyze script
    analyze_script = skill_path / 'analyze_userstories.py'
    if analyze_script.exists():
        if prompt_yes_no("Re-analyze user stories?"):
            subprocess.run(['python', str(analyze_script)], cwd=skill_path)

    # Sync to git
    if prompt_yes_no("Commit changes to git?"):
        cmd_sync([name])

    print(f"\nSkill '{name}' updated!")


def cmd_delete(args):
    """Delete a skill."""
    if not args:
        print("Usage: python main.py delete <skill-name>")
        return

    name = args[0]
    skill_path = SKILLS_DIR / name

    if not skill_path.exists():
        print(f"Skill '{name}' not found.")
        return

    # Confirm deletion
    print(f"\nWARNING: This will delete {skill_path}")
    confirm = input(f"Type '{name}' to confirm: ").strip()

    if confirm != name:
        print("Deletion cancelled.")
        return

    # Remove from git first
    try:
        subprocess.run(['git', 'rm', '-rf', str(skill_path)], cwd=PROJECT_ROOT, capture_output=True)
        subprocess.run(['git', 'commit', '-m', f'Remove {name} skill'], cwd=PROJECT_ROOT, capture_output=True)
        subprocess.run(['git', 'push'], cwd=PROJECT_ROOT, capture_output=True)
        print(f"Removed from git.")
    except Exception:
        # Fallback to manual delete
        shutil.rmtree(skill_path)

    print(f"Skill '{name}' deleted.")


def cmd_sync(args):
    """Sync skills to git and wiki."""
    config = load_config()

    if args:
        # Sync specific skill
        name = args[0]
        skill_path = SKILLS_DIR / name
        if not skill_path.exists():
            print(f"Skill '{name}' not found.")
            return
        paths_to_sync = [skill_path]
        msg = f"Update {name} skill"
    else:
        # Sync all modified skills
        paths_to_sync = [SKILLS_DIR]
        msg = "Update skills"

    print("\nSyncing to git...")

    try:
        for path in paths_to_sync:
            subprocess.run(['git', 'add', str(path)], cwd=PROJECT_ROOT)

        # Check if there are changes
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=PROJECT_ROOT, capture_output=True, text=True
        )

        if not result.stdout.strip():
            print("  No changes to commit.")
            return

        # Commit and push
        subprocess.run(['git', 'commit', '-m', msg], cwd=PROJECT_ROOT)
        subprocess.run(['git', 'push'], cwd=PROJECT_ROOT)
        print("  Pushed to git.")

    except Exception as e:
        print(f"  Git sync failed: {e}")

    # Wiki sync (if configured and wiki-api skill exists)
    if config.get('wiki_space'):
        wiki_skill = SKILLS_DIR / 'wiki-api'
        if wiki_skill.exists():
            print("\nSyncing to wiki...")
            try:
                sys.path.insert(0, str(wiki_skill))
                from executor import execute, load_operations
                load_operations()

                # Update project wiki page with skills list
                skills = list_skills()
                content = "<h2>Skills</h2><ul>"
                for s in skills:
                    ops = f" ({s['operations']} ops)" if s.get('operations') else ""
                    content += f"<li><strong>{s['name']}</strong>{ops}</li>"
                content += "</ul>"

                # Search for existing page or create new
                # TODO: Implement wiki update
                print("  Wiki sync: TODO")

            except Exception as e:
                print(f"  Wiki sync failed: {e}")


# ============ Main ============

COMMANDS = {
    'create': cmd_create,
    'new': cmd_create,
    'list': cmd_list,
    'ls': cmd_list,
    'info': cmd_info,
    'show': cmd_info,
    'update': cmd_update,
    'refresh': cmd_update,
    'delete': cmd_delete,
    'rm': cmd_delete,
    'remove': cmd_delete,
    'sync': cmd_sync,
    'push': cmd_sync,
}


def print_help():
    """Print help message."""
    print(__doc__)
    print("Commands:")
    print("  create [name]    Create new skill")
    print("  list             List all skills")
    print("  info <name>      Show skill details")
    print("  update <name>    Update skill (refresh APIs)")
    print("  delete <name>    Delete skill")
    print("  sync [name]      Sync to git/wiki")


def main():
    args = sys.argv[1:]

    if not args or args[0] in ('-h', '--help', 'help'):
        print_help()
        return

    cmd = args[0].lower()
    cmd_args = args[1:]

    if cmd in COMMANDS:
        COMMANDS[cmd](cmd_args)
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
