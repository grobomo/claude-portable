#!/usr/bin/env python3
"""
Wiki API Skill Setup

Configures Confluence API credentials.
Scans existing MCP servers and skills for reusable credentials.

Usage:
    python setup.py
"""

import os
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent
ENV_FILE = SKILL_DIR / '.env'

# Credential patterns to search for (key_pattern -> normalized_key)
CREDENTIAL_PATTERNS = {
    'CONFLUENCE_URL': 'url',
    'ATLASSIAN_URL': 'url',
    'WIKI_URL': 'url',
    'CONFLUENCE_USERNAME': 'username',
    'ATLASSIAN_USERNAME': 'username',
    'ATLASSIAN_EMAIL': 'username',
    'WIKI_USERNAME': 'username',
    'CONFLUENCE_API_TOKEN': 'token',
    'ATLASSIAN_API_TOKEN': 'token',
    'CONFLUENCE_TOKEN': 'token',
    'WIKI_TOKEN': 'token',
}


def scan_env_file(env_path):
    """Parse .env file and extract matching credentials."""
    creds = {}
    try:
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"\'')
                if key in CREDENTIAL_PATTERNS and value:
                    normalized = CREDENTIAL_PATTERNS[key]
                    creds[normalized] = value
    except Exception:
        pass
    return creds


def scan_for_credentials():
    """Scan MCP servers and skills for existing Confluence credentials."""
    found = []

    # Scan locations
    scan_paths = [
        # MCP servers (relative to lab-worker)
        SKILL_DIR.parent.parent.parent / 'mcp',
        SKILL_DIR.parent.parent.parent.parent / 'mcp',
        # Other skills
        SKILL_DIR.parent,
    ]

    for base_path in scan_paths:
        if not base_path.exists():
            continue

        # Find all .env files
        for env_file in base_path.rglob('.env'):
            # Skip our own .env
            if env_file == ENV_FILE:
                continue

            creds = scan_env_file(env_file)

            # Need at least username and token
            if creds.get('username') and creds.get('token'):
                # Determine source name
                source = env_file.parent.name
                if 'mcp' in str(env_file):
                    source = f"mcp/{source}"
                elif 'skills' in str(env_file):
                    source = f"skill/{source}"

                found.append({
                    'source': source,
                    'path': env_file,
                    'url': creds.get('url', 'https://trendmicro.atlassian.net/wiki'),
                    'username': creds.get('username'),
                    'token': creds.get('token'),
                })

    # Dedupe by username+token
    seen = set()
    unique = []
    for f in found:
        key = (f['username'], f['token'][:8])
        if key not in seen:
            seen.add(key)
            unique.append(f)

    return unique


def prompt_credential_source(found_creds, current_config):
    """Prompt user to select from found credentials or enter new."""
    if not found_creds:
        return None

    print("Found existing credentials:")
    print()

    for i, cred in enumerate(found_creds, 1):
        masked_token = cred['token'][:8] + "..." if len(cred['token']) > 8 else "****"
        print(f"  {i}. {cred['source']}")
        print(f"     User: {cred['username']}")
        print(f"     Token: {masked_token}")
        print()

    print(f"  n. Enter new credentials")
    print()

    while True:
        choice = input("Select [1]: ").strip().lower()

        if choice == '' or choice == '1':
            return found_creds[0]
        elif choice == 'n':
            return None
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(found_creds):
                return found_creds[idx]

        print(f"Invalid choice. Enter 1-{len(found_creds)} or 'n'")


def print_header():
    print()
    print("=" * 60)
    print("  Confluence Wiki API Skill Setup")
    print("=" * 60)
    print()


def get_existing_config():
    """Load existing config if present."""
    config = {
        'CONFLUENCE_URL': 'https://trendmicro.atlassian.net/wiki',
        'CONFLUENCE_USERNAME': '',
        'CONFLUENCE_API_TOKEN': ''
    }
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip().strip('"\'')
    return config


def prompt_url(current):
    """Prompt for Confluence URL."""
    print("Confluence URL (e.g., https://your-domain.atlassian.net/wiki)")
    print()

    url = input(f"URL [{current}]: ").strip()
    return url.rstrip('/') if url else current


def prompt_username(current):
    """Prompt for username."""
    print()
    print("Confluence username (your email address)")
    print()

    if current:
        print(f"Current: {current}")

    while True:
        username = input("Username (email): ").strip()
        if not username:
            if current:
                return current
            print("Username is required.")
            continue
        return username


