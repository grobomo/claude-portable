---

name: v1-oat-report
description: Generate V1 OAT detection report as styled HTML. Queries Vision One, groups by filter name, writes report to reports/ and opens in browser.
triggers:
  - oat report
  - oat detections
  - noteworthy oats
  - observed attack techniques
  - oat summary
keywords:
  - oat
  - detections
  - observed
  - attack
  - techniques
  - v1

---

# V1 OAT Report Skill

Generate a styled HTML report of Vision One Observed Attack Techniques (OAT) detections.

## When to Use

User asks about OAT detections, OAT report, noteworthy OATs, or observed attack techniques.

## Workflow

### Step 1: Query V1 API

Use the v1-api skill's executor.py to fetch OAT data. Default: last 14 days, medium+ risk.

```bash
cd .claude/skills/v1-api
python executor.py list_oat days=DAYS risk_level=medium limit=50
```

If the user specifies a time range, adjust `days=` accordingly.
If no risk filter specified, default to `risk_level=medium` (medium+ only).

### Step 2: Summarize with Python

Parse the JSON output and group by filter name. Extract per-group:
- count (number of hits)
- riskLevel
- description
- MITRE tactic IDs and technique IDs
- endpoint names (from entityName)
- users (from detail.suid or detail.principalName)
- notable URLs (from highlightedObjects where type=url)
- latest detectedDateTime
- source (endpointActivityData, networkActivityData, detections)
- action taken (from detail.act)
- product name (from detail.pname)
- policy info (from detail.policyName, detail.profile, detail.policyTemplate)

Use this Python snippet to summarize:

```python
import json, sys
from collections import defaultdict

data = json.loads(raw_output)
items = data.get('items', [])

summary = defaultdict(lambda: {
    'count': 0, 'risk': '', 'endpoints': set(), 'tactics': set(),
    'techniques': set(), 'desc': '', 'latest': '', 'source': '',
    'highlights': [], 'users': set(), 'urls': set(),
    'actions': set(), 'products': set(), 'policies': set()
})

for item in items:
    for f in item.get('filters', []):
        key = f['name']
        s = summary[key]
        s['count'] += 1
        s['risk'] = f.get('riskLevel', '')
        s['desc'] = f.get('description', '')
        s['tactics'].update(f.get('mitreTacticIds', []))
        s['techniques'].update(f.get('mitreTechniqueIds', []))
        s['source'] = item.get('source', '')
        ep = item.get('entityName', '')
        if ep: s['endpoints'].add(ep)
        dt = item.get('detectedDateTime', '')
        if dt > s['latest']: s['latest'] = dt
        d = item.get('detail', {})
        user = d.get('suid') or d.get('principalName') or ''
        if isinstance(user, str) and user: s['users'].add(user)
        act = d.get('act', '')
        if act:
            if isinstance(act, list): act = ', '.join(act)
            s['actions'].add(act)
        pname = d.get('pname', '')
        if pname: s['products'].add(pname)
        profile = d.get('profile', '')
        if profile: s['policies'].add(profile)
        for h in f.get('highlightedObjects', []):
            val = h.get('value', '')
            if isinstance(val, list): val = ', '.join(val)
            if val and h.get('type') == 'url': s['urls'].add(val)
```

### Step 3: Generate HTML Report

Write the report to `reports/oat-detections-YYYY-MM-DD.html` using the exact template below.

**Risk level tag CSS classes:**
- critical: `background: #f8d7da; color: #721c24;`
- high: `background: #f5c6cb; color: #721c24;`
- medium: `background: #fff3cd; color: #856404;`
- low: `background: #d4edda; color: #155724;`

