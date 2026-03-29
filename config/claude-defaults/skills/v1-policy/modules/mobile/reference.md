# Mobile Security Reference

Centralized reference for mobile device security, MDM policies, and threat detection.

## API Coverage: MINIMAL (5%)

| What exists | What is missing |
|-------------|-----------------|
| search_mobile_logs (read activity) | MDM policy CRUD |
| | Mobile threat detection config |
| | App reputation settings |
| | Device compliance rules |
| | Mobile app allowlist/blocklist |
| | Device inventory management |

**All configuration operations require browser automation via Blueprint.**

## Console Navigation

```
V1 Console > Mobile Security (left sidebar)
```

| Page | Path | Purpose |
|------|------|---------|
| Mobile Overview | Mobile Security > Overview | Dashboard, device status |
| Mobile Device Inventory | Mobile Security > Device Inventory | Enrolled devices |
| Mobile Security Policies | Mobile Security > Policies | MDM and threat policies |
| Mobile Threat Detection | Mobile Security > Threat Detection | Malware, phishing, network threats |
| Mobile App Management | Mobile Security > App Management | App allowlist/blocklist |

## Lab State (joeltest.org, 2026-03-02)

Not configured -- no mobile devices enrolled. Requires:
- Mobile Security license
- MDM enrollment (iOS: Apple Push, Android: Android Enterprise)
- Mobile Security app on devices

## V1 API Operations

| Operation | Purpose | Type |
|-----------|---------|------|
| search_mobile_logs | Search mobile activity logs | Read |

### Mobile Log Search Example

```bash
python .claude/skills/v1-api/executor.py search_mobile_logs hours=24 limit=10
```

## Browser Automation Required For

| Task | Console Path | Priority |
|------|-------------|----------|
| Create mobile security policy | Policies > Add Policy | P1 |
| Configure threat detection | Threat Detection > Settings | P1 |
| Manage app allowlist/blocklist | App Management | P2 |
| View device inventory | Device Inventory | P2 |
| Set device compliance rules | Policies > Compliance | P2 |
| Configure enrollment settings | Mobile Security > Settings | P3 |

## Key Concepts

### Mobile Threat Types

| Threat | Description |
|--------|-------------|
| Malicious Apps | Malware, spyware, adware |
| Phishing | URL-based phishing on mobile |
| Network Attacks | Rogue Wi-Fi, MitM, SSL stripping |
| Device Vulnerabilities | Jailbreak/root, OS vulnerabilities |
| Data Leakage | Sensitive data exposure via apps |

### Mobile Policy Components

| Component | Description |
|-----------|-------------|
| Threat Scan | Real-time scanning for malicious apps |
| Web Reputation | Block malicious/phishing URLs |
| Network Protection | Detect rogue Wi-Fi, VPN enforcement |
| Device Compliance | OS version, jailbreak detection, encryption |
| App Control | Allowlisted/blocklisted applications |

### Platform Support

| Feature | iOS | Android |
|---------|-----|---------|
| Threat scanning | Yes | Yes |
| Web reputation | Yes | Yes |
| App control | Yes | Yes |
| Network protection | Limited | Yes |
| Device compliance | Yes | Yes |
| Remote wipe | Yes | Yes |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Mobile Security menu not visible | Check V1 license includes Mobile Security module |
| No devices enrolled | Configure MDM enrollment (Apple Push / Android Enterprise) |
| Mobile logs empty | Verify Mobile Security app installed on devices |
| Threat detection not working | Check policy is assigned to device group |
| App control not enforcing | Verify MDM profile installed on device |
