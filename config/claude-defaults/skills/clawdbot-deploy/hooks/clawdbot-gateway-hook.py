#!/usr/bin/env python3
"""
Clawdbot Gateway Hook for Claude Code

Injects remote Clawdbot gateway context into Claude sessions.
Handles authentication token validation and setup prompts.

Features:
- Detects if Clawdbot auth token is configured
- Prompts user to generate/paste token if missing
- Validates token and warns if invalid
- Injects gateway context for Clawdbot-related queries

Environment Variables:
- CLAWDBOT_GATEWAY_URL: WebSocket URL to gateway (e.g., ws://18.221.133.29:18789)
- CLAWDBOT_GATEWAY_TOKEN: Optional gateway auth token
- CLAWDBOT_CONFIG_PATH: Path to clawdbot config (default: ~/.clawdbot/clawdbot.json)
"""

import json
import os
import sys
import subprocess
from pathlib import Path

# State file to track if we've already prompted for auth this session
STATE_FILE = Path.home() / '.clawdbot' / '.hook-state.json'

def load_state():
    """Load hook state from file."""
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
    except:
        pass
    return {}

def save_state(state):
    """Save hook state to file."""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state))
    except:
        pass

def get_clawdbot_config_path():
    """Get path to clawdbot config file."""
    custom_path = os.environ.get('CLAWDBOT_CONFIG_PATH')
    if custom_path:
        return Path(custom_path)
    return Path.home() / '.clawdbot' / 'clawdbot.json'

def load_clawdbot_config():
    """Load clawdbot configuration."""
    config_path = get_clawdbot_config_path()
    try:
        if config_path.exists():
            return json.loads(config_path.read_text())
    except:
        pass
    return {}

