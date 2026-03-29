# Container Security Reference

Centralized reference for Container Security policies, rulesets, and compliance scanning.
Container Security has full API support -- most operations can be done without browser automation.

## Console Navigation

```
V1 Console > Cloud Security > Container Security (left sidebar)
```

| Page | Path | Purpose |
|------|------|---------|
| Container Protection | Cloud Security > Container Protection | Runtime policies and clusters |
| Container Inventory | Cloud Security > Container Inventory | Images, clusters, namespaces |
| Compliance | Cloud Security > Compliance | Benchmark scans |

## Policy Model

Container Security policies contain **runtime rules** that define what actions to take
when containers violate security constraints.

### Rule Types

| Type | What It Checks | Example |
|------|---------------|---------|
| podSecurityContext | Pod-level security settings | hostNetwork=true, hostIPC=true, hostPID=true |
| containerSecurityContext | Container-level privileges | privileged=true |
| capabilities | Linux capabilities | baseline or restricted capabilities |
| portforward | Port forwarding attempts | kubectl port-forward |
| podexec | Exec into pods | kubectl exec |
| secrets | Secret access patterns | Volume mounts to /var/run/secrets |
| malware | Malware in containers | Runtime malware detection |
| unscannedImage | Unscanned container images | Images without vulnerability scan |
| vulnerabilities | Known CVEs in images | CVE severity thresholds |

### Actions

| Action | Effect |
|--------|--------|
| log | Record the event, allow the operation |
| block | Prevent the operation |
| terminate | Kill the container/pod |

## Current Policies (joeltest.org, 2026-03-02)

| Policy | Rules | Action Mode | Description |
|--------|-------|-------------|-------------|
| LogOnlyPolicy | 11 | All log | Comprehensive monitoring, no blocking |

Rule type breakdown for LogOnlyPolicy:
- podSecurityContext: hostNetwork, hostIPC, hostPID (3 rules)
- containerSecurityContext: privileged (1 rule)
- capabilities: baseline (1 rule)
- portforward, podexec, secrets, malware: 1 each (4 rules)
- unscannedImage, vulnerabilities: 1 each (2 rules)

## Rulesets

Rulesets are reusable collections of rules that can be attached to policies.

| API | Purpose |
|-----|---------|
| `list_container_security_rulesets` | All rulesets (custom + managed) |
| `list_container_security_custom_rulesets` | Custom rulesets only |
| `list_container_security_managed_rules` | Trend-managed rules (auto-updated) |

## Compliance Scanning

| API | Purpose |
|-----|---------|
| `list_container_security_compliance_scan_configuration` | Current scan config |
| `list_container_security_compliance_scan_summary` | Scan results summary |
| `list_container_security_compliance_scan_versions` | Available benchmarks |
| `container_security_start_compliance_scan` | Trigger a new scan |

## V1 API Operations (Full CRUD)

| Operation | Purpose |
|-----------|---------|
| `list_container_security_policies` | List all policies with rules |
| `get_container_security_policies` | Get single policy details |
| `container_security_policies` | Create new policy |
| `update_container_security_policies` | Modify existing policy |
| `delete_container_security_policies` | Delete a policy |
| `list_container_security_rulesets` | List all rulesets |
| `container_security_rulesets` | Create ruleset |
| `update_container_security_rulesets` | Modify ruleset |
| `delete_container_security_rulesets` | Delete ruleset |
| `list_container_security_attestors` | List image attestors |

## Current Infrastructure

| Resource | Status |
|----------|--------|
| K8s clusters | 0 connected |
| ECS clusters | 0 connected |
| Policies | 1 (LogOnlyPolicy) |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| No clusters visible | Connect K8s or ECS cluster via Cloud Security settings |
| Policy not applying | Check cluster group assignment |
| Compliance scan fails | Verify cluster connectivity and sensor version |
| Runtime events missing | Check sensor deployment on cluster nodes |
