# Network Security Reference

Centralized reference for network security appliances, policies, and virtual patching.

## API Coverage: MINIMAL (5%)

| What exists | What is missing |
|-------------|-----------------|
| list_public_ips (ASRM, not network) | Sensor/appliance management |
| search_network_logs (ZTSA only) | IPS rule management |
| | Virtual patch CRUD |
| | Network policy assignment |
| | Traffic filtering rules |
| | C&C blocking config |

**All configuration operations require browser automation via Blueprint.**

## Console Navigation

```
V1 Console > Network Security (left sidebar)
```

| Page | Path | Purpose |
|------|------|---------|
| Network Inventory | Network Security > Network Inventory | Managed sensors/appliances |
| Network Analytics | Network Security > Network Analytics | Traffic analysis, detections |
| Intrusion Prevention | Network Security > Intrusion Prevention | IPS rules, virtual patches |
| Suspicious Connections | Network Security > Suspicious Connections | C&C, botnet blocking |
| Network Policies | Network Security > Network Policies | Policy assignment to sensors |

## Lab State (joeltest.org, 2026-03-02)

### Network Sensors

| Sensor | Type | Status | Notes |
|--------|------|--------|-------|
| VNS (i-03ce4039ab9f2cbc2) | Virtual Network Sensor | Deployed | m5.xlarge, vns-pcap-lab stack |
| DDI #1 | Deep Discovery Inspector | Deployed | 10.0.2.228 in locked subnet |
| DDI #2 | Deep Discovery Inspector | Deployed | 10.0.3.237 in locked subnet |

### Managed Appliances

| Appliance | Type | Management |
|-----------|------|------------|
| VNS | Virtual Network Sensor | V1 Console + CLISH |
| DDI | Deep Discovery Inspector | V1 Console + local web UI |
| TippingPoint | IPS appliance | V1 Console + SMS |

## V1 API Operations

| Operation | Purpose | Covers |
|-----------|---------|--------|
| list_public_ips | List public IPs (via ASRM) | Not network-security specific |

## Browser Automation Required For

| Task | Console Path | Priority |
|------|-------------|----------|
| View network inventory | Network Inventory | P2 |
| Manage IPS rules | Intrusion Prevention > Rules | P1 |
| Deploy virtual patches | Intrusion Prevention > Virtual Patches | P1 |
| Configure C&C blocking | Suspicious Connections > Settings | P2 |
| Assign network policies | Network Policies | P2 |
| View network analytics | Network Analytics | P3 |

## Key Concepts

### Network Sensor Types

| Type | Purpose | Deployment |
|------|---------|------------|
| Virtual Network Sensor (VNS) | Passive traffic monitoring | VM with mirror interface |
| Deep Discovery Inspector (DDI) | Deep packet inspection, sandbox | VM or appliance |
| TippingPoint | Inline IPS | Hardware or VM |

### Virtual Patching

Virtual patches provide temporary protection for unpatched vulnerabilities:
- Deploy via V1 console to TippingPoint/DDI
- Maps to CVEs from vulnerability scans
- Can be auto-deployed based on ASRM vulnerability data (if API existed)

### IPS Rule Categories

| Category | Description |
|----------|-------------|
| Vulnerability Protection | CVE-based signatures |
| Exploit Detection | Generic exploit patterns |
| C&C Callbacks | Known C&C communication |
| Lateral Movement | Internal network attacks |
| Data Exfiltration | Outbound data theft patterns |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| VNS not detecting traffic | Check mirror session, verify ENI attachment |
| DDI not reporting to V1 | Check registration, verify mgmt network connectivity |
| Virtual patch not applying | Verify sensor is online, check rule compatibility |
| High false positives | Tune IPS rules, add exceptions for known-good traffic |
| No network analytics | Check sensor data flow, verify V1 license covers network |
