# V1 API Reference

Quick reference for finding the right API endpoints by use case.
Each endpoint links to its YAML file in `api_index/` for full details.

## Alerts & Detections

**"What security events need attention?"**

| Endpoint | Description |
|----------|-------------|
| `list_alerts` | Workbench alerts (correlated detections) |
| `get_alert` | Get alert details by ID |
| `update_alert` | Change alert status (New/In Progress/Closed) |
| `add_alert_note` | Add investigation note to alert |
| `get_alert_notes` | Get notes on an alert |
| `list_oat` | Observed Attack Techniques (behavioral detections) |

---

## Activity Logs & Hunting

**"What happened on endpoints/network/email?"**

| Endpoint | Description |
|----------|-------------|
| `search_endpoint_logs` | Endpoint activity (process, file, network events) |
| `search_network_logs` | ZTSA/network activity logs |
| `search_email_logs` | Email activity logs |
| `search_identity_logs` | Identity/authentication logs |
| `search_cloud_audit_logs` | Cloud audit trail |
| `search_mobile_logs` | Mobile device activity |

---

## Threat Intelligence

**"What IOCs should I block? What threats are trending?"**

| Endpoint | Description |
|----------|-------------|
| `list_blocklist` | View suspicious objects blocklist |
| `add_to_blocklist` | Block IP/domain/URL/hash |
| `remove_from_blocklist` | Unblock an IOC |
| `list_exceptions` | View exception (allow) list |
| `list_intel_reports` | Threat intelligence reports |
| `get_intel_report` | Get report details |
| `get_sandbox_result` | Sandbox analysis results |
| `get_sandbox_report` | Download sandbox report |

---

## Response Actions

**"How do I contain a threat?"**

| Endpoint | Description | Destructive |
|----------|-------------|-------------|
| `isolate_endpoint` | Network isolate endpoint | YES |
| `restore_endpoint` | Restore isolated endpoint | - |
| `terminate_process` | Kill process by SHA1 | YES |
| `collect_file` | Collect file for analysis | - |
| `quarantine_email` | Quarantine email message | YES |
| `restore_email` | Restore quarantined email | - |
| `delete_email` | Permanently delete email | YES |
| `list_scripts` | List custom response scripts | - |
| `run_script` | Execute script on endpoints | YES |
| `get_task` | Check response task status | - |

---

## Asset Inventory

**"What assets do I have? What's their status?"**

### Endpoints (Managed Agents)
| Endpoint | Description |
|----------|-------------|
| `list_endpoints` | List managed endpoints |
| `get_endpoint` | Get endpoint details |
| `list_endpoint_tasks` | List endpoint tasks |

### Attack Surface (ASRM)
| Endpoint | Description |
|----------|-------------|
| `list_devices` | All devices (discovered + managed) |
| `get_device` | Device details with risk score |
| `get_device_risks` | Device risk indicators |
| `list_cloud_assets` | Cloud assets (EC2, VMs, etc.) |
| `get_cloud_asset` | Cloud asset details |
| `get_cloud_asset_risks` | Cloud asset risk indicators |

---

## Risk Management (ASRM)

**"What are my highest risk assets/users?"**

| Endpoint | Description |
|----------|-------------|
| `list_high_risk_users` | Users with elevated risk scores |
| `get_high_risk_user` | User risk details |
| `list_domain_accounts` | Domain accounts |
| `list_service_accounts` | Service accounts |
| `list_public_ips` | Public-facing IP addresses |
| `list_fqdns` | Internet-facing domains |
| `list_local_apps` | Applications with risk/vulns |
| `get_local_app` | Application details |
| `get_local_app_vulns` | Application vulnerabilities |
| `list_custom_tags` | Custom asset tags |

---

## Cloud Security

**"What cloud accounts are connected? What's my posture?"**

### Cloud Accounts (CAM)
| Endpoint | Description |
|----------|-------------|
| `list_aws_accounts` | AWS accounts |
| `get_aws_account` | AWS account details |
| `list_azure_accounts` | Azure subscriptions |
| `get_azure_account` | Azure subscription details |
| `list_gcp_accounts` | GCP projects |
| `get_gcp_account` | GCP project details |
| `list_alibaba_accounts` | Alibaba Cloud accounts |

### Cloud Posture (CSPM)
| Endpoint | Description |
|----------|-------------|
| `list_cspm_accounts` | CSPM-monitored accounts |
| `get_cspm_checks` | Compliance check results |
| `run_cspm_scan` | Trigger posture scan |
| `scan_iac_template` | Scan IaC template |

### Container Security
| Endpoint | Description |
|----------|-------------|
| `list_k8s_clusters` | Kubernetes clusters |
| `get_k8s_cluster` | Cluster details |
| `list_k8s_images` | Container images |
| `list_container_vulns` | Container vulnerabilities |
| `list_ecs_clusters` | ECS clusters |

---

## Email Security (CECP)

**"What email accounts/domains are protected?"**

| Endpoint | Description |
|----------|-------------|
| `list_email_accounts` | Protected email accounts |
| `list_email_domains` | Protected email domains |
| `list_email_servers` | On-prem email servers |

---

## Administration

**"How do I manage users, API keys, and policies?"**

### IAM
| Endpoint | Description |
|----------|-------------|
| `list_accounts` | V1 console users |
| `list_roles` | Available roles |
| `list_api_keys` | API keys |

### Policies
| Endpoint | Description |
|----------|-------------|
| `list_policies` | Version control policies |
| `list_update_policies` | Agent update policies |

---

## API Patterns

### Templates
APIs follow consistent patterns based on their template:

| Template | Pagination | Date Filter | Filter Style |
|----------|------------|-------------|--------------|
| `standard_list` | `top` param | days | OData |
| `search` | `top` param | hours | TMV1-Query header |
| `single_get` | - | - | - |
| `simple_list` | - | - | - |
| `response_action` | - | - | Array body |
| `post_action` | - | - | Object body |
| `patch_update` | - | - | Object body |

### Common Parameters
- `days` / `hours` - Time range lookback
- `limit` - Max results (mapped to `top`)
- `filter` - Custom filter expression
- `severity` - Alert severity filter
- `risk_level` / `risk_score` - Risk filtering

---

## Known Issues & Gotchas

### 403 - Insufficient Credits
**Affected APIs:** `list_devices`, `list_cloud_assets`, `list_domain_accounts`, `list_service_accounts`, `list_fqdns`
**Fix:** Allocate ASRM credits in V1 Console > Administration > Subscription

### 404 - Product Not Configured
**Affected APIs:** `list_cspm_accounts`, `list_email_*`, `search_cloud_audit_logs`, `search_mobile_logs`
**Fix:** Connect the corresponding product in V1 Console

### Container APIs - No `top` Parameter
**Affected APIs:** `list_k8s_clusters`, `list_k8s_images`, `list_container_vulns`, `list_ecs_clusters`
**Note:** Use cursor pagination (nextLink), `top` param not supported

---

## Quick Examples

```python
# List critical alerts from last 7 days
v1("list_alerts", {"days": 7, "severity": "critical", "limit": 10})

# Search endpoint logs for PowerShell activity
v1("search_endpoint_logs", {"hours": 24, "filter": "processName:powershell*"})

# Block a malicious IP
v1("add_to_blocklist", {"ioc_type": "ip", "value": "192.168.1.100", "description": "C2 server"})

# Get high-risk users
v1("list_high_risk_users", {"risk_score": 70, "limit": 20})

# Check connected AWS accounts
v1("list_aws_accounts", {"limit": 50})
```
