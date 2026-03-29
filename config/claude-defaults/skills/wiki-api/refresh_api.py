#!/usr/bin/env python3
"""
Wiki API Spec Refresh

Fetches the official Confluence API spec and compares to local api_index.
Generates YAML configs for any new operations.

Usage:
    python refresh_api.py           # Show diff only
    python refresh_api.py --apply   # Create configs for new operations
    python refresh_api.py --check-versions  # Check for API version updates

Sources:
- Confluence Cloud REST API v1: https://developer.atlassian.com/cloud/confluence/rest/v1/
- Confluence Cloud REST API v2: https://developer.atlassian.com/cloud/confluence/rest/v2/
- Postman Collections: https://developer.atlassian.com/cloud/confluence/confcloud.1.postman.json
"""

import os
import sys
import re
import json
import yaml
import requests
from pathlib import Path
from datetime import datetime

SKILL_DIR = Path(__file__).parent
API_INDEX_DIR = SKILL_DIR / "api_index"
CACHE_FILE = SKILL_DIR / ".api_spec_cache.json"

# Atlassian API sources
API_SOURCES = {
    "v1": {
        "postman": "https://developer.atlassian.com/cloud/confluence/confcloud.1.postman.json",
        "docs": "https://developer.atlassian.com/cloud/confluence/rest/v1/",
    },
    "v2": {
        "postman": "https://developer.atlassian.com/cloud/confluence/confcloud.2.postman.json",
        "docs": "https://developer.atlassian.com/cloud/confluence/rest/v2/",
    }
}

# Template mapping
TEMPLATE_MAP = {
    ("GET", "search"): "search",
    ("GET", "single"): "read",
    ("GET", "child"): "children",
    ("GET", "list"): "search",
    ("POST", "create"): "create",
    ("POST", "action"): "create",
    ("PUT", "update"): "update",
    ("DELETE", "delete"): "delete",
}


def fetch_postman_collection(version="v1"):
    """Fetch Postman collection from Atlassian."""
    url = API_SOURCES[version]["postman"]
    print(f"Fetching {version} API from {url}...")

    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        spec = r.json()
        print(f"  Fetched successfully")
        return spec
    except Exception as e:
        print(f"  Error: {e}")
        return None


def parse_postman_collection(collection):
    """Parse Postman collection into operation list."""
    operations = []

    def extract_items(items, folder_name=""):
        for item in items:
            if "item" in item:
                # It's a folder
                name = item.get("name", "")
                extract_items(item["item"], name)
            elif "request" in item:
                # It's a request
                req = item["request"]
                method = req.get("method", "GET")

                # Get path - handle Postman URL format
                url = req.get("url", {})
                if isinstance(url, str):
                    path = url
                else:
                    # Postman path can be string (with {{basePath}}) or array
                    path_data = url.get("path", "")
                    if isinstance(path_data, str):
                        # Path is a string like "{{basePath}}wiki/rest/api/audit"
                        # Remove {{basePath}} prefix and ensure leading /
                        path = re.sub(r'\{\{[^}]+\}\}', '', path_data)
                        if not path.startswith('/'):
                            path = '/' + path
                    elif isinstance(path_data, list):
                        # Path is an array of segments
                        path_parts = [p for p in path_data if not p.startswith('{{')]
                        path = "/" + "/".join(path_parts)
                    else:
                        continue

                # Clean up path - remove double slashes
                path = re.sub(r'//+', '/', path)

                # Skip if path is empty
                if not path or path == '/':
                    continue

                # Normalize path - convert :param to {param}
                path = re.sub(r':(\w+)', r'{\1}', path)

                op = {
                    "name": item.get("name", ""),
                    "method": method,
                    "path": path,
                    "folder": folder_name,
                    "description": item.get("name", ""),
                }

                # Determine template
                has_id = '{' in path and path.endswith('}')
                is_search = 'search' in path.lower() or 'cql' in path.lower()
                is_child = 'child' in path.lower()

                if method == "GET":
                    if is_search:
                        op["template"] = "search"
                    elif is_child:
                        op["template"] = "children"
                    elif has_id:
                        op["template"] = "read"
                    else:
                        op["template"] = "search"
                elif method == "POST":
                    op["template"] = "create"
                elif method == "PUT":
                    op["template"] = "update"
                elif method == "DELETE":
                    op["template"] = "delete"
                else:
                    op["template"] = "read"

                operations.append(op)

    if "item" in collection:
        extract_items(collection["item"])

    return operations


