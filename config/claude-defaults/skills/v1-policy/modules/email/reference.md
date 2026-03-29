# Email Security Reference

Centralized reference for both CECP and CEGP email security modules.
Individual workflow files cross-reference this for detailed settings.

## Console Navigation

### CECP (Cloud Email & Collaboration Protection)

```
V1 Console > Email & Collaboration Security (left sidebar)
```

| Page | Path | Purpose |
|------|------|---------|
| Dashboard | Email & Collaboration Security > Dashboard | Overview stats |
| Email Asset Inventory | Email & Collaboration Security > Email Asset Inventory | Accounts, domains, policy assignments |
| Policies | Email & Collaboration Security > Policies | Create/edit/assign scanning policies |
| Quarantine | Email & Collaboration Security > Quarantine | Manage quarantined messages |
| Logs | Email & Collaboration Security > Logs | Email message tracking |
| Settings | Email & Collaboration Security > Settings | Service connections, sensor config |

### CEGP (Cloud Email Gateway Protection)

```
V1 Console > Email & Collaboration Security > Email Gateway (sub-section)
```

| Page | Path | Purpose |
|------|------|---------|
| Domain Management | Email Gateway > Domains | Add/verify domains, MX config |
| Policy Management | Email Gateway > Policy Management | Inbound/outbound scanning rules |
| DKIM Settings | Email Gateway > Domain Settings > DKIM | DKIM key generation + DNS setup |
| Mail Tracking | Email Gateway > Mail Tracking | Gateway log search |

## CECP Scanning Modules (6)

### 1. Advanced Spam Protection

| Setting | Options | Default |
|---------|---------|---------|
| Detection level | Low / Medium / High / Very High | Medium |
| Action per category | Quarantine / Delete / Tag subject / Pass | Varies |
| Blocked senders | Email/domain list | Empty |
| Approved senders | Email/domain list | Empty |

Doc: `trend-vision-one-advanced-spam-protection`

### 2. Anti-Malware Scanning

| Setting | Options | Default |
|---------|---------|---------|
| Scan engine | Machine Learning / Pattern / Both | Both |
| Action on detection | Quarantine / Delete / Tag / Pass | Quarantine |
| Scan attachments | On/Off | On |
| Password-protected files | Block / Pass | Pass |

Doc: `trend-vision-one-anti-malware-scanning`

### 3. Web Reputation

| Setting | Options | Default |
|---------|---------|---------|
| Risk level threshold | Low / Medium / High | Medium |
| Action | Block / Warn / Pass | Block |
| Exception URLs | URL list | Empty |
| Track clicked URLs | On/Off | On |

Doc: `trend-vision-one-web-reputation`

### 4. Data Loss Prevention (DLP)

| Setting | Options | Default |
|---------|---------|---------|
| DLP template | Compliance templates (HIPAA, PCI, GDPR, etc.) | None |
| Custom rules | Keyword/regex patterns | Empty |
| Action | Block / Quarantine / Encrypt / Tag / Monitor | Monitor |
| Apply to | Outbound / Inbound / Internal | Outbound |

Docs: `dlp_config`, `dlp_actions`, `dlp_templates`

### 5. Virtual Analyzer (Sandbox)

| Setting | Options | Default |
|---------|---------|---------|
| File types | Documents / Executables / Archives / All | All |
| Timeout | 1-10 minutes | 3 minutes |
| Verdict actions | Quarantine suspicious / Block malicious | Both |
| URL analysis | On/Off | On |

Doc: `trend-vision-one-virtual-analyzer-cemp`

### 6. Content Filtering

| Setting | Options | Default |
|---------|---------|---------|
| Blocked extensions | File extension list (.exe, .bat, etc.) | Common executables |
| Size limits | Max attachment size MB | 50 MB |
| Embedded content | Block macros / scripts | Block |

Doc: `trend-vision-one-content-filtering`

## CEGP Scanner Layers

CEGP applies multiple scanners per policy rule. From 30-day detection data (joeltest.org):

