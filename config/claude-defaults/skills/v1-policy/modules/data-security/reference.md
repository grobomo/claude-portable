# Data Security Reference

Centralized reference for data security, DLP, data discovery, and classification.

## API Coverage: ZERO (0%)

| What exists | What is missing |
|-------------|-----------------|
| Nothing | Everything |
| | Data discovery scan config |
| | Data classification rules |
| | DLP policy CRUD |
| | Sensitive data patterns |
| | Incident management |
| | Cloud storage scanning |

**ALL operations require browser automation via Blueprint.**

## Console Navigation

```
V1 Console > Data Security (left sidebar)
```

| Page | Path | Purpose |
|------|------|---------|
| Data Security Overview | Data Security > Overview | Dashboard, data risk summary |
| Data Discovery | Data Security > Data Discovery | Scan for sensitive data |
| Data Classification | Data Security > Data Classification | Classify data by type/sensitivity |
| DLP Policies | Data Security > DLP Policies | Data loss prevention rules |
| DLP Incidents | Data Security > DLP Incidents | Policy violation events |
| DLP Templates | Data Security > DLP Templates | Predefined compliance templates |

## Lab State (joeltest.org, 2026-03-02)

Not configured -- no data security policies active. Requires:
- Connected cloud storage (S3, Azure Blob, etc.)
- Email integration for email DLP
- Endpoint agent for endpoint DLP

## V1 API Operations

None. Zero API coverage for data security.

## Browser Automation Required For

| Task | Console Path | Priority |
|------|-------------|----------|
| Configure data discovery scans | Data Discovery > Settings | P1 |
| Create DLP policy | DLP Policies > Add Policy | P1 |
| Manage DLP templates | DLP Templates | P2 |
| Set data classification rules | Data Classification > Rules | P2 |
| View/manage DLP incidents | DLP Incidents | P2 |
| Configure sensitive data patterns | DLP Policies > Patterns | P3 |

## Key Concepts

### DLP Policy Components

| Component | Description |
|-----------|-------------|
| Templates | Predefined patterns (PCI-DSS, HIPAA, GDPR, PII) |
| Channels | Where to enforce (email, cloud storage, endpoints) |
| Actions | Block, quarantine, encrypt, notify, log only |
| Conditions | Pattern matches, file types, data volume thresholds |
| Exceptions | Users/groups/domains exempt from policy |

### Data Classification Levels

| Level | Description |
|-------|-------------|
| Public | No restrictions |
| Internal | Organization-only |
| Confidential | Restricted access |
| Highly Confidential | Strict controls required |

### Compliance Templates

| Template | Regulation |
|----------|-----------|
| PCI-DSS | Payment card data |
| HIPAA | Healthcare data |
| GDPR | EU personal data |
| PII | General personal info |
| Financial | Financial records |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| No data security menu | Check V1 license includes data security module |
| DLP not detecting | Verify agent has DLP module enabled, check policy scope |
| False positives | Tune patterns, add exceptions for known-good content |
| Cloud scanning not working | Verify cloud account connected with file-storage-security feature |
| Classification not applied | Check classification rules match data location |
