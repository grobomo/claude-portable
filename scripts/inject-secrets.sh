#!/bin/bash
# Fetch secrets and write to config files.
# Supports two modes:
#   1. BWS mode: BWS_ACCESS_TOKEN set -> fetch from Bitwarden Secrets Manager
#   2. Direct mode: Individual env vars set -> use directly
set -euo pipefail

CLAUDE_DIR="$HOME/.claude"

# --- Mode 1: BWS (Bitwarden Secrets Manager) ---
if [ -n "${BWS_ACCESS_TOKEN:-}" ]; then
  echo "  Mode: Bitwarden Secrets Manager"
  SECRETS=$(bws secret list 2>/dev/null || echo "[]")
  if [ "$SECRETS" = "[]" ]; then
    echo "  WARNING: No secrets found in BWS (or auth failed)."
  else
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

    # Export secrets as env vars for downstream scripts
    for var in GITHUB_TOKEN CLAUDE_OAUTH_ACCESS_TOKEN CLAUDE_OAUTH_REFRESH_TOKEN \
               V1_API_TOKEN CONFLUENCE_API_TOKEN JIRA_API_TOKEN TRELLO_API_TOKEN \
               SSH_PUBLIC_KEY; do
      val=$(get_secret "$var" 2>/dev/null || true)
      if [ -n "$val" ]; then
        export "$var=$val"
        echo "  Loaded $var from BWS"
      fi
    done

    # Write MCP .env files (secrets named mcp-SERVICE/VAR)
    echo "$SECRETS" | python3 -c "
import json, sys, os
secrets = json.load(sys.stdin)
envs = {}
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
  fi
fi

# --- Mode 2: Direct env vars (already set in docker-compose environment) ---
# Both modes converge here: write credentials from env vars (however they were loaded)

# Write Claude OAuth credentials
if [ -n "${CLAUDE_OAUTH_ACCESS_TOKEN:-}" ] && [ -n "${CLAUDE_OAUTH_REFRESH_TOKEN:-}" ]; then
  mkdir -p "$CLAUDE_DIR"
  EXPIRES_AT="${CLAUDE_OAUTH_EXPIRES_AT:-$(python3 -c "import time; print(int((time.time()+3600)*1000))")}"
  cat > "$CLAUDE_DIR/.credentials.json" << CREDEOF
{
  "claudeAiOauth": {
    "accessToken": "${CLAUDE_OAUTH_ACCESS_TOKEN}",
    "refreshToken": "${CLAUDE_OAUTH_REFRESH_TOKEN}",
    "expiresAt": ${EXPIRES_AT},
    "scopes": ["user:inference", "user:mcp_servers", "user:profile", "user:sessions:claude_code"],
    "subscriptionType": "${CLAUDE_SUBSCRIPTION_TYPE:-individual}",
    "rateLimitTier": "${CLAUDE_RATE_LIMIT_TIER:-default}"
  }
}
CREDEOF
  chmod 600 "$CLAUDE_DIR/.credentials.json"
  echo "  Wrote Claude OAuth credentials"
fi

# Write GitHub token to git config for private repo cloning
if [ -n "${GITHUB_TOKEN:-}" ]; then
  git config --global credential.helper store
  echo "https://x-access-token:${GITHUB_TOKEN}@github.com" > "$HOME/.git-credentials"
  chmod 600 "$HOME/.git-credentials"
  echo "  Configured GitHub token"
fi

# Write SSH public key for rsync access
if [ -n "${SSH_PUBLIC_KEY:-}" ]; then
  mkdir -p "$HOME/.ssh"
  echo "$SSH_PUBLIC_KEY" > "$HOME/.ssh/authorized_keys"
  chmod 600 "$HOME/.ssh/authorized_keys"
  chmod 700 "$HOME/.ssh"
  echo "  Configured SSH public key"
fi

echo "  Secret injection complete."