| Scanner | Total Scans | Clean | Sandbox | Quarantine |
|---------|-------------|-------|---------|------------|
| ContentFilter | 850 | 850 | 0 | 0 |
| GeneralFilter | 606 | 606 | 0 | 0 |
| AntiSpam | 464 | 440 | 20 | 4 |
| AntiVirus | 376 | 373 | 3 | 0 |
| Correlated Intelligence | 210 | 210 | 0 | 0 |
| DlpFilter | 10 | 10 | 0 | 0 |

CEGP default policies:
- Global Inbound Policy (Virus) -- AntiVirus scanning
- Global Inbound Policy (Spam) -- AntiSpam with URLDDAScan
- Global Outbound Policy (Virus) -- AntiVirus bypass on outbound

## V1 API Operations

| Operation | Returns | Used By |
|-----------|---------|---------|
| `list_email_asset_inventory_email_accounts` | All accounts with sensor status, policy assignments | CECP audit, sensor check |
| `list_email_asset_inventory_email_domains` | Domain configuration status (inbound/outbound) | CEGP audit, domain check |
| `list_email_asset_inventory_email_servers` | Connected mail services | CECP provisioning |
| `search_email_logs hours=N limit=N` | Email activity logs (both CECP + CEGP) | Both: detection audit |

### Filtering Logs by Product

```bash
# All email logs
python .claude/skills/v1-api/executor.py search_email_logs hours=168 limit=500

# Filter results by product:
#   CEGP: pname="Cloud Email Gateway Protection"
#         scanType: gateway_realtime_accepted_mail_traffic
#   CECP: pname="Cloud Email and Collaboration Protection"
#         scanType: exo_inline_realtime_accepted_mail_traffic
```

## Blueprint Automation Patterns

### Navigation

```
# Navigate to a section by text
mcpm call blueprint browser_lookup query="<section-name>"
mcpm call blueprint browser_click selector="<result>"
mcpm call blueprint browser_evaluate code="await new Promise(r => setTimeout(r, 3000))"

# Always snapshot before interacting
mcpm call blueprint browser_snapshot
```

### Form Interaction

```
# Type into a field
mcpm call blueprint browser_type selector="<input-selector>" text="<value>"

# Click a button by text
mcpm call blueprint browser_lookup query="Save"
mcpm call blueprint browser_click selector="<save-button>"

# Screenshot for confirmation
mcpm call blueprint browser_take_screenshot
```

### Discovery Protocol

V1 is a SPA with dynamic class names. Before every workflow step:

```
1. browser_snapshot -> get current DOM
2. browser_take_screenshot -> visual context
3. Compare against expected layout from module file
4. If UI changed -> browser_lookup with text content to find element
5. Adapt selectors, proceed
```

## Troubleshooting

| Issue | Product | Fix |
|-------|---------|-----|
| Section not in sidebar | CECP | Check V1 subscription / license |
| No accounts shown | CECP | Exchange Online not connected (go to Service Connections) |
| Sensor disabled | CECP | See enable-email-sensor.md |
| Policy changes not taking effect | CECP | 5-15 min propagation; check protection mode (inline vs API) |
| DLP templates not available | CECP | DLP is a separate license add-on |
| Sandbox queue full | Both | Check V1 credits (sandbox uses per-file credits) |
| Domain not verifying | CEGP | Check DNS TXT record propagation (dig TXT domain) |
| MX not routing | CEGP | Verify MX records point to *.mail.trendmicro.com |
| No gateway events | CEGP | Check MX routing; test with external sender |
| DKIM verification failed | CEGP | Check CNAME record propagation for selector._domainkey |

## Detection Effectiveness Benchmarks (joeltest.org, 30d)

| Metric | Value |
|--------|-------|
| Total emails processed | 144 |
| Detection rate | 18.8% |
| Quarantine rate | 2.8% |
| Sandbox submission rate | 3.4x (more sandbox scans than emails -- URL scanning) |
| CEGP share | 98.6% (142 events) |
| CECP share | 1.4% (2 events -- sensor disabled) |
| AntiSpam non-clean actions | 24 |

These benchmarks were captured 2026-03-02 with CECP sensor disabled. Expect CECP
numbers to increase significantly after sensor enablement.
