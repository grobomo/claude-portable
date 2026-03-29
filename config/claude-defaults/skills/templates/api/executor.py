#!/usr/bin/env python3
"""
API Executor Template - Standalone CLI for API calls

Usage:
    python executor.py operation_name key=value
    python executor.py --list
    python executor.py --help

Customize this file for your specific API.
"""

import os
import sys
import json
import yaml
import requests
from pathlib import Path

# ============ Configuration ============

SKILL_DIR = Path(__file__).parent
API_INDEX_DIR = SKILL_DIR / "api_index"

# Update for your API
BASE_URL = os.environ.get('API_BASE_URL', 'https://api.example.com')

# Or use regional URLs:
# REGION_URLS = {
#     'us': 'https://api.example.com',
#     'eu': 'https://api.eu.example.com',
# }

# ============ Environment Loading ============

def load_env():
    """Load .env file from skill folder."""
    env_file = SKILL_DIR / '.env'
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip().strip('"\'')

load_env()

# ============ API Request ============

_session = None

def get_session():
    """Get reusable session with connection pooling."""
    global _session
    if _session is None:
        _session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10, pool_maxsize=20,
            max_retries=requests.adapters.Retry(total=2, backoff_factor=0.5)
        )
        _session.mount('https://', adapter)
    return _session


def get_base_url():
    """Get base URL for API."""
    # Simple version:
    return BASE_URL

    # Regional version:
    # region = os.environ.get('API_REGION', 'us').lower()
    # return REGION_URLS.get(region, REGION_URLS['us'])


def get_headers(extra_headers=None):
    """Get standard API headers. Customize for your auth method."""
    api_key = os.environ.get('API_KEY', '')

    # Bearer token auth (most common)
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }

    # Basic auth alternative:
    # import base64
    # username = os.environ.get('API_USERNAME', '')
    # auth = base64.b64encode(f"{username}:{api_key}".encode()).decode()
    # headers = {
    #     'Authorization': f'Basic {auth}',
    #     'Content-Type': 'application/json',
    # }

    if extra_headers:
        headers.update(extra_headers)
    return headers


def api_request(method, endpoint, params=None, body=None, headers=None, timeout=30):
    """Make API request and return response."""
    url = f"{get_base_url()}{endpoint}"
    hdrs = get_headers(headers)
    session = get_session()

    try:
        if method == 'GET':
            r = session.get(url, headers=hdrs, params=params, timeout=timeout)
        elif method == 'POST':
            r = session.post(url, headers=hdrs, params=params, json=body, timeout=timeout)
        elif method == 'PUT':
            r = session.put(url, headers=hdrs, json=body, timeout=timeout)
        elif method == 'PATCH':
            r = session.patch(url, headers=hdrs, json=body, timeout=timeout)
        elif method == 'DELETE':
            r = session.delete(url, headers=hdrs, json=body, timeout=timeout)
        else:
            return {'error': f'Unsupported method: {method}'}

        if r.status_code not in (200, 201, 202, 204):
            return {'error': f'HTTP {r.status_code}: {r.text[:500]}'}

        if r.status_code == 204 or not r.text:
            return {'success': True}

        return r.json()
    except Exception as e:
        return {'error': str(e)}

# ============ YAML Config Loading ============

OPERATIONS = {}

def load_operations():
    """Load all operations from YAML files."""
    global OPERATIONS
    OPERATIONS = {}

    if not API_INDEX_DIR.exists():
        return 0

    for folder in API_INDEX_DIR.iterdir():
        if not folder.is_dir() or folder.name.startswith("_"):
            continue
        config_file = folder / "config.yaml"
        if config_file.exists():
            try:
                data = yaml.safe_load(config_file.read_text())
                if data and "name" in data:
                    OPERATIONS[data["name"]] = data
            except Exception as e:
                print(f"Warning: Failed to load {config_file}: {e}", file=sys.stderr)

    return len(OPERATIONS)

# ============ Template Execution ============

