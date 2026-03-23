#!/usr/bin/env python3
"""
Write .env for claude-portable by pulling credentials from OS credential store.
Falls back to reading Claude's local credential files if not in keyring.

Usage:
    python scripts/write-env.py              # auto-detect auth method
    python scripts/write-env.py --api-key    # force API key mode
    python scripts/write-env.py --oauth      # force OAuth mode
"""
import json
import os
import subprocess
import sys
from pathlib import Path

KEYRING_SERVICE = "claude-code"

def get_from_keyring(key):
    """Try to get a credential from OS keyring."""
    try:
        import keyring
        val = keyring.get_password(KEYRING_SERVICE, key)
        return val
    except Exception:
        return None

def store_to_keyring(key, value):
    """Store a credential in OS keyring."""
    try:
        import keyring
        keyring.set_password(KEYRING_SERVICE, key, value)
        return True
    except Exception:
        return False

def find_claude_credentials():
    """Find Claude OAuth credentials file on this system."""
    candidates = [
        Path.home() / ".claude" / ".credentials.json",
    ]
    # Windows: check USERPROFILE and APPDATA
    if os.name == "nt":
        for base in [os.environ.get("USERPROFILE", ""), os.environ.get("APPDATA", "")]:
            if base:
                candidates.append(Path(base) / ".claude" / ".credentials.json")
                candidates.append(Path(base).parent / ".claude" / ".credentials.json")

    for p in candidates:
        if p.exists():
            try:
                data = json.loads(p.read_text())
                if "claudeAiOauth" in data:
                    return data["claudeAiOauth"], str(p)
            except Exception:
                continue
    return None, None

def get_gh_token():
    """Get GitHub token from gh CLI."""
    try:
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return get_from_keyring("github/TOKEN") or ""

def detect_auth():
    """Detect available auth method. Returns ('api_key', key) or ('oauth', creds) or (None, None)."""
    # 1. Check keyring for API key
    api_key = get_from_keyring("anthropic/API_KEY")
    if api_key:
        return "api_key", api_key

    # 2. Check env var
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key:
        return "api_key", api_key

    # 3. Check keyring for OAuth
    access = get_from_keyring("claude-portable/OAUTH_ACCESS_TOKEN")
    refresh = get_from_keyring("claude-portable/OAUTH_REFRESH_TOKEN")
    if access and refresh:
        return "oauth", {"accessToken": access, "refreshToken": refresh, "expiresAt": ""}

    # 4. Check local Claude credentials file
    creds, path = find_claude_credentials()
    if creds:
        # Store in keyring for next time
        store_to_keyring("claude-portable/OAUTH_ACCESS_TOKEN", creds["accessToken"])
        store_to_keyring("claude-portable/OAUTH_REFRESH_TOKEN", creds["refreshToken"])
        return "oauth", creds

    return None, None

def write_env(proj_dir):
    mode = None
    if "--api-key" in sys.argv:
        mode = "api_key"
    elif "--oauth" in sys.argv:
        mode = "oauth"

    if mode == "api_key":
        auth_type, auth_data = "api_key", get_from_keyring("anthropic/API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
        if not auth_data:
            print("ERROR: No API key found in keyring (anthropic/API_KEY) or ANTHROPIC_API_KEY env var.")
            print("Store it first: python ~/.claude/skills/credential-manager/store_gui.py anthropic/API_KEY")
            sys.exit(1)
    elif mode == "oauth":
        auth_type, auth_data = "oauth", None
        creds, _ = find_claude_credentials()
        if creds:
            auth_data = creds
        else:
            print("ERROR: No OAuth credentials found. Log into Claude Code first: claude")
            sys.exit(1)
    else:
        auth_type, auth_data = detect_auth()

    if auth_type is None:
        print("No auth credentials found. Options:")
        print("  1. Store an API key:  python ~/.claude/skills/credential-manager/store_gui.py anthropic/API_KEY")
        print("  2. Log into Claude Code locally:  claude")
        sys.exit(1)

    gh_token = get_gh_token()
    env_path = os.path.join(proj_dir, ".env")

    with open(env_path, "w") as f:
        if auth_type == "api_key":
            f.write(f"ANTHROPIC_API_KEY={auth_data}\n")
            print(f"Auth: API key (from {'keyring' if get_from_keyring('anthropic/API_KEY') else 'env var'})")
        else:
            f.write(f"CLAUDE_OAUTH_ACCESS_TOKEN={auth_data['accessToken']}\n")
            f.write(f"CLAUDE_OAUTH_REFRESH_TOKEN={auth_data['refreshToken']}\n")
            f.write(f"CLAUDE_OAUTH_EXPIRES_AT={auth_data.get('expiresAt', '')}\n")
            print(f"Auth: OAuth tokens (from local Claude credentials)")

        f.write(f"GITHUB_TOKEN={gh_token or 'none'}\n")
        f.write("REPO_URL=https://github.com/grobomo/claude-portable.git\n")

    print(f"Wrote {env_path}")
    # Protect the file
    try:
        os.chmod(env_path, 0o600)
    except Exception:
        pass

if __name__ == "__main__":
    proj_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    write_env(proj_dir)
