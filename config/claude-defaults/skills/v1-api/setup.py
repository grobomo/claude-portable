#!/usr/bin/env python3
"""
V1 API Skill Setup

Configures API credentials for the V1 API skill.
Run this once to set up your Vision One API access.

Usage:
    python setup.py
"""

import os
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent
ENV_FILE = SKILL_DIR / '.env'

REGIONS = {
    '1': ('us', 'United States (api.xdr.trendmicro.com)'),
    '2': ('eu', 'Europe (api.eu.xdr.trendmicro.com)'),
    '3': ('jp', 'Japan (api.xdr.trendmicro.co.jp)'),
    '4': ('sg', 'Singapore (api.sg.xdr.trendmicro.com)'),
    '5': ('au', 'Australia (api.au.xdr.trendmicro.com)'),
    '6': ('in', 'India (api.in.xdr.trendmicro.com)'),
    '7': ('ae', 'Middle East (api.mea.xdr.trendmicro.com)'),
}


def print_header():
    print()
    print("=" * 60)
    print("  Vision One API Skill Setup")
    print("=" * 60)
    print()


def get_existing_config():
    """Load existing config if present."""
    config = {'V1_API_KEY': '', 'V1_REGION': 'us'}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip().strip('"\'')
    return config


def prompt_region(current):
    """Prompt user to select region."""
    print("Select your Vision One region:")
    print()
    for key, (code, name) in REGIONS.items():
        marker = " (current)" if code == current else ""
        print(f"  {key}. {name}{marker}")
    print()

    while True:
        choice = input(f"Enter choice [1-7] (default: keep current): ").strip()
        if not choice:
            return current
        if choice in REGIONS:
            return REGIONS[choice][0]
        print("Invalid choice. Enter 1-7.")


def prompt_api_key(current):
    """Prompt user to enter API key."""
    print()
    print("Enter your Vision One API key.")
    print()
    print("To get an API key:")
    print("  1. Go to V1 Console > Administration > API Keys")
    print("  2. Click 'Add API Key'")
    print("  3. Set role with these permissions:")
    print("     - Workbench (View, Filter)")
    print("     - Attack Surface Risk Management (View)")
    print("     - Observed Attack Techniques (View)")
    print("     - Response Management (View)")
    print("  4. Copy the generated token")
    print()

    if current:
        masked = current[:20] + "..." + current[-10:] if len(current) > 40 else current
        print(f"Current key: {masked}")
        print()

    while True:
        key = input("API Key (paste full token, or press Enter to keep current): ").strip()
        if not key:
            if current:
                return current
            print("API key is required.")
            continue

        # Basic validation - V1 tokens are JWT format
        if not key.startswith('eyJ'):
            print("Warning: Token doesn't look like a V1 API key (should start with 'eyJ').")
            confirm = input("Use anyway? [y/N]: ").strip().lower()
            if confirm != 'y':
                continue

        if len(key) < 100:
            print("Warning: Token seems too short for a V1 API key.")
            confirm = input("Use anyway? [y/N]: ").strip().lower()
            if confirm != 'y':
                continue

        return key


def test_connection(api_key, region):
    """Test API connection."""
    print()
    print("Testing API connection...")

    try:
        import requests
    except ImportError:
        print("Warning: 'requests' not installed. Skipping connection test.")
        print("Run: pip install requests")
        return None

    region_urls = {
        'us': 'https://api.xdr.trendmicro.com',
        'eu': 'https://api.eu.xdr.trendmicro.com',
        'jp': 'https://api.xdr.trendmicro.co.jp',
        'sg': 'https://api.sg.xdr.trendmicro.com',
        'au': 'https://api.au.xdr.trendmicro.com',
        'in': 'https://api.in.xdr.trendmicro.com',
        'ae': 'https://api.mea.xdr.trendmicro.com',
    }

    base_url = region_urls.get(region, region_urls['us'])
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

    # Try a simple endpoint
    try:
        r = requests.get(
            f"{base_url}/v3.0/workbench/alerts",
            headers=headers,
            params={'top': '1'},
            timeout=15
        )

        if r.status_code == 200:
            print("  [OK] Connection successful!")
            return True
        elif r.status_code == 403:
            print("  [WARN] Connected but got 403 - key may have limited permissions")
            print("         Some APIs may not work. Consider creating a key with more permissions.")
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


def save_config(api_key, region):
    """Save configuration to .env file."""
    content = f"""# Vision One API Configuration
# Generated by setup.py

V1_API_KEY={api_key}
V1_REGION={region}
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

    # Get region
    region = prompt_region(config['V1_REGION'])

    # Get API key
    api_key = prompt_api_key(config['V1_API_KEY'])

    # Test connection
    test_result = test_connection(api_key, region)

    if test_result is False:
        print()
        save_anyway = input("Connection failed. Save configuration anyway? [y/N]: ").strip().lower()
        if save_anyway != 'y':
            print("Setup cancelled.")
            return

    # Save config
    save_config(api_key, region)

    print()
    print("Setup complete! Test with:")
    print("  python executor.py list_alerts days=7 limit=5")
    print()


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
