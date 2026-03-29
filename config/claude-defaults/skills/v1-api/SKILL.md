---

name: v1-api
description: Query Vision One APIs directly. Use when user asks about V1, Vision One, alerts, endpoints, threats, blocklist, or security data.
keywords:
  - alerts
  - endpoint
  - logs
---

# Vision One API Skill

Query V1 APIs directly without MCP server overhead.

## Usage

User says: "list alerts", "search endpoint logs", "block this IP", "V1 status", etc.

## First-Time Setup

```bash
python setup.py
```

This prompts for:
- Vision One region (US, EU, JP, etc.)
- API key (from V1 Console > Administration > API Keys)

## How to Use

1. **Find the right API** - Read `api_reference.md` or run `python executor.py --list`
2. **Run the query** - Execute `python executor.py {operation} [params]`

## Quick Reference

```bash
# List operations
python executor.py --list

# List alerts from last 7 days
python executor.py list_alerts days=7 severity=critical limit=10

# Search endpoint logs
python executor.py search_endpoint_logs hours=24 filter="processName:powershell*"

# List OAT detections
python executor.py list_oat days=7 limit=10

# Block an IP
python executor.py add_to_blocklist ioc_type=ip value=192.168.1.100
```

## Folder Structure

```
v1-api/
├── SKILL.md           # This file
├── setup.py           # First-time setup wizard
├── executor.py        # Runs API calls (standalone, no deps except requests/yaml)
├── .env               # V1_API_KEY, V1_REGION (created by setup.py)
├── api_reference.md   # Find the right API by use case
└── api_index/         # YAML configs per operation (74 operations)
    ├── list_alerts/config.yaml
    ├── search_endpoint_logs/config.yaml
    └── ...
```

## Common Operations

| Task | Operation | Key Params |
|------|-----------|------------|
| List alerts | `list_alerts` | days, severity, status, limit |
| List OAT | `list_oat` | days, limit |
| Search endpoint logs | `search_endpoint_logs` | hours, filter |
| Search network logs | `search_network_logs` | hours, filter |
| Block IOC | `add_to_blocklist` | ioc_type, value |
| List endpoints | `list_endpoints` | limit |
| Get high-risk users | `list_high_risk_users` | risk_score, limit |

## API Key Permissions

For full access, create an API key with:
- Workbench (View, Filter)
- Attack Surface Risk Management (View)
- Observed Attack Techniques (View)
- Response Management (View, Filter, Run response actions)

For full API list, read `api_reference.md`.
