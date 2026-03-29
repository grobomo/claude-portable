---

name: v1-policy
description: >
  Manage all Vision One product policies via API + browser automation. Covers 12 modules:
  email (CECP/CEGP), endpoint (SEP/SWP), ZTSA, network, identity, data security, AI security,
  mobile, container, detection models, response, and cloud accounts.
  Uses v1-api for operations with API coverage, Blueprint MCP for browser-only operations.
  See API-GAP-ANALYSIS.md for complete API vs browser coverage map.
keywords:
  - policy
  - cecp
  - cegp
  - anti-spam
  - anti-malware
  - dlp
  - ztsa
  - ips
  - email
  - loss
  - prevention
  - web
  - reputation
  - virtual
  - analyzer
  - content
  - filtering
  - endpoint
  - protection
  - security
  - assign
  - container
  - detection
  - model
  - sensor
  - zero
  - trust
  - secure
  - access
  - network
  - patch
  - intrusion
  - identity
  - posture
  - classification
  - ai
  - guardrail
  - mobile

---

# V1 Policy Management Skill

Manage Vision One product policies through API calls and browser automation. Some V1 modules
have full API CRUD (container, detection, response). Others have zero API coverage and require
console interaction via Blueprint (ZTSA, network, data security, mobile, AI security).
See API-GAP-ANALYSIS.md for the complete coverage map ranked by priority.

## Configuration

Settings are in `config.yaml` next to this file. Users can customize:

| Setting | Default | Options |
|---------|---------|---------|
| `browser_mode` | `incognito` | `incognito` or `normal` |
| `console_url` | `https://portal.xdr.trendmicro.com` | Any V1 portal URL |

**Incognito mode** (default) prevents session conflicts when the user's primary browser is
logged into a different V1 account. To use incognito mode, Blueprint must be enabled for
incognito in Chrome: `chrome://extensions` > Blueprint > "Allow in Incognito".

Read config before starting:
```bash
cat .claude/skills/v1-policy/config.yaml
```

## Prerequisites

Before any policy workflow:

1. **Read `config.yaml`** to check browser_mode setting
2. **Blueprint MCP running** -- `mcpm start blueprint` (Chrome extension must be active)
3. **If incognito mode:** Blueprint must have "Allow in Incognito" enabled in chrome://extensions
4. **V1 console open** -- in incognito or normal per config:
   - Incognito: `start "" "chrome" "--incognito" "https://portal.xdr.trendmicro.com"`
   - Normal: open in any Chrome tab
5. **V1 API available** -- for read-only data (account lists, policy status)

## Product Router

| User Intent | Module | API Coverage | Dependencies |
|-------------|--------|-------------|--------------|
| Email sensor / CECP / CEGP | [modules/email/](modules/email/) | 30% (inventory read) | Blueprint, v1-api, trend-docs |
| Endpoint sensor policy / SEP / SWP | [modules/endpoint/](modules/endpoint/) | 20% (override only) | Blueprint, v1-api |
| Container security / K8s / ECS | [modules/container/](modules/container/) | 100% (full CRUD) | v1-api |
| Detection models / OAT filters | [modules/detection/](modules/detection/) | 90% (full CRUD) | v1-api |
| Suspicious objects / blocklist | [modules/response/](modules/response/) | 90% (full CRUD) | v1-api |
| Cloud accounts / AWS / Azure / GCP | [modules/cloud/](modules/cloud/) | 85% (onboard/status) | v1-api |
| ZTSA / access policy / zero trust | [modules/ztsa/](modules/ztsa/) | 5% (logs only) | Blueprint, v1-api |
| Network security / IPS / virtual patch | [modules/network/](modules/network/) | 5% (public IPs only) | Blueprint |
| Identity security / posture | [modules/identity/](modules/identity/) | 15% (response actions) | Blueprint, v1-api |
| Data security / DLP | [modules/data-security/](modules/data-security/) | 0% (nothing) | Blueprint |
| AI security / guardrails | [modules/ai-security/](modules/ai-security/) | 5% (eval only) | Blueprint, v1-api |
| Mobile security / MDM | [modules/mobile/](modules/mobile/) | 5% (logs only) | Blueprint, v1-api |

**Full gap analysis:** [API-GAP-ANALYSIS.md](API-GAP-ANALYSIS.md)

### Email Sub-skill Tree

