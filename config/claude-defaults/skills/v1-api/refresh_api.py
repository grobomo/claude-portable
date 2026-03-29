#!/usr/bin/env python3
"""
V1 API Spec Refresh

Fetches the official Vision One OpenAPI spec and compares to local api_index.
Generates YAML configs for any new operations.

Usage:
    python refresh_api.py           # Show diff only
    python refresh_api.py --apply   # Create configs for new operations
"""

import os
import sys
import json
import yaml
import requests
from pathlib import Path
from datetime import datetime

SKILL_DIR = Path(__file__).parent
API_INDEX_DIR = SKILL_DIR / "api_index"
OPENAPI_URL = "https://automation.trendmicro.com/sp-api-open-v3.0.json"
CACHE_FILE = SKILL_DIR / ".api_spec_cache.json"

# Template mapping from OpenAPI to our templates
METHOD_TEMPLATE_MAP = {
    ("GET", True): "standard_list",   # GET with pagination = list
    ("GET", False): "single_get",      # GET without pagination
    ("POST", "search"): "search",      # POST for search endpoints
    ("POST", "action"): "response_action",  # POST for response actions
    ("POST", "default"): "post_action",
    ("PATCH", True): "patch_update",
    ("DELETE", True): "post_action",
}


def fetch_openapi_spec():
    """Fetch OpenAPI spec from official docs."""
    print(f"Fetching OpenAPI spec from {OPENAPI_URL}...")
    try:
        r = requests.get(OPENAPI_URL, timeout=30)
        r.raise_for_status()
        spec = r.json()

        # Cache it
        CACHE_FILE.write_text(json.dumps(spec, indent=2))
        print(f"  Cached to {CACHE_FILE.name}")
        return spec
    except Exception as e:
        print(f"  Error: {e}")

        # Try cache
        if CACHE_FILE.exists():
            print(f"  Using cached spec from {CACHE_FILE.name}")
            return json.loads(CACHE_FILE.read_text())
        return None


def parse_operations(spec):
    """Parse OpenAPI spec into operation list."""
    operations = []

    paths = spec.get("paths", {})
    for path, methods in paths.items():
        for method, details in methods.items():
            if method.upper() not in ("GET", "POST", "PATCH", "PUT", "DELETE"):
                continue

            op = {
                "operation_id": details.get("operationId", ""),
                "method": method.upper(),
                "path": path,
                "summary": details.get("summary", ""),
                "description": details.get("description", ""),
                "tags": details.get("tags", []),
                "parameters": details.get("parameters", []),
                "request_body": details.get("requestBody"),
            }

            # Determine template type
            has_pagination = any(
                p.get("name") in ("top", "skip", "nextLink")
                for p in op["parameters"]
            )

            if op["method"] == "GET":
                op["template"] = "standard_list" if has_pagination else "single_get"
            elif op["method"] == "POST":
                if "search" in path.lower():
                    op["template"] = "search"
                elif any(x in path.lower() for x in ["response", "isolate", "restore", "terminate", "collect"]):
                    op["template"] = "response_action"
                else:
                    op["template"] = "post_action"
            else:
                op["template"] = "patch_update"

            operations.append(op)

    return operations


def path_to_name(method, path):
    """Convert API path to snake_case operation name."""
    import re

    # Remove version prefix
    clean_path = re.sub(r'^/v\d+\.\d+/', '', path)

    # Check if path ends with {id} parameter (single item vs list)
    is_single = clean_path.endswith('}')

    # Remove path parameters like {id}, {alertId}
    clean_path = re.sub(r'/\{[^}]+\}', '', clean_path)

    # Split by / and filter empty
    parts = [p for p in clean_path.split('/') if p]

    if not parts:
        return ""

    # Convert camelCase to snake_case for each part
    snake_parts = []
    for p in parts:
        p = re.sub(r'(?<!^)(?=[A-Z])', '_', p).lower()
        # Common substitutions
        p = p.replace('activities', 'logs')
        p = p.replace('endpoints', 'endpoint')
        snake_parts.append(p)

    # Build name based on method
    if method == "GET":
        if is_single:
            prefix = "get"
        else:
            prefix = "list"
    elif method == "POST":
        if "search" in clean_path.lower():
            prefix = "search"
        elif any(x in clean_path.lower() for x in ["delete", "remove"]):
            prefix = "delete"
        else:
            prefix = ""  # Use path verb
    elif method == "PATCH":
        prefix = "update"
    elif method == "DELETE":
        prefix = "delete"
    else:
        prefix = method.lower()

    # Join parts, avoiding duplicate words
    name_parts = []
    if prefix and prefix not in snake_parts[0]:
        name_parts.append(prefix)
    name_parts.extend(snake_parts)

    name = '_'.join(name_parts)

    # Clean up
    name = re.sub(r'[^a-z0-9_]', '_', name)
    name = re.sub(r'_+', '_', name)
    return name.strip('_')


