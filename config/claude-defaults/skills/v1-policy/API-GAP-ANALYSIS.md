# V1 API Gap Analysis

Ranked list of missing API coverage compared to V1 console features.
Use this to advocate for "everything needs an API" to product management.

**Methodology:** Every V1 console section mapped against the 280 available API operations.
Ranked by impact: how many users hit this gap, how painful the workaround is.

**Date:** 2026-03-02 | **V1 API version:** v3.0 | **Total operations:** 280

---

## Priority Rankings

```
PRIORITY 1 (Critical)  -- Needed daily, no API at all, browser-only
PRIORITY 2 (High)      -- Needed weekly, partial API, browser for key actions
PRIORITY 3 (Medium)    -- Needed occasionally, workaround exists
PRIORITY 4 (Low)       -- Rare use case or read-only is sufficient
```

---

## PRIORITY 1 -- Critical Missing APIs

### 1. Zero Trust Secure Access (ZTSA) Policy Management

**Console:** Cloud Security > Zero Trust Secure Access > Secure Access Rules / Internet Access / Private Access
**Available APIs:** search_network_logs (read-only log search)
**Missing:**
- Create/read/update/delete access policies
- Manage Secure Access Rules (allow, block, monitor)
- Internet Access Configuration (URL categories, cloud apps)
- Private Access Configuration (internal apps, connectors)
- Private Access Connectors management (deploy, status, health)
- SAM (Secure Access Module) deployment tokens
- ZTSA user/group assignment
- Bandwidth/traffic policies

**Impact:** ZTSA is V1 flagship zero trust product. Every ZTSA deployment requires manual
console work for policy setup. No programmatic way to:
- Provision ZTSA for new offices/users
- Sync access policies from identity providers
- Automate policy changes during incidents
- Export/import policies between environments

**Workaround:** Browser automation via Blueprint (modules/ztsa/)

---

### 2. Endpoint Security Policy CRUD

**Console:** Endpoint Security > Endpoint Security Policies > Policies tab
**Available APIs:** endpoint_security_endpoint_apply_sensor_policy (override only), list_endpoints, list_policies (version control only), endpoint version control CRUD
**Missing:**
- Create new endpoint security policies
- Read/export full policy configuration (scan settings, exclusions, firewall rules)
- Update policy settings (enable/disable modules, change scan schedules)
- Delete policies
- Clone/duplicate policies
- Policy assignment to groups (only per-endpoint override exists)
- Standard Endpoint Protection (SEP) policy management
- Server & Workload Protection (SWP) policy management
- Endpoint sensor settings (behavioral monitoring, machine learning, web reputation)
- Firewall rule management
- Application control rules
- Vulnerability protection rules

**Impact:** Every V1 endpoint deployment needs policies configured. The existing API only
lets you override sensor policy per-endpoint -- you cannot create or manage the actual
policy objects. This means:
- No Infrastructure-as-Code for endpoint policies
- No bulk policy changes across 1000s of endpoints
- No automated policy testing/rollback
- Migration between V1 tenants requires manual recreation

**Workaround:** Browser automation for SEP/SWP policy management (modules/endpoint/)

---

### 3. Email Security Policy CRUD (CECP & CEGP)

**Console:** Email & Collaboration Security > Cloud Email & Collaboration Protection > Policies
**Available APIs:** list_email_asset_inventory_* (read-only inventory), search_email_logs, quarantine_email, delete_email, restore_email
**Missing:**
- Create/read/update/delete email protection policies
- Configure scanning modules (anti-malware, anti-spam, web reputation, DLP, etc.)
- Policy assignment to users/groups/domains
- Virtual Analyzer (sandbox) settings per policy
- Content filtering rules
- DLP template management
- DMARC/DKIM/SPF policy configuration (CEGP)
- Email gateway rules (CEGP)
- Quarantine policy settings
- Notification templates

**Impact:** Email security is the most common V1 use case. Every email protection
deployment requires clicking through 6+ scanning modules per policy. No way to:
- Template policies across multiple tenants
- Automate policy changes for compliance
- Version control email security settings
- Bulk-configure scanning modules

