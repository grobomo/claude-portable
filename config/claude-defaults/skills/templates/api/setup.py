#!/usr/bin/env python3
"""
API Skill Setup Template

Configures API credentials. Run this once to set up access.
Scans existing MCP servers and skills for reusable credentials.

Usage:
    python setup.py
"""

import os
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent
ENV_FILE = SKILL_DIR / '.env'

# Update for your API
SKILL_NAME = "My API"
BASE_URL = "https://api.example.com"

# Credential patterns to search for (key_pattern -> normalized_key)
# Update these patterns for your API
CREDENTIAL_PATTERNS = {
    'API_KEY': 'api_key',
    'API_TOKEN': 'api_key',
    'AUTH_TOKEN': 'api_key',
    'ACCESS_TOKEN': 'api_key',
    'API_BASE_URL': 'base_url',
    'BASE_URL': 'base_url',
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
    """Scan MCP servers and skills for existing credentials."""
    found = []

    # Scan locations
    scan_paths = [
        # MCP servers (relative to project)
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

            # Need at least an API key
            if creds.get('api_key'):
                # Determine source name
                source = env_file.parent.name
                if 'mcp' in str(env_file):
                    source = f"mcp/{source}"
                elif 'skills' in str(env_file):
                    source = f"skill/{source}"

                found.append({
                    'source': source,
                    'path': env_file,
                    'api_key': creds.get('api_key'),
                    'base_url': creds.get('base_url', BASE_URL),
                })

    # Dedupe by api_key prefix
    seen = set()
    unique = []
    for f in found:
        key = f['api_key'][:12]
        if key not in seen:
            seen.add(key)
            unique.append(f)

    return unique


def prompt_credential_source(found_creds):
    """Prompt user to select from found credentials or enter new."""
    if not found_creds:
        return None

    print("Found existing credentials:")
    print()

    for i, cred in enumerate(found_creds, 1):
        masked = cred['api_key'][:8] + "..." if len(cred['api_key']) > 8 else "****"
        print(f"  {i}. {cred['source']}")
        print(f"     Key: {masked}")
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
    print(f"  {SKILL_NAME} Skill Setup")
    print("=" * 60)
    print()


def get_existing_config():
    """Load existing config if present."""
    config = {'API_KEY': '', 'API_BASE_URL': BASE_URL}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip().strip('"\'')
    return config


def prompt_api_key(current):
    """Prompt user to enter API key."""
    print()
    print("Enter your API key/token.")
    print()
    print("To get an API key:")
    print("  1. Go to your API settings")
    print("  2. Create a new API key/token")
    print("  3. Copy the generated token")
    print()

    if current:
        masked = current[:10] + "..." + current[-5:] if len(current) > 20 else current
        print(f"Current key: {masked}")
        print()

    while True:
        key = input("API Key (or press Enter to keep current): ").strip()
        if not key:
            if current:
                return current
            print("API key is required.")
            continue
        return key


def prompt_base_url(current):
    """Prompt user for base URL."""
    print()
    print(f"Base URL (default: {BASE_URL})")
    print()

    url = input(f"Base URL [{current}]: ").strip()
    return url if url else current


def test_connection(api_key, base_url):
    """Test API connection."""
    print()
    print("Testing API connection...")

    try:
        import requests
    except ImportError:
        print("Warning: 'requests' not installed. Skipping connection test.")
        print("Run: pip install requests")
        return None

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

    # Update with a simple test endpoint
    try:
        r = requests.get(
            f"{base_url}/health",  # or another simple endpoint
            headers=headers,
            timeout=15
        )

        if r.status_code == 200:
            print("  [OK] Connection successful!")
            return True
        elif r.status_code == 401:
            print("  [FAIL] Unauthorized - check your API key")
            return False
        elif r.status_code == 403:
            print("  [WARN] Connected but got 403 - key may have limited permissions")
            return True
        else:
            print(f"  [FAIL] HTTP {r.status_code}: {r.text[:100]}")
            return False
    except requests.exceptions.Timeout:
        print("  [FAIL] Connection timeout - check your network")
        return False
    except Exception as e:
        print(f"  [FAIL] {e}")
        return False


def save_config(api_key, base_url):
    """Save configuration to .env file."""
    content = f"""# {SKILL_NAME} Configuration
# Generated by setup.py

API_KEY={api_key}
API_BASE_URL={base_url}
"""
    ENV_FILE.write_text(content)
    print()
    print(f"Configuration saved to: {ENV_FILE}")


def main():
    print_header()

    # Load existing config
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
        selected = prompt_credential_source(found_creds)

        if selected:
            # Use selected credentials
            api_key = selected['api_key']
            base_url = selected['base_url']
            print(f"\nUsing credentials from: {selected['source']}")
        else:
            # Enter new credentials
            print()
            api_key = prompt_api_key(config['API_KEY'])
            base_url = prompt_base_url(config['API_BASE_URL'])
    else:
        print("No existing credentials found.\n")
        api_key = prompt_api_key(config['API_KEY'])
        base_url = prompt_base_url(config['API_BASE_URL'])

    # Test connection
    test_result = test_connection(api_key, base_url)

    if test_result is False:
        print()
        save_anyway = input("Connection failed. Save configuration anyway? [y/N]: ").strip().lower()
        if save_anyway != 'y':
            print("Setup cancelled.")
            return

    # Save config
    save_config(api_key, base_url)

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
