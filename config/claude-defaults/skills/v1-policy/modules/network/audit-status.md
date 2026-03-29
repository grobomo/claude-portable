# Network Security: Audit Status

Check network security sensor health and detection state.

## API-Based Checks

```bash
# Public IPs (ASRM, not network-specific but related)
python .claude/skills/v1-api/executor.py list_public_ips

# Network logs (note: this is ZTSA logs, not IPS/DDI)
python .claude/skills/v1-api/executor.py search_network_logs hours=24 limit=10

# Endpoints that may have network agents
python .claude/skills/v1-api/executor.py list_endpoints top=100
```

## Browser-Based Checks

```
1. Navigate to Network Security > Network Inventory
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_lookup query="Network Inventory"
   mcpm call blueprint browser_click selector="<result>"
   mcpm call blueprint browser_take_screenshot
   → Shows: all registered sensors, status, last seen

2. Check IPS rule state
   Navigate to Network Security > Intrusion Prevention
   mcpm call blueprint browser_take_screenshot
   → Shows: enabled rules, recent detections

3. Check virtual patch deployment
   Navigate to Network Security > Intrusion Prevention > Virtual Patches
   mcpm call blueprint browser_take_screenshot
   → Shows: deployed patches, CVE coverage

4. Check suspicious connections
   Navigate to Network Security > Suspicious Connections
   mcpm call blueprint browser_take_screenshot
   → Shows: blocked C&C callbacks, botnet detection
```

## Health Check Criteria

| Check | Healthy | Unhealthy |
|-------|---------|-----------|
| Sensor status | Online, recent heartbeat | Offline >1h |
| IPS rules | Current signatures, enabled | Outdated or disabled |
| Virtual patches | Deployed for known CVEs | Unpatched vulnerabilities |
| Detections | Expected volume for traffic | Zero detections or spike |
| C&C blocking | Active and blocking | Disabled or not configured |

## Lab-Specific Checks

```bash
# VNS health via CLISH
ssh admin@3.146.110.166  # pw: V1Sensor@Lab2026!
# > enable > connect  (should show all "good")

# DDI #1 via tunnel
ssh -i ~/.aws/png.pem -L 8443:10.0.2.228:443 ec2-user@3.16.81.109
# Open https://localhost:8443

# DDI #2 via tunnel
ssh -i ~/.aws/png.pem -L 8444:10.0.3.237:443 ec2-user@3.16.81.109
# Open https://localhost:8444
```