**Workaround:** Browser automation for CECP (modules/email/cecp/) and CEGP (modules/email/cegp/)

---

### 4. Network Security Configuration

**Console:** Network Security > Network Inventory / Inspection Rules / Virtual Patches
**Available APIs:** list_public_ips (ASRM, not network security), search_network_logs (ZTSA logs only)
**Missing:**
- Network sensor/appliance management (TippingPoint, DDI, VNS)
- Inspection rule management (enable/disable IPS signatures)
- Virtual patch deployment
- Network sensor policy assignment
- Traffic filtering rules
- Network object groups
- SSL inspection settings
- Suspicious connection blocking rules
- C&C callback blocking configuration

**Impact:** Network security appliances (DDI, TippingPoint, VNS) are managed entirely
through the console. No API exists for:
- Automating virtual patch deployment after vulnerability scans
- Programmatic IPS rule tuning
- Network sensor provisioning at scale
- Integration with vulnerability management workflows

**Workaround:** Browser automation (modules/network/)

---

## PRIORITY 2 -- High-Priority Missing APIs

### 5. Identity Security Configuration

**Console:** Identity Security > Identity Posture / Access Control / Identity Inventory
**Available APIs:** search_identity_logs (read-only log search), response_domain_accounts_* (disable/enable/reset/signout)
**Missing:**
- Identity posture policies (password strength, MFA enforcement)
- Access control policies
- Identity inventory management (beyond what ASRM provides)
- AD/Entra ID connector configuration
- Privileged account monitoring rules
- Identity risk scoring configuration
- Suspicious sign-in detection settings

**Impact:** Identity security is increasingly critical. Response actions exist (disable
account, force reset) but no way to configure the detection/prevention policies that
trigger those actions.

**Workaround:** Browser automation (modules/identity/)

---

### 6. Data Security Configuration

**Console:** Data Security > Data Discovery / Data Classification / DLP Policies
**Available APIs:** None (0 operations)
**Missing:**
- Data discovery scan configuration
- Data classification rules
- DLP policy management
- Sensitive data patterns
- Data security incident management
- Cloud storage scanning policies (beyond file-storage-security in cloud module)

**Impact:** Data security/DLP is a compliance requirement. Zero API coverage means
every DLP policy must be created manually. No:
- Policy export/import
- Compliance template deployment
- Automated policy updates for new regulations

**Workaround:** Browser automation (modules/data-security/)

---

### 7. AI Security Configuration

**Console:** AI Security > AI Service Access Control / AI Application Security
**Available APIs:** ai_security_apply_guardrails (single operation -- evaluate guardrails, does not manage config)
**Missing:**
- AI service access control policies (allow/block AI services)
- AI application security policies
- AI usage monitoring rules
- Prompt injection detection configuration
- AI data leakage prevention rules
- AI model inventory management
- Shadow AI detection settings

**Impact:** AI security is the newest V1 module and fastest-growing concern. The single
existing API evaluates guardrails but cannot configure them. No way to:
- Programmatically manage which AI services are allowed
- Deploy consistent AI security policies across org
- Integrate AI security with existing security orchestration

**Workaround:** Browser automation (modules/ai-security/)

---

### 8. Workflow & Automation (Playbooks) Management

**Console:** Workflow & Automation > Playbooks / Custom Scripts / Response Management
**Available APIs:** list_security_playbooks_* (read playbooks/tasks), security_playbooks_playbooks_run (trigger), list_scripts, list_response_* (response settings/tasks)
**Missing:**
- Create/update/delete playbooks (can only read and trigger)
- Playbook template management
- Custom script CRUD (can only list, not create/edit)
- Automated response rule configuration (auto-containment, auto-block)
- Notification channel configuration
- SOAR integration settings

**Impact:** Can trigger existing playbooks but cannot create or modify them via API. This
means playbook development is console-only -- no version control, no CI/CD for security
automation.

