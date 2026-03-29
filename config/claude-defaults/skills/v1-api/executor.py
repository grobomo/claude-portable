#!/usr/bin/env python3
"""
V1 API Executor - Standalone CLI for Vision One API calls

Usage:
    python executor.py list_alerts days=7 severity=critical limit=10
    python executor.py search_endpoint_logs hours=24 filter="processName:powershell*"
    python executor.py add_to_blocklist ioc_type=ip value=192.168.1.100
    python executor.py --list
    python executor.py --refresh   # Refresh API list from official docs
"""

import os
import sys
import json
import yaml
import requests
from urllib3.util.ssl_ import create_urllib3_context
from pathlib import Path
import time
from datetime import datetime, timedelta, timezone

# ============ Configuration ============

SKILL_DIR = Path(__file__).parent
API_INDEX_DIR = SKILL_DIR / "api_index"

REGION_URLS = {
    'us': 'https://api.xdr.trendmicro.com',
    'eu': 'https://api.eu.xdr.trendmicro.com',
    'jp': 'https://api.xdr.trendmicro.co.jp',
    'sg': 'https://api.sg.xdr.trendmicro.com',
    'au': 'https://api.au.xdr.trendmicro.com',
    'in': 'https://api.in.xdr.trendmicro.com',
    'ae': 'https://api.mea.xdr.trendmicro.com',
}

# ============ Environment Loading ============
# Requires: credential-manager (pip install keyring)
# API keys stored in OS credential store - no plaintext .env fallback

_cred_path = os.path.expanduser('~/.claude/super-manager/credentials')
sys.path.insert(0, _cred_path)
try:
    from claude_cred import load_env
    load_env()
except ImportError:
    raise RuntimeError(
        "credential-manager required. Install: claude plugin install credential-manager@grobomo-marketplace"
    )
finally:
    sys.path.remove(_cred_path)

# ============ API Request ============

_session = None

# DNS override support for VPN environments
DNS_OVERRIDE = {
    'api.xdr.trendmicro.com': os.environ.get('V1_DNS_IP', '54.81.200.252'),
    'api.eu.xdr.trendmicro.com': os.environ.get('V1_DNS_IP_EU', ''),
    'api.xdr.trendmicro.co.jp': os.environ.get('V1_DNS_IP_JP', ''),
}


class DNSResolverAdapter(requests.adapters.HTTPAdapter):
    """HTTP Adapter that overrides DNS resolution while preserving SSL verification."""

    def __init__(self, dns_overrides=None, **kwargs):
        self.dns_overrides = dns_overrides or {}
        super().__init__(**kwargs)

    def get_connection(self, url, proxies=None):
        """Override to inject custom DNS resolution via socket patching."""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        hostname = parsed.hostname

        if hostname in self.dns_overrides and self.dns_overrides[hostname]:
            # Patch socket.getaddrinfo to return our IP for this host
            import socket
            original_getaddrinfo = socket.getaddrinfo
            override_ip = self.dns_overrides[hostname]

            def patched_getaddrinfo(host, port, *args, **kwargs):
                if host == hostname:
                    # Return the override IP but keep original hostname for SNI
                    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (override_ip, port))]
                return original_getaddrinfo(host, port, *args, **kwargs)

            socket.getaddrinfo = patched_getaddrinfo
            try:
                conn = super().get_connection(url, proxies)
            finally:
                socket.getaddrinfo = original_getaddrinfo
            return conn

        return super().get_connection(url, proxies)


def get_session():
    """Get reusable session with connection pooling and DNS override."""
    global _session
    if _session is None:
        _session = requests.Session()

        # Use DNS override adapter if V1_DNS_OVERRIDE env is set
        if os.environ.get('V1_DNS_OVERRIDE', 'auto') != 'disabled':
            adapter = DNSResolverAdapter(
                dns_overrides=DNS_OVERRIDE,
                pool_connections=10, pool_maxsize=20,
                max_retries=requests.adapters.Retry(total=2, backoff_factor=0.5)
            )
        else:
            adapter = requests.adapters.HTTPAdapter(
                pool_connections=10, pool_maxsize=20,
                max_retries=requests.adapters.Retry(total=2, backoff_factor=0.5)
            )
        _session.mount('https://', adapter)
    return _session


def get_base_url():
    """Get base URL for current region."""
    region = os.environ.get('V1_REGION', 'us').lower()
    return REGION_URLS.get(region, REGION_URLS['us'])


