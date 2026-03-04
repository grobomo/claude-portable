#!/bin/bash
# Fetch secrets from Bitwarden Secrets Manager and write to config files.
# Requires: BWS_ACCESS_TOKEN env var set.
set -euo pipefail

if [ -z "${BWS_ACCESS_TOKEN:-}" ]; then
  echo "  BWS_ACCESS_TOKEN not set, skipping."
  exit 0
fi

# Fetch all secrets as JSON
SECRETS=$(bws secret list 2>/dev/null || echo "[]")
if [ "$SECRETS" = "[]" ]; then
  echo "  No secrets found in BWS (or auth failed)."
  exit 0
fi

# Helper: get secret value by key name
get_secret() {
  echo "$SECRETS" | python3 -c "
import json, sys
secrets = json.load(sys.stdin)
key = sys.argv[1]
for s in secrets:
    if s.get('key') == key:
        print(s.get('value', ''), end='')
        sys.exit(0)
sys.exit(1)
" "$1" 2>/dev/null
}

# --- Claude Enterprise setup token ---
SETUP_TOKEN=$(get_secret "CLAUDE_SETUP_TOKEN" 2>/dev/null || true)
if [ -n "$SETUP_TOKEN" ]; then
  export CLAUDE_SETUP_TOKEN="$SETUP_TOKEN"
  echo "  Loaded CLAUDE_SETUP_TOKEN"
fi

# --- GitHub token (for cloning private repos) ---
GH_TOKEN=$(get_secret "GITHUB_TOKEN" 2>/dev/null || true)
if [ -n "$GH_TOKEN" ]; then
  export GITHUB_TOKEN="$GH_TOKEN"
  export GH_TOKEN="$GH_TOKEN"
  echo "  Loaded GITHUB_TOKEN"
fi

# --- Write .env files for MCP servers ---
# Each secret named like "mcp-SERVICE/VAR" becomes VAR=value in /opt/mcp/mcp-SERVICE/.env
echo "$SECRETS" | python3 -c "
import json, sys, os
secrets = json.load(sys.stdin)
envs = {}  # {service: {var: value}}
for s in secrets:
    key = s.get('key', '')
    if '/' in key:
        svc, var = key.split('/', 1)
        if svc.startswith('mcp-'):
            envs.setdefault(svc, {})[var] = s.get('value', '')
for svc, pairs in envs.items():
    env_path = f'/opt/mcp/{svc}/.env'
    os.makedirs(os.path.dirname(env_path), exist_ok=True)
    with open(env_path, 'w') as f:
        for var, val in pairs.items():
            f.write(f'{var}={val}\n')
    print(f'  Wrote {env_path} ({len(pairs)} vars)')
" 2>/dev/null || true

# --- Write credentials to Python keyring (for claude_cred.py compatibility) ---
echo "$SECRETS" | python3 -c "
import json, sys
try:
    import keyring
    from keyrings.alt.file import PlaintextKeyring
    keyring.set_keyring(PlaintextKeyring())
except ImportError:
    sys.exit(0)
secrets = json.load(sys.stdin)
count = 0
for s in secrets:
    key = s.get('key', '')
    val = s.get('value', '')
    if '/' in key and val:
        keyring.set_password('claude-code', key, val)
        count += 1
print(f'  Synced {count} secrets to keyring')
" 2>/dev/null || true

echo "  Secret injection complete."