def check_auth_token():
    """
    Check if Clawdbot has a valid auth token configured.

    Returns:
        dict with keys:
        - has_token: bool - whether any token is configured
        - token_valid: bool|None - whether token is valid (None if can't check)
        - token_source: str - where token came from (setup-token, api-key, etc.)
        - error: str|None - error message if any
    """
    config = load_clawdbot_config()

    result = {
        'has_token': False,
        'token_valid': None,
        'token_source': None,
        'error': None
    }

    # Check for token in config
    models = config.get('models', {})
    providers = models.get('providers', {})
    anthropic = providers.get('anthropic', {})

    # Check various token sources
    if anthropic.get('source') == 'setup-token':
        result['has_token'] = True
        result['token_source'] = 'setup-token'
    elif anthropic.get('apiKey'):
        result['has_token'] = True
        result['token_source'] = 'api-key'
    elif os.environ.get('ANTHROPIC_API_KEY'):
        result['has_token'] = True
        result['token_source'] = 'env-var'

    # Try to validate token by checking gateway health
    if result['has_token']:
        try:
            proc = subprocess.run(
                ['clawdbot', 'models', 'status', '--json'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if proc.returncode == 0:
                status = json.loads(proc.stdout)
                result['token_valid'] = status.get('anthropic', {}).get('authenticated', False)
            else:
                # Command failed, might be invalid token
                if 'unauthorized' in proc.stderr.lower() or 'invalid' in proc.stderr.lower():
                    result['token_valid'] = False
                    result['error'] = 'Token appears invalid'
        except subprocess.TimeoutExpired:
            result['error'] = 'Timeout checking token validity'
        except FileNotFoundError:
            result['error'] = 'clawdbot CLI not found'
        except:
            pass

    return result

def get_gateway_status():
    """Check if Clawdbot gateway is reachable."""
    gateway_url = os.environ.get('CLAWDBOT_GATEWAY_URL', '')

    if not gateway_url:
        return None

    try:
        result = subprocess.run(
            ['clawdbot', 'gateway', 'health', '--json'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except:
        pass

    return {'url': gateway_url, 'status': 'unknown'}

def build_auth_setup_instructions():
    """Build instructions for setting up auth token."""
    return """
--- CLAWDBOT AUTH SETUP REQUIRED ---

Clawdbot needs a Claude API token to function.

**Option 1: Enterprise Setup Token (Recommended)**
On your LOCAL machine (with Claude Code authenticated):
```bash
claude setup-token
```
Copy the token, then on the Clawdbot EC2:
```bash
sudo -u clawdbot clawdbot models auth paste-token --provider anthropic
```

**Option 2: API Key**
Get an API key from https://console.anthropic.com/
Then on EC2:
```bash
sudo -u clawdbot clawdbot config set models.providers.anthropic.apiKey "sk-ant-..."
```

After configuring, restart the gateway:
```bash
sudo systemctl restart clawdbot
```

--- END AUTH SETUP ---
"""

def build_auth_warning():
    """Build warning for invalid auth token."""
    return """
--- WARNING: CLAWDBOT AUTH INVALID ---

The configured Clawdbot auth token appears to be invalid or expired.
Clawdbot will not be able to process requests until this is fixed.

To regenerate:
1. On your local machine: `claude setup-token`
2. On EC2: `sudo -u clawdbot clawdbot models auth paste-token --provider anthropic`
3. Restart: `sudo systemctl restart clawdbot`

You can continue, but Clawdbot features won't work.

--- END WARNING ---
"""

def main():
    # Read input from Claude
    input_data = json.loads(sys.stdin.read())
    prompt = input_data.get('prompt', '').lower()

    # Keywords that trigger Clawdbot context injection
    clawdbot_keywords = ['clawdbot', 'gateway', 'remote claude', 'bot', 'signal', 'message']

    gateway_url = os.environ.get('CLAWDBOT_GATEWAY_URL', '')

    # If no gateway configured, skip
    if not gateway_url:
        print(json.dumps({}))
        return

    # Check if prompt mentions Clawdbot-related topics
    mentions_clawdbot = any(kw in prompt for kw in clawdbot_keywords)

    # Load state
    state = load_state()

    # Check auth status
    auth_status = check_auth_token()

    context_parts = []

    # Handle missing auth token
    if not auth_status['has_token']:
        # Only prompt once per session (unless explicitly asked about auth)
        if not state.get('prompted_for_auth') or 'auth' in prompt or 'token' in prompt or 'setup' in prompt:
            context_parts.append(build_auth_setup_instructions())
            state['prompted_for_auth'] = True
            save_state(state)

    # Handle invalid auth token
    elif auth_status['token_valid'] == False:
        # Warn about invalid token (but don't block)
        if not state.get('warned_invalid_auth') or 'auth' in prompt or 'token' in prompt:
            context_parts.append(build_auth_warning())
            state['warned_invalid_auth'] = True
            save_state(state)

    # If prompt mentions Clawdbot, add gateway context
    if mentions_clawdbot:
        gateway_context = [
            "--- CLAWDBOT GATEWAY CONTEXT ---",
            f"Gateway URL: {gateway_url}",
        ]

        # Auth status
        if auth_status['has_token']:
            if auth_status['token_valid'] == True:
                gateway_context.append(f"Authentication: Valid ({auth_status['token_source']})")
            elif auth_status['token_valid'] == False:
                gateway_context.append(f"Authentication: INVALID ({auth_status['token_source']})")
            else:
                gateway_context.append(f"Authentication: Configured ({auth_status['token_source']})")
        else:
            gateway_context.append("Authentication: NOT CONFIGURED")

        # Gateway token (separate from Claude API token)
        gateway_token = os.environ.get('CLAWDBOT_GATEWAY_TOKEN', '')
        if gateway_token:
            gateway_context.append("Gateway Token: Configured")

        # Get gateway status
        status = get_gateway_status()
        if status:
            gateway_context.append(f"Gateway Status: {status.get('status', 'unknown')}")

        gateway_context.extend([
            "",
            "Available Commands:",
            "- clawdbot gateway status  # Check gateway health",
            "- clawdbot models status   # Check API auth",
            "- clawdbot message send    # Send message via gateway",
            "- clawdbot agent run       # Run agent via gateway",
            "--- END CLAWDBOT CONTEXT ---"
        ])

        context_parts.append("\n".join(gateway_context))

    # Output result
    if context_parts:
        output = {"addToPrompt": "\n\n".join(context_parts)}
    else:
        output = {}

    print(json.dumps(output))

if __name__ == '__main__':
    main()
