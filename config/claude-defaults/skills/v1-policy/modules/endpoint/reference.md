# Endpoint Security Reference

Centralized reference for endpoint sensor policies, version control, and agent management.

## Console Navigation

```
V1 Console > Endpoint Security (left sidebar)
```

| Page | Path | Purpose |
|------|------|---------|
| Endpoint Inventory | Endpoint Security > Endpoint Inventory | List agents, status, policies |
| Sensor Policy | Endpoint Security > Sensor Policy | Configure detection settings per policy |
| Version Control | Endpoint Security > Version Control | Agent update schedules and pinning |
| Agent Deployment | Endpoint Security > Agent Deployment | Install scripts and tokens |

## Security Policy Types

Endpoints are assigned to one of four protection categories:

| Category | Policy Name Pattern | Use Case |
|----------|-------------------|----------|
| Standard Endpoint Protection (SEP) | Standard Endpoint Protection General Policy | Full EPP+EDR for desktops |
| Server & Workload Protection (SWP) | Server & Workload Protection General Policy | Server workloads |
| Connected Endpoint Protection | Connected Endpoint Protection General Policy | Managed by on-prem Apex One |
| Sensor Only | Sensor Only General Policy | Lightweight EDR-only agent |

## Current Endpoints (joeltest.org, 2026-03-02)

| Endpoint | OS | Security Policy | License |
|----------|-----|----------------|---------|
| WIN10 | Windows 10 | Sensor Only General Policy | EDR |
| ip-10-0-1-76 | Linux | Server & Workload Protection General Policy | EDR |
| ip-10-0-0-54 | Linux | Sensor Only General Policy | EDR |
| Joel-Ubuntu1 | Linux | Sensor Only General Policy | EDR |
| WIN22-JOEL | Windows | Standard Endpoint Protection General Policy | EDR + Advanced |
| dsm.joeltest.org | Windows | (none) | (none) |
| EC2AMAZ-MSDQHND | Windows | (none) | (none) |
| ip-172-31-42-162 | Linux | (none) | (none) |

**Note:** Endpoints with no security policy or license are visible in inventory but not
actively managed. They may be stale agents or pending deployment.

## Version Control Policies

Version control determines which agent build endpoints receive.

| Policy | Endpoint Groups | Editable |
|--------|----------------|----------|
| Default | All groups (24 groups) | Yes |

Available agent versions: n (latest), n-1, n-2, or pinned monthly (202601, 202512, etc.)

## V1 API Operations

| Operation | Returns | Purpose |
|-----------|---------|---------|
| `list_endpoints top=100` | All managed endpoints with policy/license | Inventory audit |
| `list_policies` | Version control policies and assigned groups | Version control audit |
| `list_endpoint_security_version_control_policies_agent_update_policies` | Available agent versions (n, n-1, monthly) | Version planning |
| `endpoint_security_endpoint_apply_sensor_policy` | Override sensor policy for specific endpoint | Per-endpoint config |
| `endpoint_security_endpoint_export` | Export endpoint info (CSV) | Reporting |
| `list_eiqs_endpoint` | Detailed endpoint list with extended info | Deep audit |
| `get_endpoint` | Single endpoint details | Troubleshooting |
| `list_search_sensor_statistics` | Sensor stats by endpoint | Health monitoring |

## Sensor Policy Settings (Browser Required)

Sensor policies are configured via the V1 console. Key settings:

| Setting | Options | Impact |
|---------|---------|--------|
| Behavior Monitoring | Enable/Disable | Process monitoring, suspicious activity detection |
| Predictive Machine Learning | Enable/Disable | ML-based unknown threat detection |
| Web Reputation | Enable/Disable | URL filtering on endpoints |
| Firewall | Enable/Disable | Host-based firewall rules |
| Device Control | Enable/Disable | USB/removable media control |
| Application Control | Enable/Disable | Whitelist/blacklist applications |
| Vulnerability Protection | Enable/Disable | Virtual patching (IPS rules) |
| Data Loss Prevention | Enable/Disable | Content inspection for sensitive data |

**Note:** These settings have no direct API -- they require Blueprint browser automation
to configure via the V1 console Sensor Policy page.

## EPP Agent Details

Endpoints connected to Apex One as a Service show additional EPP data:

| Field | Example | Meaning |
|-------|---------|---------|
| protectionManager | Trend Micro Apex One as a Service | EPP management server |
| endpointGroup | Joeltestorg | Agent group assignment |
| policyName | (varies) | Apex One policy name |
| componentVersion | outdatedVersion / upToDate | Pattern currency |
| componentUpdatePolicy | n-1 | Component update speed |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Endpoint shows no policy | Check if agent is installed and communicating |
| Agent version outdated | Check version control policy (Default allows n-1) |
| Sensor only but want full EPP | Assign to SEP or SWP group via console |
| Components outdated | Force update via console or check update schedule |
| Agent not reporting | Check service gateway connectivity, agent service status |