def get_existing_operations():
    """Get existing operations with their endpoints."""
    existing = {}  # name -> endpoint
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


def generate_yaml_config(op):
    """Generate YAML config for an operation."""
    name = path_to_name(op["method"], op["path"])

    # Build params
    required_params = []
    optional_params = []

    for param in op["parameters"]:
        p = {
            "name": param.get("name"),
            "type": param.get("schema", {}).get("type", "string"),
            "description": param.get("description", ""),
        }
        if param.get("required"):
            required_params.append(p)
        else:
            optional_params.append(p)

    config = {
        "name": name,
        "description": op["summary"] or op["description"],
        "method": op["method"],
        "endpoint": op["path"],
        "template": op["template"],
        "tags": op["tags"],
        "params": {
            "required": required_params,
            "optional": optional_params,
        },
        "template_config": {},
    }

    # Add date params for list/search endpoints
    if op["template"] in ("standard_list", "search"):
        date_params = [p for p in op["parameters"] if "time" in p.get("name", "").lower() or "date" in p.get("name", "").lower()]
        if date_params:
            start = next((p["name"] for p in date_params if "start" in p["name"].lower()), None)
            end = next((p["name"] for p in date_params if "end" in p["name"].lower()), None)
            if start and end:
                config["template_config"]["date_params"] = {
                    "start": start,
                    "end": end,
                    "unit": "days",
                }

    # Add pagination for list endpoints
    if op["template"] == "standard_list":
        top_param = next((p for p in op["parameters"] if p.get("name") == "top"), None)
        if top_param:
            config["template_config"]["pagination"] = {
                "param": "top",
                "type": "int",
                "max": 200,
            }

    return config


def create_operation_folder(name, config):
    """Create folder and config.yaml for operation."""
    folder = API_INDEX_DIR / name
    folder.mkdir(exist_ok=True)

    config_file = folder / "config.yaml"
    config_file.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))

    # Create example files
    example_py = folder / "example_api_call.py"
    example_py.write_text(f'''#!/usr/bin/env python3
"""Example API call for {name}"""

import requests

# TODO: Add working example
# See executor.py for how this operation is called
''')

    example_json = folder / "example_api_response.json"
    example_json.write_text('{\n  "TODO": "Add actual response sample"\n}\n')

    return folder


def main():
    apply_changes = "--apply" in sys.argv

    print("=" * 60)
    print("  V1 API Spec Refresh")
    print("=" * 60)
    print()

    # Fetch spec
    spec = fetch_openapi_spec()
    if not spec:
        print("Failed to fetch OpenAPI spec")
        sys.exit(1)

    # Parse operations
    operations = parse_operations(spec)
    print(f"Found {len(operations)} operations in OpenAPI spec")
    print()

    # Get existing - dict of name -> endpoint
    existing = get_existing_operations()
    existing_endpoints = set(existing.values())
    print(f"Found {len(existing)} operations in api_index/")
    print()

    # Normalize endpoint for comparison (remove path params)
    import re
    def normalize_endpoint(ep):
        return re.sub(r'/\{[^}]+\}', '/{id}', ep)

    existing_normalized = {normalize_endpoint(ep) for ep in existing_endpoints if ep}
    spec_endpoints = {normalize_endpoint(op["path"]) for op in operations}

    # Find new operations (in spec but not in local)
    new_ops = []
    for op in operations:
        normalized = normalize_endpoint(op["path"])
        if normalized not in existing_normalized:
            name = path_to_name(op["method"], op["path"])
            new_ops.append((name, op))

    # Find deprecated (in local but not in spec)
    deprecated = []
    for name, endpoint in existing.items():
        if endpoint and normalize_endpoint(endpoint) not in spec_endpoints:
            deprecated.append((name, endpoint))

    print("-" * 60)
    print(f"NEW operations: {len(new_ops)}")
    for name, op in new_ops[:20]:  # Show first 20
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
        print("Review and test the new configs before using")
    elif new_ops:
        print("Run with --apply to create configs for new operations")

    print()
    print(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