```
v1-policy > email
|
+-- reference.md                # Centralized: navigation, scanner details, API ops, troubleshooting
|
+-- enable-email-sensor.md      # Cross-product: enable CECP inline sensor on EXO
|   Affects both CECP and CEGP visibility in V1
|   Current state: all 6 accounts sensorDetection=Disabled
|
+-- cecp/                       # Cloud Email & Collaboration Protection
|   +-- provision-service.md    # Connect Exchange Online / Gmail / SharePoint
|   +-- create-policy.md        # New threat protection policy (6 scanning modules)
|   +-- assign-policy.md        # Assign policy to accounts/groups
|   +-- audit-status.md         # Check protection status via API
|
+-- cegp/                       # Cloud Email Gateway Protection
    +-- provision-domain.md     # Add domain, configure MX records
    +-- create-dmarc-policy.md  # DMARC/DKIM/SPF authentication
    +-- create-gateway-policy.md # Inbound/outbound scanning rules
    +-- audit-status.md         # Check domain config and detection stats
```


### Endpoint Sub-skill Tree

```
v1-policy > endpoint
|
+-- reference.md                # Sensor policies, version control, agent update
+-- audit-status.md             # Current endpoints, policies, agent versions
+-- apply-sensor-policy.md      # Override sensor policy per endpoint
+-- version-control.md          # Agent update policies (n, n-1, n-2, pinned)
```

### Container Sub-skill Tree

```
v1-policy > container
|
+-- reference.md                # Container Security policies, rulesets, compliance
+-- audit-status.md             # List policies, rulesets, clusters
+-- create-policy.md            # New container security policy (runtime rules)
+-- manage-rulesets.md          # Custom and managed rulesets
```

### Detection Sub-skill Tree

```
v1-policy > detection
|
+-- reference.md                # Detection models, exceptions, custom filters
+-- audit-status.md             # List enabled models, exceptions, custom filters
+-- manage-exceptions.md        # Add/edit/delete detection exceptions
+-- manage-models.md            # Enable/disable detection models
```

### Response Sub-skill Tree

```
v1-policy > response
|
+-- reference.md                # Blocklist, exception list, response settings
+-- audit-status.md             # Current blocklist entries, response settings
+-- manage-blocklist.md         # Add/remove suspicious objects
+-- manage-exceptions.md        # Allow list management
```

### Cloud Sub-skill Tree

```
v1-policy > cloud
|
+-- reference.md                # Connected cloud accounts, features, compliance
+-- audit-status.md             # AWS/Azure/GCP accounts, feature status
+-- connect-aws.md              # Connect AWS account via CloudFormation
+-- connect-azure.md            # Connect Azure subscription
```

### ZTSA Sub-skill Tree (5% API -- browser required)

```
v1-policy > ztsa
|
+-- reference.md                # ZTSA config, SAM, connectors, access rules
+-- audit-status.md             # ZTSA deployment health, SAM status
+-- manage-access-rules.md      # Create/edit/delete access rules (browser)
```

### Network Security Sub-skill Tree (5% API -- browser required)

```
v1-policy > network
|
+-- reference.md                # Network sensors, IPS, virtual patches
+-- audit-status.md             # Sensor health, IPS rule state
```

### Identity Security Sub-skill Tree (15% API -- partial)

```
v1-policy > identity
|
+-- reference.md                # Identity posture, access control, risk indicators
+-- audit-status.md             # Identity source health, risk posture
+-- response-actions.md         # Disable/enable/reset/signout (API available)
```

### Data Security Sub-skill Tree (0% API -- browser only)

```
v1-policy > data-security
|
+-- reference.md                # DLP, data discovery, classification
+-- audit-status.md             # DLP policy state, incidents
```

### AI Security Sub-skill Tree (5% API -- browser required)

```
v1-policy > ai-security
|
+-- reference.md                # AI guardrails, access control, monitoring
+-- audit-status.md             # AI security deployment state
```

### Mobile Security Sub-skill Tree (5% API -- browser required)

```
v1-policy > mobile
|
+-- reference.md                # MDM, threat detection, app management
+-- audit-status.md             # Device enrollment, policy state
```

**Read `modules/<product>/reference.md`** for shared navigation, settings details, API operations,
and troubleshooting. Then read the specific workflow file for step-by-step instructions.

## Blueprint Connection Pattern

```
1. Read config.yaml to determine browser_mode
2. If incognito: find tab with portal.xdr.trendmicro.com in incognito window
   If normal: find tab with portal.xdr.trendmicro.com in any window

3. mcpm call blueprint browser_tabs action='list'
   → Find the V1 console tab (URL contains portal.xdr.trendmicro.com or portal.trendmicro.com)

2. mcpm call blueprint browser_attach tabId=<id>
   → Attach to the V1 tab

3. mcpm call blueprint browser_snapshot
   → Verify we're on V1 console (check for V1 UI elements)

4. If login page detected → run Auth Flow below
```

## V1 Console Auth Flow

**Known limitation:** The V1 sign-in page (signin.v1.trendmicro.com) blocks Blueprint
debugger -- screenshot, evaluate, and interact all fail on this domain. The user must
complete sign-in manually (including MFA). Once the console loads, Blueprint works normally.

## Granular Documentation Lookup

