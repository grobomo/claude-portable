# Identity Security Reference

Centralized reference for identity security configuration, posture, and access control.

## API Coverage: LOW (15%)

| What exists | What is missing |
|-------------|-----------------|
| search_identity_logs (read activity) | Identity posture policies |
| response_domain_accounts_disable | Access control policies |
| response_domain_accounts_enable | AD/Entra ID connector config |
| response_domain_accounts_reset_password | Privileged account monitoring |
| response_domain_accounts_sign_out | Risk scoring configuration |
| list_domain_accounts (ASRM) | Detection settings |
| list_high_risk_users (ASRM) | Identity inventory management |

**Response actions exist. Policy configuration requires browser automation.**

## Console Navigation

```
V1 Console > Identity Security (left sidebar)
```

| Page | Path | Purpose |
|------|------|---------|
| Identity Overview | Identity Security > Overview | Risk dashboard, compromised accounts |
| Identity Posture | Identity Security > Identity Posture | Password, MFA, privilege assessment |
| Access Activity | Identity Security > Access Activity | Sign-in analytics, anomalies |
| Identity Inventory | Identity Security > Identity Inventory | Users, service accounts, groups |
| Risk Indicators | Identity Security > Risk Indicators | Identity-based risk events |

## Lab State (joeltest.org, 2026-03-02)

### Connected Identity Sources

To be documented via browser automation.

### Domain Accounts

```bash
# Check via API
python .claude/skills/v1-api/executor.py list_domain_accounts
python .claude/skills/v1-api/executor.py list_high_risk_users
```

## V1 API Operations

| Operation | Purpose | Type |
|-----------|---------|------|
| search_identity_logs | Search identity activity logs | Read |
| list_domain_accounts | List domain accounts | Read |
| list_high_risk_users | List high-risk users | Read |
| get_high_risk_user | Get user risk details | Read |
| response_domain_accounts_disable | Disable user account | Response |
| response_domain_accounts_enable | Enable user account | Response |
| response_domain_accounts_reset_password | Force password reset | Response |
| response_domain_accounts_sign_out | Force sign out | Response |

## Browser Automation Required For

| Task | Console Path | Priority |
|------|-------------|----------|
| Configure identity posture policies | Identity Posture > Settings | P1 |
| Set up AD/Entra connector | Identity Security > Settings > Connectors | P1 |
| Configure access control rules | Access Activity > Rules | P2 |
| Set risk scoring thresholds | Risk Indicators > Settings | P2 |
| Manage privileged account monitoring | Identity Posture > Privileged Accounts | P2 |
| Configure detection rules | Identity Security > Detection Rules | P3 |

## Key Concepts

### Identity Risk Indicators

| Indicator | Description |
|-----------|-------------|
| Compromised credentials | Credentials found in breach databases |
| Suspicious sign-in | Unusual location, device, or time |
| Impossible travel | Sign-ins from geographically impossible locations |
| Brute force | Multiple failed authentication attempts |
| Privilege escalation | Unexpected admin role assignment |
| Stale accounts | Inactive accounts with active permissions |

### Identity Sources

| Source | Integration |
|--------|------------|
| Active Directory | On-prem AD connector |
| Azure AD / Entra ID | Cloud connector |
| Okta | API integration |
| Google Workspace | API integration |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| No identity data | Check AD/Entra connector is configured and syncing |
| Identity logs empty | Verify identity source integration is active |
| Risk scores not calculating | Ensure sufficient identity activity data (>7 days) |
| Response actions failing | Check service account permissions on AD/Entra |
| Stale account alerts | Review retention settings for inactive account threshold |