def get_headers(extra_headers=None):
    """Get standard API headers."""
    api_key = os.environ.get('V1_API_KEY', '')
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'User-Agent': 'v1-api-skill/1.0'
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


def api_request_all_pages(method, endpoint, params=None, body=None, headers=None, timeout=30, max_pages=50):
    """Make API request and follow nextLink/progressRate to get ALL results.

    V1 search APIs return progressRate < 100 while still searching, and
    nextLink to fetch subsequent pages. This follows both automatically.
    """
    all_items = []
    page = 0
    url = f"{get_base_url()}{endpoint}"
    hdrs = get_headers(headers)
    session = get_session()

    while page < max_pages:
        try:
            if page == 0:
                r = session.get(url, headers=hdrs, params=params, timeout=timeout)
            else:
                # nextLink is a full URL, no extra params needed
                r = session.get(url, headers=hdrs, timeout=timeout)

            if r.status_code not in (200, 201, 202, 204):
                if all_items:
                    return {'items': all_items, 'error': f'Page {page}: HTTP {r.status_code}'}
                return {'error': f'HTTP {r.status_code}: {r.text[:500]}'}

            if r.status_code == 204 or not r.text:
                break

            data = r.json()
            items = data.get('items', [])
            all_items.extend(items)

            # Check for next page
            next_link = data.get('nextLink', '')
            progress = data.get('progressRate', 100)

            if next_link:
                url = next_link
                page += 1
            elif progress < 100:
                # Search still running but no nextLink yet -- wait and retry same URL
                time.sleep(1)
                page += 1
            else:
                break

        except Exception as e:
            if all_items:
                return {'items': all_items, 'error': f'Page {page}: {str(e)}'}
            return {'error': str(e)}

    result = {'items': all_items}
    if page >= max_pages:
        result['truncated'] = True
        result['pages_fetched'] = page
    result['progressRate'] = 100
    result['totalItems'] = len(all_items)
    return result

# ============ YAML Config Loading ============

OPERATIONS = {}

def load_operations():
    """Load all operations from YAML files."""
    global OPERATIONS
    OPERATIONS = {}

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
    """Substitute path parameters like {alert_id} with actual values."""
    result = endpoint
    for key in list(params.keys()):
        placeholder = f"{{{key}}}"
        if placeholder in result:
            result = result.replace(placeholder, str(params.pop(key)))
    return result


def execute_standard_list(endpoint, params, config):
    """Execute standard list API call."""
    query_params = {}

    # Build date range
    date_cfg = config.get("date_params")
    if date_cfg:
        unit = date_cfg.get("unit", "days")
        if unit == "days" and "days" in params:
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=params.pop("days"))
            query_params[date_cfg["start"]] = start.strftime('%Y-%m-%dT%H:%M:%SZ')
            query_params[date_cfg["end"]] = end.strftime('%Y-%m-%dT%H:%M:%SZ')
        elif unit == "hours" and "hours" in params:
            end = datetime.now(timezone.utc)
            start = end - timedelta(hours=params.pop("hours"))
            query_params[date_cfg["start"]] = start.strftime('%Y-%m-%dT%H:%M:%SZ')
            query_params[date_cfg["end"]] = end.strftime('%Y-%m-%dT%H:%M:%SZ')
    else:
        params.pop("days", None)
        params.pop("hours", None)

    # Build pagination
    pag = config.get("pagination")
    if pag and "limit" in params:
        limit = params.pop("limit")
        if pag.get("type") == "int" and "max" in pag:
            query_params[pag["param"]] = str(min(limit, pag["max"]))
        elif pag.get("type") == "enum" and "values" in pag:
            values = pag["values"]
            top_val = min(values, key=lambda x: abs(x - limit) if limit <= x else float('inf'))
            query_params[pag["param"]] = str(top_val)
    elif "limit" in params:
        params.pop("limit")

    # Build OData filters
    filters = []
    filter_mappings = {
        "severity": "severity eq '{}'",
        "status": "investigationStatus eq '{}'",
        "risk_level": "riskLevel eq '{}'",
        "provider": "provider eq '{}'",
        "ioc_type": "type eq '{}'",
    }
    for param, template in filter_mappings.items():
        if param in params and params[param]:
            filters.append(template.format(params.pop(param)))

    if "risk_score" in params and params["risk_score"] > 0:
        filters.append(f"latestRiskScore ge {params.pop('risk_score')}")

    if "filter" in params and params["filter"]:
        filters.append(params.pop("filter"))
    elif "filter" in params:
        params.pop("filter")

    # Handle filter style
    extra_headers = {}
    filter_style = config.get("filter_style", "odata")
    if filters:
        filter_expr = " and ".join(filters)
        if filter_style == "odata":
            query_params["filter"] = filter_expr
        elif filter_style == "header":
            extra_headers[config.get("filter_header", "TMV1-Filter")] = filter_expr

    if config.get("order_by"):
        query_params["orderBy"] = config["order_by"]

    return api_request_all_pages("GET", endpoint, params=query_params, headers=extra_headers if extra_headers else None)


