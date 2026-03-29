---

name: v1-report
description: Generate styled HTML reports from Vision One API data. Supports container security, endpoint, ZTSA, OAT, and custom XDR search reports.
triggers:
  - v1 report
  - container security report
  - container report
  - endpoint report
  - vulnerability report
  - v1 security report
  - xdr report
  - generate v1 report
keywords:
  - v1
  - report
  - container
  - security
  - vulnerability
  - endpoint
  - xdr
  - html

---

# V1 Report Skill

Generate styled HTML reports from Vision One API data. Covers multiple V1 products with consistent formatting.

## When to Use

User asks for a V1 report, container security report, vulnerability report, endpoint report, or any report that pulls data from Vision One APIs.

## Report Types

| Type | API Endpoints | Trigger |
|------|--------------|---------|
| Container Security | `/v3.0/containerSecurity/kubernetesClusters`, `/v3.0/containerSecurity/vulnerabilities` | "container report", "cs report" |
| OAT Detections | v1-api skill `list_oat` | "oat report" (defer to v1-oat-report skill) |
| Endpoint Inventory | `/v3.0/eicar/endpoints` | "endpoint report" |
| Workbench Alerts | `/v3.0/workbench/alerts` | "alert report", "workbench report" |
| Custom XDR Search | `/v2.0/xdr/search/data` | "xdr report" + user query |

## Workflow

### Step 1: Determine Report Type

Parse user request to identify which V1 product/data they want. If unclear, default to container security.

### Step 2: Get V1 API Token

```python
import keyring
TOKEN = keyring.get_password('claude-code', 'v1-lite/V1_API_KEY')
BASE = 'https://api.xdr.trendmicro.com'
HEADERS = {'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json;charset=utf-8'}
```

### Step 3: Query V1 APIs

#### Container Security
```python
import requests

# Clusters
clusters = requests.get(f'{BASE}/v3.0/containerSecurity/kubernetesClusters', headers=HEADERS).json().get('items', [])

# Vulnerabilities (limit param, not top)
vulns = requests.get(f'{BASE}/v3.0/containerSecurity/vulnerabilities?limit=200', headers=HEADERS).json().get('items', [])
```

#### Workbench Alerts
```python
alerts = requests.get(f'{BASE}/v3.0/workbench/alerts', headers=HEADERS,
    params={'top': 50, 'orderBy': 'createdDateTime desc'}).json().get('items', [])
```

### Step 4: Generate HTML Report

Write to `reports/<report-name>.html` using the standard template below.

**Output location:** Always write to the project's `reports/` folder. Use naming pattern: `<type>-report-YYYY-MM-DD.html`

### Step 5: Open and Verify

```bash
start "" "reports/<filename>.html"
```

Always take a screenshot and visually verify the report layout before telling the user it's done.

## HTML Template

Use this base CSS for ALL report types (matches existing reports in reports/ folder):

```css
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 960px; margin: 40px auto; padding: 0 20px; background: #f8f9fa; color: #1a1a2e; }
h1 { border-bottom: 3px solid #e94560; padding-bottom: 10px; }
h2 { color: #0f3460; margin-top: 30px; border-bottom: 1px solid #ddd; padding-bottom: 5px; }
h3 { color: #16213e; margin-top: 20px; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; }
th, td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; font-size: 0.9em; }
th { background: #0f3460; color: #fff; }
tr:nth-child(even) { background: #f2f2f2; }
code { background: #e8e8e8; padding: 2px 6px; border-radius: 3px; font-size: 0.85em; }
.meta { color: #666; font-size: 0.85em; margin-top: 30px; border-top: 1px solid #ddd; padding-top: 10px; }
.tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; font-weight: 600; margin: 0 2px; }
.tag.critical { background: #f8d7da; color: #721c24; }
.tag.high { background: #f8d7da; color: #721c24; }
.tag.medium { background: #fff3cd; color: #856404; }
.tag.low { background: #d4edda; color: #155724; }
.tag.healthy { background: #d4edda; color: #155724; }
.status-box { background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin: 12px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.kv { margin: 4px 0; }
.kv strong { color: #0f3460; }
.step { background: #fff; border-left: 4px solid #0f3460; padding: 12px 16px; margin: 10px 0; border-radius: 0 8px 8px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.step h4 { margin: 0 0 8px 0; color: #0f3460; }
.note { background: #e3f2fd; border-left: 4px solid #1976d2; padding: 10px 14px; margin: 10px 0; border-radius: 0 6px 6px 0; }
.warn { background: #fff3cd; border-left: 4px solid #ffc107; padding: 10px 14px; margin: 10px 0; border-radius: 0 6px 6px 0; }
```

## Report Sections (Container Security)

Every container security report MUST include these sections:

1. **Cluster Overview** - name, orchestrator, version, protection status, node/pod counts, protection modules table
2. **Vulnerability Scan Results** - severity summary + CVE table (CVE, severity tag, CVSS, package, version, image)
3. **Runtime Security Events** - table of test actions with commands, expected detections, MITRE ATT&CK mappings
4. **Image Scan Summary** - auto-scan results (vuln/malware/secret)
5. **XDR Search Queries** - ready-to-use queries for Agentic SIEM and XDR > Search
6. **Save Search as Detection Rule** - step-by-step: run query, save as detection model, add to saved searches
7. **Configure Alert Notifications** - step-by-step: set up email channel, create automation rule, verify flow
8. **Deployment Summary** - environment details table

## Report Sections (Generic)

For non-container reports, adapt sections to fit the data:

1. **Summary** - key metrics, counts, severity breakdown
2. **Data Table** - main results table with severity tags
3. **XDR Search Queries** - relevant search queries
4. **Next Steps** - actionable recommendations with step-by-step guides
5. **Metadata** - generation time, API source, IDs

## Severity Tag Colors

| Severity | CSS Class |
|----------|-----------|
| Critical | `.tag.critical` - red background |
| High | `.tag.high` - red background |
| Medium | `.tag.medium` - yellow background |
| Low | `.tag.low` - green background |
| Healthy/Enabled | `.tag.healthy` - green background |

## V1 API Notes

- Container vulnerabilities use `limit=` param (not `top=`)
- Workbench alerts use `top=` param
- Container cluster API returns nested nodes[].pods[] structure
- Runtime security event APIs may return 404 — use the V1 console Log tab via browser automation as fallback
- Always use `keyring.get_password('claude-code', 'v1-lite/V1_API_KEY')` for the token

## Reference Report

See `reports/container-security-report.html` for the canonical container security report format.
See `reports/oat-detections-2026-02-25.html` for the canonical OAT report format.