def substitute_path_params(endpoint, params):
    """Substitute path parameters like {id} with actual values."""
    result = endpoint
    for key in list(params.keys()):
        placeholder = f"{{{key}}}"
        if placeholder in result:
            result = result.replace(placeholder, str(params.pop(key)))
    return result


def execute_get_single(endpoint, params, config):
    """GET single resource."""
    return api_request("GET", endpoint, params=params if params else None)


def execute_get_list(endpoint, params, config):
    """GET list with pagination."""
    query_params = {}

    # Handle pagination
    pag = config.get("pagination")
    if pag and "limit" in params:
        limit = params.pop("limit")
        query_params[pag.get("param", "limit")] = str(min(limit, pag.get("max", 100)))

    # Pass remaining params as query params
    query_params.update(params)

    return api_request("GET", endpoint, params=query_params)


def execute_get_search(endpoint, params, config):
    """GET with search query."""
    query_params = {}

    # Handle search query
    search_param = config.get("search_param", "query")
    if "query" in params:
        query_params[search_param] = params.pop("query")

    # Handle pagination
    if "limit" in params:
        query_params["limit"] = str(params.pop("limit"))

    query_params.update(params)

    return api_request("GET", endpoint, params=query_params)


def execute_post_create(endpoint, params, config):
    """POST to create resource."""
    return api_request("POST", endpoint, body=params)


def execute_post_action(endpoint, params, config):
    """POST to trigger action."""
    return api_request("POST", endpoint, body=params)


def execute_put_update(endpoint, params, config):
    """PUT to fully update resource."""
    return api_request("PUT", endpoint, body=params)


def execute_patch_update(endpoint, params, config):
    """PATCH to partially update resource."""
    return api_request("PATCH", endpoint, body=params)


def execute_delete(endpoint, params, config):
    """DELETE resource."""
    return api_request("DELETE", endpoint, body=params if params else None)


# Template dispatcher
TEMPLATES = {
    "get_single": execute_get_single,
    "get_list": execute_get_list,
    "get_search": execute_get_search,
    "post_create": execute_post_create,
    "post_action": execute_post_action,
    "put_update": execute_put_update,
    "patch_update": execute_patch_update,
    "delete": execute_delete,
}


def execute(operation, params):
    """Execute an API operation."""
    if operation not in OPERATIONS:
        return {"error": f"Unknown operation: {operation}. Run with --list to see available operations."}

    config = OPERATIONS[operation]
    template_name = config.get("template", "get_single")
    template_fn = TEMPLATES.get(template_name)

    if not template_fn:
        return {"error": f"Unknown template: {template_name}"}

    # Substitute path params
    endpoint = substitute_path_params(config["endpoint"], params)

    # Apply defaults
    for param in config.get("params", {}).get("optional", []):
        if param["name"] not in params and param.get("default"):
            params[param["name"]] = param["default"]

    template_config = config.get("template_config", {})
    return template_fn(endpoint, params, template_config)

# ============ CLI ============

def parse_params(args):
    """Parse key=value arguments into dict."""
    params = {}
    for arg in args:
        if '=' in arg:
            key, value = arg.split('=', 1)
            try:
                value = int(value)
            except ValueError:
                pass
            params[key] = value
    return params


def list_operations():
    """List all available operations."""
    ops = []
    for name in sorted(OPERATIONS.keys()):
        desc = OPERATIONS[name].get("description", "")[:60]
        ops.append(f"  {name}: {desc}")
    return ops


def main():
    # Load operations
    load_operations()

    if len(sys.argv) < 2:
        print("Usage: python executor.py <operation> [key=value ...]")
        print("       python executor.py --list")
        print("\nExamples:")
        print("  python executor.py search query=\"my search\"")
        print("  python executor.py get_item id=12345")
        sys.exit(1)

    if sys.argv[1] == '--list':
        print(f"Available operations ({len(OPERATIONS)}):\n")
        for op in list_operations():
            print(op)
        sys.exit(0)

    if sys.argv[1] == '--help':
        print(__doc__)
        sys.exit(0)

    operation = sys.argv[1]
    params = parse_params(sys.argv[2:])

    result = execute(operation, params)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