#### HTML Template

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>V1 OAT Detections - DATE_RANGE</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; background: #f8f9fa; color: #1a1a2e; }
  h1 { border-bottom: 3px solid #e94560; padding-bottom: 10px; }
  h2 { color: #0f3460; margin-top: 30px; }
  h3 { color: #16213e; }
  .chat { margin: 20px 0; }
  .msg { padding: 14px 18px; margin: 10px 0; border-radius: 10px; line-height: 1.6; }
  .user { background: #e3f2fd; border-left: 4px solid #1976d2; }
  .user::before { content: "User"; font-weight: 700; color: #1976d2; display: block; margin-bottom: 4px; font-size: 0.85em; text-transform: uppercase; }
  .assistant { background: #fff; border-left: 4px solid #e94560; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  .assistant::before { content: "Claude"; font-weight: 700; color: #e94560; display: block; margin-bottom: 4px; font-size: 0.85em; text-transform: uppercase; }
  table { border-collapse: collapse; width: 100%; margin: 12px 0; }
  th, td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }
  th { background: #0f3460; color: #fff; }
  tr:nth-child(even) { background: #f2f2f2; }
  code { background: #e8e8e8; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }
  .meta { color: #666; font-size: 0.85em; margin-top: 30px; border-top: 1px solid #ddd; padding-top: 10px; }
  .tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; font-weight: 600; margin: 0 2px; }
  .tag.critical { background: #f8d7da; color: #721c24; }
  .tag.high { background: #f5c6cb; color: #721c24; }
  .tag.medium { background: #fff3cd; color: #856404; }
  .tag.low { background: #d4edda; color: #155724; }
</style>
</head>
<body>

<h1>V1 OAT Detections Report</h1>
<p>Query: Noteworthy Observed Attack Techniques, DATE_RANGE</p>

<div class="chat">

<div class="msg user">
USER_PROMPT_HERE
</div>

<div class="msg assistant">
<h2>V1 OAT Detections (DATE_RANGE)</h2>

<p><strong>Total OATs:</strong> TOTAL_COUNT (all risk levels) | <strong>Medium+ risk:</strong> FILTERED_COUNT</p>

<h3>Noteworthy Detections</h3>

<!-- TABLE: one row per unique filter name, sorted by risk desc then count desc -->
<table>
  <tr><th>Filter</th><th>Risk</th><th>Hits</th><th>MITRE</th><th>Endpoint</th></tr>
  <!-- ROWS HERE -->
</table>

<h3>Key Details</h3>
<ul>
  <!-- Per-group details as bullet points -->
  <li><strong>User:</strong> USER_LIST</li>
  <li><strong>Source endpoint:</strong> ENDPOINT (OS, IP) -- context note</li>
  <li><strong>Action taken:</strong> ACTION</li>
  <li><strong>Policy:</strong> POLICY_INFO</li>
  <li><strong>Triggered URLs:</strong>
    <ul>
      <li>URL_1</li>
      <li>URL_2</li>
    </ul>
  </li>
  <li><strong>Product:</strong> PRODUCT_NAME</li>
  <li><strong>Latest detection:</strong> DATETIME</li>
</ul>

<h3>Assessment</h3>
<p>ASSESSMENT_PARAGRAPH -- classify as expected lab activity, genuine concern, or needs investigation. Reference the specific DLP/detection policy and explain WHY it triggered.</p>
</div>

</div>

<div class="meta">
  Generated by Claude Code | Session: TODAY_DATE | Source: Vision One API (<code>list_oat</code> via v1-api skill)
</div>

</body>
</html>
```

### Step 4: Open in Browser

```bash
start "" "reports/oat-detections-YYYY-MM-DD.html"
```

### Step 5: Show Summary in Chat

After generating the HTML, also show a brief text summary in the chat:
- Total OATs (all risk levels) and filtered count
- Table of unique filter names with risk, hits, MITRE, endpoints
- One-line assessment

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| days | 14 | How many days back to query |
| risk_level | medium | Minimum risk level (low, medium, high, critical) |

## Notes

- The v1-api executor handles pagination automatically
- For large result sets (1000+), always filter by risk_level to avoid timeout
- The "all risk levels" total count comes from a separate unfiltered query: `python executor.py list_oat days=DAYS limit=1` (just to get totalCount)
- Assessment section is AI-generated based on the data -- identify lab noise vs genuine threats