def prompt_api_token(current):
    """Prompt for API token."""
    print()
    print("Confluence API token")
    print()
    print("To get a token:")
    print("  1. Go to https://id.atlassian.com/manage/api-tokens")
    print("  2. Click 'Create API token'")
    print("  3. Give it a name and copy the token")
    print()

    if current:
        masked = current[:8] + "..." + current[-4:] if len(current) > 15 else "****"
        print(f"Current token: {masked}")
        print()

    while True:
        token = input("API Token (or Enter to keep current): ").strip()
        if not token:
            if current:
                return current
            print("API token is required.")
            continue
        return token


def test_connection(url, username, token):
    """Test Confluence API connection."""
    print()
    print("Testing API connection...")

    try:
        import requests
        import base64
    except ImportError:
        print("Warning: 'requests' not installed. Skipping connection test.")
        return None

    auth = base64.b64encode(f"{username}:{token}".encode()).decode()
    headers = {
        'Authorization': f'Basic {auth}',
        'Accept': 'application/json'
    }

    try:
        r = requests.get(
            f"{url}/rest/api/space",
            headers=headers,
            params={'limit': '1'},
            timeout=15
        )

        if r.status_code == 200:
            data = r.json()
            spaces = len(data.get('results', []))
            print(f"  [OK] Connection successful! Found {spaces} space(s)")
            return True
        elif r.status_code == 401:
            print("  [FAIL] Unauthorized - check your credentials")
            return False
        elif r.status_code == 403:
            print("  [WARN] Connected but got 403 - token may have limited permissions")
            return True
        else:
            print(f"  [FAIL] HTTP {r.status_code}: {r.text[:100]}")
            return False
    except requests.exceptions.Timeout:
        print("  [FAIL] Connection timeout")
        return False
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def save_config(url, username, token):
    """Save configuration to .env file."""
    content = f"""# Confluence Wiki API Configuration
# Generated by setup.py

CONFLUENCE_URL={url}
CONFLUENCE_USERNAME={username}
CONFLUENCE_API_TOKEN={token}
"""
    ENV_FILE.write_text(content)
    print()
    print(f"Configuration saved to: {ENV_FILE}")


def main():
    print_header()

    config = get_existing_config()

    if ENV_FILE.exists():
        print("Existing configuration found.")
        update = input("Update configuration? [y/N]: ").strip().lower()
        if update != 'y':
            print("Setup cancelled.")
            return
        print()

    # Scan for existing credentials
    print("Scanning for existing credentials...")
    found_creds = scan_for_credentials()

    if found_creds:
        print(f"Found {len(found_creds)} credential source(s).\n")
        selected = prompt_credential_source(found_creds, config)

        if selected:
            # Use selected credentials
            url = selected['url']
            username = selected['username']
            token = selected['token']
            print(f"\nUsing credentials from: {selected['source']}")
        else:
            # Enter new credentials
            print()
            url = prompt_url(config['CONFLUENCE_URL'])
            username = prompt_username(config['CONFLUENCE_USERNAME'])
            token = prompt_api_token(config['CONFLUENCE_API_TOKEN'])
    else:
        print("No existing credentials found.\n")
        # Get config manually
        url = prompt_url(config['CONFLUENCE_URL'])
        username = prompt_username(config['CONFLUENCE_USERNAME'])
        token = prompt_api_token(config['CONFLUENCE_API_TOKEN'])

    # Test connection
    test_result = test_connection(url, username, token)

    if test_result is False:
        print()
        save_anyway = input("Connection failed. Save configuration anyway? [y/N]: ").strip().lower()
        if save_anyway != 'y':
            print("Setup cancelled.")
            return

    # Save
    save_config(url, username, token)

    # Check if this is a new setup (no api_index populated)
    api_index = SKILL_DIR / "api_index"
    op_count = len([f for f in api_index.iterdir() if f.is_dir() and not f.name.startswith("_")]) if api_index.exists() else 0

    if op_count < 10:
        # New setup - run refresh + apply + analyze
        print()
        print("-" * 60)
        print("Initializing API operations...")
        print()

        run_init = input("Fetch latest API spec and generate suggestions? [Y/n]: ").strip().lower()
        if run_init != 'n':
            import subprocess
            refresh_script = SKILL_DIR / "refresh_api.py"
            if refresh_script.exists():
                subprocess.run(["python", str(refresh_script), "--apply"])
            print()
            print("Initialization complete!")

    print()
    print("Setup complete! Test with:")
    print("  python executor.py --list")
    print("  python executor.py search query=\"test\"")
    print()
    print("See SUGGESTED_CALLS.md for common use cases.")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nSetup cancelled.")
    except Exception as e:
        print(f"\nError: {e}")
    finally:
        print()
        input("Press Enter to exit...")