**Workaround:** Partial -- run existing playbooks via API, create new ones via browser

---

## PRIORITY 3 -- Medium-Priority Missing APIs

### 9. Mobile Security Configuration

**Console:** Mobile Security > Mobile Device Inventory / Mobile Security Policies
**Available APIs:** search_mobile_logs (read-only log search)
**Missing:**
- Mobile device management (MDM) policies
- Mobile threat detection configuration
- App reputation settings
- Device compliance rules
- Mobile app allowlist/blocklist

**Impact:** Mobile security policies are console-only. Lower priority because mobile
deployments are typically configured once and rarely changed.

**Workaround:** Browser automation (modules/mobile/)

---

### 10. Service Management Configuration

**Console:** Service Management > Service Gateway / Product Connector / Data Upload
**Available APIs:** container_security_generate_service_gateway_password (single operation)
**Missing:**
- Service Gateway deployment and management
- Product connector configuration (Apex One, Deep Security, etc.)
- Data upload settings
- Proxy settings for cloud connectivity
- Service health monitoring configuration

**Impact:** Service Management is infrastructure setup -- done once per deployment. But
automating this for multi-tenant MSP environments would be valuable.

---

### 11. Administration Settings

**Console:** Administration > User Accounts / API Keys / Notifications / License
**Available APIs:** list_accounts, list_api_keys, list_roles, IAM CRUD, list_audit_logs
**Missing:**
- Notification settings (email/webhook/SIEM delivery)
- License management
- SSO/SAML configuration
- Syslog output configuration (CEF/JSON format, transport)
- Third-party integration settings (ServiceNow, Splunk, etc.)
- Console customization (branding, language)

**Impact:** IAM is well-covered. But notification routing and integration settings have no
API, which blocks automation of:
- Multi-tenant notification setup
- SIEM integration provisioning
- Automated license management

---

### 12. Threat Intelligence Management

**Console:** Threat Intelligence > Intelligence Reports / Custom Intelligence / STIX/TAXII
**Available APIs:** list_intel_reports, get_intel_report, CRUD for intelligence reports and suspicious objects, TAXII feed endpoints
**Missing:**
- STIX/TAXII feed source management (add/remove feeds)
- Custom intelligence sharing group configuration
- Threat intelligence scoring rules
- IoC auto-import settings
- Intelligence report auto-generation settings

**Impact:** Core intel operations (list, search, add/remove IOCs) are covered. Gap is
in feed management and sharing configuration -- needed for ISAC integrations.

---

## PRIORITY 4 -- Low-Priority / Adequate Coverage

### 13. Dashboards & Reports

**Console:** Dashboards & Reports > Executive Dashboard / Risk Dashboard / Custom Reports
**Available APIs:** None for dashboard configuration, but ASRM/alert/OAT data APIs cover underlying data
**Missing:** Dashboard layout, scheduled report configuration, custom report builder
**Impact:** Low -- dashboards are consumption, not configuration. Data APIs are sufficient.

---

### 14. TrendAI Flex Licensing

**Console:** TrendAI Flex Licensing > Credits Usage / Credit Allocation
**Available APIs:** None
**Missing:** Credit usage query, allocation management
**Impact:** Low -- licensing is a business operation, not security automation.

---

## Coverage Summary

