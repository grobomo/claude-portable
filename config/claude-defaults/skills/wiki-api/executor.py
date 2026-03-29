#!/usr/bin/env python3
"""
Wiki API Executor - Standalone CLI for Confluence API calls

Usage:
    python executor.py search query="my text"
    python executor.py read page_id=1234567
    python executor.py create space_key=~username title="My Page" content="<p>Hello</p>"
    python executor.py --list
    python executor.py --refresh   # Refresh API list from official docs
"""

import os
import sys
import re
import json
import yaml
import base64
import requests
from pathlib import Path

# ============ Configuration ============

SKILL_DIR = Path(__file__).parent
API_INDEX_DIR = SKILL_DIR / "api_index"

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
    """Get base URL for Confluence API."""
    url = os.environ.get('CONFLUENCE_URL', 'https://trendmicro.atlassian.net/wiki')
    return url.rstrip('/')


def get_headers(extra_headers=None):
    """Get standard API headers with Basic auth."""
    username = os.environ.get('CONFLUENCE_USERNAME', '')
    api_token = os.environ.get('CONFLUENCE_API_TOKEN', '')

    # Resolve credential: prefix from OS credential store
    if api_token.startswith('credential:'):
        import keyring
        cred_key = api_token[len('credential:'):]
        service, key = cred_key.rsplit('/', 1) if '/' in cred_key else ('claude-code', cred_key)
        api_token = keyring.get_password('claude-code', cred_key) or ''

    auth = base64.b64encode(f"{username}:{api_token}".encode()).decode()

    headers = {
        'Authorization': f'Basic {auth}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
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

# ============ Helper Functions ============

def extract_page_id(page_id_or_url):
    """Extract page ID from URL or return as-is."""
    if 'pages/' in str(page_id_or_url):
        match = re.search(r'/pages/(\d+)', str(page_id_or_url))
        if match:
            return match.group(1)
    return str(page_id_or_url)

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
    """Substitute path parameters like {page_id} with actual values."""
    result = endpoint
    for key in list(params.keys()):
        placeholder = f"{{{key}}}"
        if placeholder in result:
            value = params.pop(key)
            # Extract page ID if URL provided
            if 'page_id' in key:
                value = extract_page_id(value)
            result = result.replace(placeholder, str(value))
    return result


def execute_search(endpoint, params, config):
    """Execute search with CQL."""
    query_params = {}

    # Build CQL query
    query = params.pop("query", "")
    space = params.pop("space", "")

    if 'type=' in query or 'space=' in query:
        # Already CQL
        cql = query
    else:
        # Build CQL from text search
        cql = f'type=page AND text ~ "{query}"'
        if space:
            cql += f' AND space="{space}"'

    query_params['cql'] = cql

    # Pagination
    if "limit" in params:
        query_params['limit'] = str(params.pop("limit"))

    return api_request("GET", endpoint, params=query_params)


def execute_read(endpoint, params, config):
    """Read page content."""
    format_type = params.pop("format", "text")
    # max_length: truncates page content -- NOT recommended, loses data.
    # Set to 0 (default) for full content. Only use if you explicitly need truncation.
    max_length = int(params.pop("max_length", 0))

    query_params = {'expand': 'body.storage,version,space'}

    result = api_request("GET", endpoint, params=query_params)

    if 'error' in result:
        return result

    body = result.get('body', {}).get('storage', {}).get('value', '')

    if format_type == 'json':
        return result
    elif format_type == 'html':
        return {'content': body, 'title': result.get('title'), 'id': result.get('id')}
    else:
        # Text format - strip HTML
        text = re.sub(r'<[^>]+>', ' ', body)
        text = re.sub(r'\s+', ' ', text).strip()
        if max_length > 0 and len(text) > max_length:
            text = text[:max_length] + '...'
        return {
            'title': result.get('title'),
            'id': result.get('id'),
            'space': result.get('space', {}).get('key'),
            'content': text
        }


def execute_children(endpoint, params, config):
    """List child pages."""
    result = api_request("GET", endpoint)

    if 'error' in result:
        return result

    children = []
    for item in result.get('results', []):
        children.append({
            'id': item['id'],
            'title': item['title']
        })

    return {'children': children, 'count': len(children)}


def execute_create(endpoint, params, config):
    """Create new page."""
    body = {
        "type": "page",
        "title": params.get("title", "Untitled"),
        "space": {"key": params.get("space_key", "")},
        "body": {"storage": {"value": params.get("content", ""), "representation": "storage"}}
    }

    if params.get("parent_id"):
        body["ancestors"] = [{"id": extract_page_id(params["parent_id"])}]

    return api_request("POST", endpoint, body=body)


def execute_update(endpoint, params, config):
    """Update existing page."""
    # First get current version
    page_id = extract_page_id(params.get("page_id", ""))
    get_endpoint = f"/rest/api/content/{page_id}"

    current = api_request("GET", get_endpoint, params={'expand': 'version'})
    if 'error' in current:
        return current

    version = current['version']['number'] + 1

    body = {
        "type": "page",
        "title": params.get("title", current.get('title', '')),
        "version": {"number": version},
        "body": {"storage": {"value": params.get("content", ""), "representation": "storage"}}
    }

    return api_request("PUT", endpoint, body=body)


def execute_delete(endpoint, params, config):
    """Delete page."""
    return api_request("DELETE", endpoint)


def execute_comments(endpoint, params, config):
    """Get or add comments."""
    if params.get("add"):
        # Add comment
        page_id = extract_page_id(params.get("page_id", ""))
        body = {
            "type": "comment",
            "container": {"id": page_id, "type": "page"},
            "body": {"storage": {"value": f"<p>{params['add']}</p>", "representation": "storage"}}
        }
        return api_request("POST", "/rest/api/content", body=body)
    else:
        # List comments
        result = api_request("GET", endpoint, params={'expand': 'body.storage'})
        if 'error' in result:
            return result

        comments = []
        for c in result.get('results', []):
            body = re.sub(r'<[^>]+>', '', c.get('body', {}).get('storage', {}).get('value', ''))
            comments.append({'id': c['id'], 'text': body[:200]})

        return {'comments': comments, 'count': len(comments)}


def execute_labels(endpoint, params, config):
    """Get or add labels."""
    if params.get("add"):
        # Add label
        body = [{"prefix": "global", "name": params["add"]}]
        return api_request("POST", endpoint, body=body)
    else:
        # List labels
        result = api_request("GET", endpoint)
        if 'error' in result:
            return result

        labels = [l['name'] for l in result.get('results', [])]
        return {'labels': labels}


# Template dispatcher
TEMPLATES = {
    "search": execute_search,
    "read": execute_read,
    "children": execute_children,
    "create": execute_create,
    "update": execute_update,
    "delete": execute_delete,
    "comments": execute_comments,
    "labels": execute_labels,
}


def execute(operation, params):
    """Execute an API operation."""
    if operation not in OPERATIONS:
        return {"error": f"Unknown operation: {operation}. Run with --list to see available operations."}

    config = OPERATIONS[operation]
    template_name = config.get("template", "search")
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
        print("       python executor.py --refresh [--apply] [--no-analyze]")
        print("       python executor.py --analyze [--skip-research]")
        print("\nExamples:")
        print("  python executor.py search query=\"API docs\"")
        print("  python executor.py read page_id=1234567")
        print("  python executor.py create space_key=~user title=\"New Page\" content=\"<p>Hello</p>\"")
        sys.exit(1)

    if sys.argv[1] == '--list':
        print(f"Available operations ({len(OPERATIONS)}):\n")
        for op in list_operations():
            print(op)
        sys.exit(0)

    if sys.argv[1] == '--analyze':
        import subprocess
        analyze_script = SKILL_DIR / "analyze_userstories.py"
        args = ["python", str(analyze_script)] + sys.argv[2:]
        subprocess.run(args)
        sys.exit(0)

    if sys.argv[1] == '--refresh':
        import subprocess
        refresh_script = SKILL_DIR / "refresh_api.py"
        args = ["python", str(refresh_script)] + sys.argv[2:]
        subprocess.run(args)
        sys.exit(0)

    operation = sys.argv[1]
    params = parse_params(sys.argv[2:])

    result = execute(operation, params)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