For any feature being configured, get the official docs BEFORE making changes:

### Pattern 1: Known feature (use doc-slugs.yaml)

```bash
# Read the slug map
cat .claude/skills/v1-policy/doc-slugs.yaml

# Fetch the specific doc page
python .claude/skills/trend-docs/executor.py "<slug-from-yaml>" --max-pages 2
```

### Pattern 2: Unknown feature (ask TrendGPT first)

```
mcpm call trendgpt-aatf trendgpt_query query="How to configure <feature> in Vision One CECP?"
```

### Pattern 3: Deep dive (use both)

```
# Get overview from TrendGPT
mcpm call trendgpt-aatf trendgpt_query query="What are the options for <feature>?"

# Then get detailed config from docs
python .claude/skills/trend-docs/executor.py "<slug>" --max-pages 5
```

## V1 API Integration (Read-Only Data)

Use v1-api for data that doesn't require console interaction:

```bash
# Email
python .claude/skills/v1-api/executor.py list_email_asset_inventory_email_accounts
python .claude/skills/v1-api/executor.py list_email_asset_inventory_email_domains
python .claude/skills/v1-api/executor.py search_email_logs hours=24

# Endpoints
python .claude/skills/v1-api/executor.py list_endpoints top=100
python .claude/skills/v1-api/executor.py list_policies                    # Version control

# Container Security (full CRUD via API)
python .claude/skills/v1-api/executor.py list_container_security_policies
python .claude/skills/v1-api/executor.py list_container_security_rulesets
python .claude/skills/v1-api/executor.py list_container_security_managed_rules

# Detection Models
python .claude/skills/v1-api/executor.py list_dmm_models
python .claude/skills/v1-api/executor.py list_dmm_exceptions
python .claude/skills/v1-api/executor.py list_dmm_custom_filters

# Response / Blocklist
python .claude/skills/v1-api/executor.py list_blocklist
python .claude/skills/v1-api/executor.py list_exceptions
python .claude/skills/v1-api/executor.py list_response_setting_status

# Cloud Accounts
python .claude/skills/v1-api/executor.py list_aws_accounts
python .claude/skills/v1-api/executor.py list_azure_accounts
python .claude/skills/v1-api/executor.py list_gcp_accounts
python .claude/skills/v1-api/executor.py list_k8s_clusters

# ZTSA (logs only -- no policy APIs)
python .claude/skills/v1-api/executor.py search_network_logs hours=24 limit=10

# Identity Security (response actions + logs)
python .claude/skills/v1-api/executor.py search_identity_logs hours=24 limit=10
python .claude/skills/v1-api/executor.py list_domain_accounts
python .claude/skills/v1-api/executor.py list_high_risk_users

# AI Security (guardrail evaluation only)
python .claude/skills/v1-api/executor.py ai_security_apply_guardrails messages='[{"role":"user","content":"test"}]'

# Mobile Security (logs only)
python .claude/skills/v1-api/executor.py search_mobile_logs hours=24 limit=10
```

## Blueprint Best Practices for V1 SPA

V1 is a single-page app (SPA). Follow these rules:

1. **Snapshot before every interaction** -- The DOM changes frequently. Always `browser_snapshot` before clicking or typing.
2. **Use `browser_lookup` for text matching** -- V1 uses dynamic class names. Find elements by visible text, not CSS classes.
3. **Wait after navigation** -- After clicking sidebar items, wait 2-3 seconds for SPA routing: `browser_evaluate code="await new Promise(r => setTimeout(r, 3000))"`
4. **Screenshot for visual confirmation** -- Use `browser_take_screenshot` after key actions to verify state.
5. **Never assume element positions** -- Always re-snapshot after page transitions.
6. **Handle loading spinners** -- V1 shows spinners during API calls. Wait for them to disappear before interacting.

## Discovery Protocol

For resilience to V1 UI changes, follow this before any workflow step:

```
1. browser_snapshot → get current DOM state
2. browser_take_screenshot → visual context
3. Compare against expected layout from module file
4. If UI changed:
   a. browser_lookup query="<expected text>" → find element by text
   b. Adapt selectors based on current DOM
   c. Document the change for future reference
5. Proceed with workflow step
```

## Error Recovery

| Error | Recovery |
|-------|----------|
| Blueprint not connected | `mcpm start blueprint`, verify Chrome extension active |
| Can't access incognito tab | Enable Blueprint for incognito: chrome://extensions > Allow in Incognito |
| V1 tab not found | Open V1 per browser_mode setting, re-list tabs |
| Login page blocks Blueprint | User must complete sign-in manually (known limitation) |
| Element not found | Take screenshot, use browser_lookup with text content |
| SPA navigation failed | Click V1 logo to go home, retry navigation |
| API call failed | Check v1-api credentials, try `python .claude/skills/v1-api/executor.py --list` |