def path_to_name(method, path):
    """Convert API path to snake_case operation name."""
    # Remove /wiki/rest/api/ or /wiki/api/v2/ prefix
    clean_path = re.sub(r'^/wiki/(rest/api|api/v\d+)/', '', path)

    # Check if ends with {param}
    is_single = clean_path.endswith('}')

    # Remove path parameters
    clean_path = re.sub(r'/\{[^}]+\}', '', clean_path)

    # Split and clean
    parts = [p for p in clean_path.split('/') if p]
    if not parts:
        return ""

    # Convert camelCase to snake_case
    snake_parts = []
    for p in parts:
        p = re.sub(r'(?<!^)(?=[A-Z])', '_', p).lower()
        snake_parts.append(p)

    # Build name based on method
    if method == "GET":
        prefix = "get" if is_single else "list"
    elif method == "POST":
        prefix = "create"
    elif method == "PUT":
        prefix = "update"
    elif method == "DELETE":
        prefix = "delete"
    else:
        prefix = method.lower()

    # Join parts
    name_parts = []
    if prefix and prefix not in snake_parts[0]:
        name_parts.append(prefix)
    name_parts.extend(snake_parts)

    name = '_'.join(name_parts)
    name = re.sub(r'[^a-z0-9_]', '_', name)
    name = re.sub(r'_+', '_', name)
    return name.strip('_')


def get_existing_operations():
    """Get existing operations with their endpoints."""
    existing = {}  # name -> endpoint
    if not API_INDEX_DIR.exists():
        return existing

    for folder in API_INDEX_DIR.iterdir():
        if not folder.is_dir() or folder.name.startswith("_"):
            continue
        config_file = folder / "config.yaml"
        if config_file.exists():
            try:
                config = yaml.safe_load(config_file.read_text())
                endpoint = config.get("endpoint", "")
                existing[folder.name] = endpoint
            except:
                existing[folder.name] = ""
        else:
            existing[folder.name] = ""

    return existing


def normalize_endpoint(ep):
    """Normalize endpoint for comparison."""
    # Remove path params
    ep = re.sub(r'/\{[^}]+\}', '/{id}', ep)
    # Remove prefix variations - handle both /wiki/rest/api and /rest/api
    ep = re.sub(r'^/wiki/', '/', ep)
    ep = re.sub(r'^/(rest/api|api/v\d+)/', '/', ep)
    return ep


def generate_yaml_config(op):
    """Generate YAML config for an operation."""
    name = path_to_name(op["method"], op["path"])

    config = {
        "name": name,
        "description": op.get("description", ""),
        "method": op["method"],
        "endpoint": op["path"],
        "template": op.get("template", "read"),
        "tags": [op.get("folder", "general")],
        "params": {
            "required": [],
            "optional": [],
        },
        "template_config": {},
    }

    # Extract path params as required
    path_params = re.findall(r'\{(\w+)\}', op["path"])
    for param in path_params:
        config["params"]["required"].append({
            "name": param,
            "type": "string",
            "description": f"Path parameter: {param}"
        })

    return config


def create_operation_folder(name, config):
    """Create folder and config.yaml for operation."""
    folder = API_INDEX_DIR / name
    folder.mkdir(parents=True, exist_ok=True)

    config_file = folder / "config.yaml"
    config_file.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))

    return folder


