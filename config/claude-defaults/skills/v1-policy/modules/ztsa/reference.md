# Zero Trust Secure Access (ZTSA) Reference

Centralized reference for ZTSA configuration, policies, and automation.

## API Coverage: MINIMAL (5%)

| What exists | What is missing |
|-------------|-----------------|
| search_network_logs (read ZTSA activity) | ALL policy CRUD |
| | Access rule management |
| | Internet/Private access config |
| | Connector management |
| | SAM deployment tokens |
| | User/group assignment |

**All policy operations require browser automation via Blueprint.**

## Console Navigation

```
V1 Console > Zero Trust Secure Access (left sidebar)
```

| Page | Path | Purpose |
|------|------|---------|
| Secure Access Overview | Zero Trust Secure Access > Overview | Dashboard, connection stats |
| Secure Access Rules | Zero Trust Secure Access > Secure Access Rules | Allow/block/monitor rules |
| Internet Access Config | Zero Trust Secure Access > Internet Access Configuration | URL categories, cloud apps |
| Private Access Config | Zero Trust Secure Access > Private Access Configuration | Internal apps, connectors |
| Private Access Connectors | Zero Trust Secure Access > Private Access Connectors | Connector deployment/health |
| Secure Access Module | Zero Trust Secure Access > Secure Access Module | SAM deployment |
| Risk Control | Zero Trust Secure Access > Risk Control | Risk-based access decisions |

## Lab State (joeltest.org, 2026-03-02)

### Secure Access Module (SAM)

| Endpoint | SAM Status | Notes |
|----------|-----------|-------|
| EC2AMAZ-MSDQHND (Windows) | Deployed | t3.medium, win-ztsa-test stack |
| Linux endpoints | N/A | SAM not supported on Linux |

### Access Rules

To be documented via browser automation (no API).

## V1 API Operations

| Operation | Purpose | Covers |
|-----------|---------|--------|
| search_network_logs | Search ZTSA/network activity logs | Read-only activity data |

## Browser Automation Required For

| Task | Console Path | Priority |
|------|-------------|----------|
| Create access rule | Secure Access Rules > Add Rule | P1 |
| Edit access rule | Secure Access Rules > click rule | P1 |
| Configure Internet Access | Internet Access Configuration | P1 |
| Configure Private Access | Private Access Configuration | P1 |
| Deploy connector | Private Access Connectors > Add | P2 |
| Deploy SAM | Secure Access Module > Deploy | P2 |
| Configure risk control | Risk Control > Settings | P3 |

## Key Concepts

### Access Rule Types

| Type | Purpose |
|------|---------|
| Internet Access | Control access to external sites/services |
| Private Access | Control access to internal applications |
| Cloud App Access | Control access to sanctioned cloud apps |

### Rule Components

| Component | Description |
|-----------|-------------|
| Users/Groups | Who the rule applies to (AD/Entra ID sync) |
| Applications | What apps/URLs/categories are controlled |
| Action | Allow, Block, Monitor, Isolate |
| Schedule | When the rule is active |
| Risk Level | Threshold for risk-based enforcement |

### SAM Platforms

| OS | Supported |
|----|-----------|
| Windows 10/11 | Yes |
| Windows Server 2016+ | Yes |
| macOS 10.15+ | Yes |
| Linux | No |
| iOS / Android | Via mobile app |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| SAM not connecting | Check proxy settings, verify ZTSA license enabled |
| No ZTSA logs | Traffic must flow through SAM/connector (not direct) |
| Connector offline | Check connector VM, verify outbound 443 to V1 |
| Rules not applying | Check user/group sync from identity provider |
| Browser access bypasses SAM | Configure PAC file or use SAM in transparent mode |
