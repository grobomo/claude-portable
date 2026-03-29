# Detection Model Reference

Centralized reference for XDR detection models, custom filters, and exceptions.
Detection models power the Workbench alerts and OAT (Observed Attack Techniques).

## Console Navigation

```
V1 Console > XDR Threat Investigation > Detection Model Management (left sidebar)
```

| Page | Path | Purpose |
|------|------|---------|
| Detection Models | XDR Threat Investigation > Detection Model Management | Enable/disable models |
| Custom Filters | XDR Threat Investigation > Search > Custom Filters | Saved detection queries |
| Exceptions | XDR Threat Investigation > Exception List | Suppress false positives |

## Model Types

| Type | Code | Source | Count |
|------|------|--------|-------|
| Threat Intelligence | TI | ti-0001 | 1 (always enabled) |
| Search & Analytics Engine | SAE | sae-* | 500+ (auto-updated by Trend) |

### SAE Model Categories (from lab data)

| MITRE Technique | Example Model | Risk |
|----------------|--------------|------|
| T1059.003 (Command/Scripting) | CMD Execution via Nslookup DNS Response | High |
| Various | SSH Shell Command Is Detected | Low |
| Various | MIME Header Detected To Have A Virus | Low |
| Various | Botnet C&C Communication | Low |

Models reference `requiredProducts` -- they only fire if the matching product sends data:
- `sao` = Standard Endpoint Protection (Apex One)
- `sds` = Server & Workload Protection (Deep Security)
- `xes` = XDR Endpoint Sensor
- `tlc` = Third-party Log Collector (e.g., Fortinet, Palo Alto)

## Current Exceptions (joeltest.org, 2026-03-02)

| ID | Description | Criteria | Scope |
|----|-------------|----------|-------|
| EXC.R00003 | IT team admin false positives | logonUser=Administrator | Demo - Possible Credential Dumping |
| EXC.R00002 | Trend test exclusion | (check API) | (check API) |

## V1 API Operations

| Operation | Purpose |
|-----------|---------|
| `list_dmm_models` | List all detection models with enable status |
| `list_dmm_exceptions` | List all custom exceptions |
| `get_dmm_exceptions` | Get single exception details |
| `dmm_exceptions` | Create new exception |
| `delete_dmm_exceptions_delete` | Delete an exception |
| `list_dmm_custom_filters` | List saved custom detection filters |
| `list_dmm_custom_models` | List custom (user-created) detection models |

## Exception Anatomy

Each exception has:
- **criteria**: What to match (fieldType, fieldName, fieldValues, matchType)
- **scope**: Which model/filter to apply the exception to
- **targetEntities**: Optional entity-level targeting
- **enable**: Active or inactive

```json
{
  "criteria": [
    {
      "fieldType": "user_account",
      "fieldName": "logonUser",
      "fieldValues": ["Administrator"],
      "matchType": "EXACT"
    }
  ],
  "scope": {
    "filters": [
      {
        "filterId": "687db884-...",
        "filterName": "Demo - Possible Credential Dumping via Registry Hive"
      }
    ]
  }
}
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Model shows "not available" | Required product not connected (check requiredProducts) |
| Too many false positive alerts | Create exception for the specific model/filter |
| Custom filter not triggering | Check query syntax and data source availability |
| Model disabled unexpectedly | Check if Trend auto-disabled due to product removal |