def check_api_versions():
    """Check for API version updates."""
    print("\nChecking API versions...")

    for version, urls in API_SOURCES.items():
        print(f"\n{version}:")
        print(f"  Docs: {urls['docs']}")
        print(f"  Postman: {urls['postman']}")

        try:
            r = requests.head(urls['postman'], timeout=10)
            if r.status_code == 200:
                last_modified = r.headers.get('Last-Modified', 'Unknown')
                print(f"  Last Modified: {last_modified}")
            else:
                print(f"  Status: {r.status_code}")
        except Exception as e:
            print(f"  Error: {e}")


def run_analysis(quiet=False):
    """Run user story analysis after refresh."""
    analyze_script = SKILL_DIR / "analyze_userstories.py"
    if analyze_script.exists():
        import subprocess
        args = ["python", str(analyze_script)]
        if quiet:
            args.append("--quiet")
        subprocess.run(args)
        return True
    return False


def main():
    apply_changes = "--apply" in sys.argv
    check_versions = "--check-versions" in sys.argv
    analyze_only = "--analyze" in sys.argv
    no_analyze = "--no-analyze" in sys.argv

    print("=" * 60)
    print("  Wiki API Spec Refresh")
    print("=" * 60)
    print()

    # Just run analysis
    if analyze_only:
        run_analysis()
        return

    if check_versions:
        check_api_versions()
        return

    # Fetch v1 spec (primary API used by wiki-lite)
    spec = fetch_postman_collection("v1")
    if not spec:
        print("Failed to fetch API spec")
        # Try cache
        if CACHE_FILE.exists():
            print(f"Using cached spec from {CACHE_FILE.name}")
            spec = json.loads(CACHE_FILE.read_text())
        else:
            sys.exit(1)
    else:
        # Cache it
        CACHE_FILE.write_text(json.dumps(spec, indent=2))

    # Parse operations
    operations = parse_postman_collection(spec)
    print(f"Found {len(operations)} operations in Postman collection")
    print()

    # Get existing
    existing = get_existing_operations()
    existing_endpoints = set(existing.values())
    print(f"Found {len(existing)} operations in api_index/")
    print()

    # Normalize for comparison
    existing_normalized = {normalize_endpoint(ep) for ep in existing_endpoints if ep}
    spec_endpoints = {normalize_endpoint(op["path"]) for op in operations}

    # Find new operations
    new_ops = []
    for op in operations:
        normalized = normalize_endpoint(op["path"])
        if normalized not in existing_normalized:
            name = path_to_name(op["method"], op["path"])
            if name:  # Skip empty names
                new_ops.append((name, op))

    # Find deprecated
    deprecated = []
    for name, endpoint in existing.items():
        if endpoint and normalize_endpoint(endpoint) not in spec_endpoints:
            deprecated.append((name, endpoint))

    print("-" * 60)
    print(f"NEW operations: {len(new_ops)}")
    for name, op in new_ops[:20]:
        print(f"  + {name}: {op['method']} {op['path']}")
    if len(new_ops) > 20:
        print(f"  ... and {len(new_ops) - 20} more")
    print()

    print(f"DEPRECATED (local only): {len(deprecated)}")
    for name, endpoint in deprecated[:10]:
        print(f"  - {name}: {endpoint}")
    if len(deprecated) > 10:
        print(f"  ... and {len(deprecated) - 10} more")
    print()

    if apply_changes and new_ops:
        print("-" * 60)
        print("Creating configs for new operations...")
        created = 0
        for name, op in new_ops:
            try:
                config = generate_yaml_config(op)
                folder = create_operation_folder(name, config)
                print(f"  Created: {folder.name}/")
                created += 1
            except Exception as e:
                print(f"  Error creating {name}: {e}")

        print()
        print(f"Created {created} new operation configs")

        # Auto-run analysis after apply (unless --no-analyze)
        if not no_analyze:
            print()
            print("-" * 60)
            run_analysis()
    elif new_ops:
        print("Run with --apply to create configs for new operations")

    print()
    print(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