def execute_search(endpoint, params, config):
    """Execute search API call with TMV1-Query header."""
    query_params = {}
    extra_headers = {}

    # Build date range (hours)
    date_cfg = config.get("date_params")
    if date_cfg and "hours" in params:
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=params.pop("hours"))
        query_params[date_cfg["start"]] = start.strftime('%Y-%m-%dT%H:%M:%SZ')
        query_params[date_cfg["end"]] = end.strftime('%Y-%m-%dT%H:%M:%SZ')

    # Build pagination
    pag = config.get("pagination")
    if pag and "limit" in params:
        limit = params.pop("limit")
        query_params[pag["param"]] = str(min(limit, pag.get("max", 200)))
    elif "limit" in params:
        params.pop("limit")

    # Handle TMV1-Query header
    if "filter" in params and params["filter"]:
        extra_headers["TMV1-Query"] = params.pop("filter")
    else:
        params.pop("filter", None)
        extra_headers["TMV1-Query"] = config.get("default_filter", "*")

    return api_request_all_pages("GET", endpoint, params=query_params, headers=extra_headers)


def execute_single_get(endpoint, params, config):
    """Execute single resource GET."""
    return api_request("GET", endpoint, params=params if params else None)


def execute_simple_list(endpoint, params, config):
    """Execute simple list with no params."""
    return api_request("GET", endpoint)


def execute_response_action(endpoint, params, config):
    """Execute response action POST with array body."""
    builder_name = config.get("body_builder", "endpoint_action")

    body_builders = {
        "endpoint_action": lambda p: [{"agentGuid": p["endpoint_guid"], "description": p.get("description", "")}],
        "file_collect": lambda p: [{"agentGuid": p["endpoint_guid"], "filePath": p["file_path"], "description": p.get("description", "")}],
        "process_terminate": lambda p: [{"agentGuid": p["endpoint_guid"], "fileSha1": p["file_sha1"], "description": p.get("description", "")}],
        "email_action": lambda p: [{"messageId": p["message_id"], "mailbox": p["mailbox"], "description": p.get("description", "")}],
        "blocklist_add": lambda p: [{"type": p["ioc_type"], "value": p["value"], "riskLevel": p.get("risk_level", "high"), "description": p.get("description", ""), "daysToExpiration": p.get("days_to_expiration", 0)}],
        "blocklist_remove": lambda p: [{"type": p["ioc_type"], "value": p["value"]}],
    }

    builder = body_builders.get(builder_name)
    if not builder:
        return {"error": f"Unknown body builder: {builder_name}"}

    return api_request("POST", endpoint, body=builder(params))


def execute_post_action(endpoint, params, config):
    """Execute POST action with object body."""
    return api_request("POST", endpoint, body=params)


def execute_patch_update(endpoint, params, config):
    """Execute PATCH update."""
    return api_request("PATCH", endpoint, body=params)


# Template dispatcher
TEMPLATES = {
    "standard_list": execute_standard_list,
    "search": execute_search,
    "single_get": execute_single_get,
    "simple_list": execute_simple_list,
    "response_action": execute_response_action,
    "post_action": execute_post_action,
    "patch_update": execute_patch_update,
}


def execute(operation, params):
    """Execute an API operation."""
    if operation not in OPERATIONS:
        return {"error": f"Unknown operation: {operation}. Run with --list to see available operations."}

    config = OPERATIONS[operation]
    template_name = config.get("template", "standard_list")
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
        print("       python executor.py --refresh")
        print("\nExamples:")
        print("  python executor.py list_alerts days=7 severity=critical")
        print("  python executor.py list_oat days=7 limit=10")
        print("  python executor.py search_endpoint_logs hours=24")
        sys.exit(1)

    if sys.argv[1] == '--list':
        print(f"Available operations ({len(OPERATIONS)}):\n")
        for op in list_operations():
            print(op)
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