| V1 Console Section | API Operations | Coverage | Gap |
|--------------------|---------------|----------|-----|
| Agentic SIEM & XDR (Workbench) | 35+ | HIGH | Notes, insights, alerts well covered |
| Attack Surface Risk Management | 40+ | HIGH | Comprehensive device/vuln/risk APIs |
| Container Security | 30+ | FULL | Complete CRUD for policies/rulesets |
| Cloud Account Management | 15+ | HIGH | Onboarding, features, CSPM |
| Detection Model Management | 10+ | HIGH | Models, exceptions, custom filters |
| Response Management | 20+ | HIGH | Blocklist, isolation, scripts, YARA |
| Email Asset Inventory | 6 | MEDIUM | Read-only inventory, no policy CRUD |
| Endpoint Management | 8 | LOW | List/export/override only, no policy CRUD |
| **ZTSA** | **1** | **NONE** | **Only log search, zero config APIs** |
| **Network Security** | **1** | **NONE** | **Only public IPs via ASRM** |
| **Identity Security** | **5** | **LOW** | **Response actions only, no policies** |
| **Data Security** | **0** | **NONE** | **Zero API coverage** |
| **AI Security** | **1** | **NONE** | **Guardrail eval only, no config** |
| **Mobile Security** | **1** | **NONE** | **Only log search** |
| Workflow & Automation | 8 | MEDIUM | Read/trigger only, no create/edit |
| IAM / Administration | 12 | HIGH | User/role/key CRUD, audit logs |
| Threat Intelligence | 10+ | MEDIUM | IOCs covered, feed mgmt missing |

### API-to-Console Ratio by Product Area

```
Container Security   ====================  100% API coverage (CRUD)
ASRM / Risk Mgmt    ====================   95% (read-heavy, sufficient)
Detection Models     ====================   90% (CRUD for models/exceptions)
Response Actions     ====================   90% (block/isolate/scan/script)
Cloud Accounts       ===================    85% (onboard/features/status)
Workbench / XDR      ===================    85% (alerts/OAT/insights)
IAM / Admin          ================       80% (users/keys/roles, no notifications)
Threat Intel         ==============         70% (IOCs yes, feeds no)
Workflow             ==========             50% (read/trigger, no create)
Email Security       ======                 30% (inventory read, no policies)
Endpoint Policies    ====                   20% (override only, no CRUD)
Identity Security    ===                    15% (response actions only)
ZTSA                 =                       5% (log search only)
Network Security     =                       5% (public IPs only)
AI Security          =                       5% (guardrail eval only)
Data Security        .                       0% (nothing)
Mobile Security      =                       5% (log search only)
```

---

## Recommendations for Product Management

### Tier 1: Ship These First (blocks automation for most customers)

1. **ZTSA Policy CRUD** -- Every ZTSA customer does policy work in the console daily.
   Access rules, internet/private access config, connector management.

2. **Endpoint Security Policy CRUD** -- Every V1 customer has endpoints. Creating/editing
   policies programmatically is table stakes for enterprise security.

3. **Email Security Policy CRUD** -- Email is the #1 attack vector. CECP/CEGP policy
   management via API enables MSP multi-tenant management.

### Tier 2: High Demand (blocks specific workflows)

4. **Network Security / Virtual Patching API** -- Vulnerability-to-virtual-patch automation
   is a top customer request.

5. **Identity Security Policy Configuration** -- Zero trust requires identity policy automation.

6. **Playbook CRUD** -- Security automation teams need to manage playbooks as code.

### Tier 3: Growing Demand

7. **AI Security Configuration** -- Fastest-growing area, needs API before market demands it.

8. **Data Security / DLP Policies** -- Compliance automation requires this.

9. **Notification/Integration Settings** -- Multi-tenant SIEM/SOAR provisioning.

---

## How v1-policy Skill Bridges the Gap

For every "NONE" or "LOW" coverage area above, this skill provides browser automation
via Blueprint MCP as an interim solution:

| Gap | Module | Method |
|-----|--------|--------|
| ZTSA policies | modules/ztsa/ | Blueprint browser automation |
| Endpoint policies | modules/endpoint/ | Blueprint + v1-api for read |
| Email policies | modules/email/ | Blueprint + v1-api for inventory |
| Network security | modules/network/ | Blueprint browser automation |
| Identity security | modules/identity/ | Blueprint + v1-api for response |
| Data security | modules/data-security/ | Blueprint browser automation |
| AI security | modules/ai-security/ | Blueprint browser automation |
| Mobile security | modules/mobile/ | Blueprint browser automation |

Each module uses APIs where available (read operations, response actions) and falls
back to browser automation for configuration/policy CRUD that has no API.
