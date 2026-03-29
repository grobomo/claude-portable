# CEGP: Provision Domain

Add a new email domain to CEGP and configure MX records for gateway scanning.

## Current Domains (2026-03-02)

| Domain | Inbound | Outbound | Status |
|--------|---------|----------|--------|
| joeltest.org | Completed | Completed | Active |
| joeltest2.org | NOT CONFIGURED | NOT CONFIGURED | Pending |
| test.cbegroup.com | NOT CONFIGURED | NOT CONFIGURED | Pending |

Check via API:
```bash
python .claude/skills/v1-api/executor.py list_email_asset_inventory_email_domains
```

## Provision New Domain Workflow

```
1. Navigate to Email & Collaboration Security > Email Gateway > Domain Management
   mcpm call blueprint browser_lookup query="Domain Management"
   # OR: Email Gateway > Domains

2. Click "Add Domain"
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_lookup query="Add Domain"
   mcpm call blueprint browser_click selector="<add-button>"

3. Enter domain name
   mcpm call blueprint browser_type selector="<domain-input>" text="<domain.com>"

4. CEGP provides MX records to configure in DNS
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_take_screenshot
   # Record the MX values shown

5. Configure MX records in DNS provider
   # This step requires access to the domain's DNS (Route53, Cloudflare, etc.)
   # MX records point to CEGP gateway: *.mail.trendmicro.com

6. Verify domain ownership (TXT record or email verification)

7. Configure inbound scanning policy
   # See create-gateway-policy.md

8. Configure outbound scanning (optional)
   # Requires smart host routing through CEGP

9. Verify via API
   python .claude/skills/v1-api/executor.py list_email_asset_inventory_email_domains
```

## DNS Records Required

| Type | Host | Value | Purpose |
|------|------|-------|---------|
| MX | @ | CEGP gateway (provided by V1) | Route inbound mail through CEGP |
| TXT | @ | Verification token | Domain ownership proof |
| TXT | @ | SPF include for CEGP | Allow CEGP to send on behalf of domain |

## Documentation

```bash
python .claude/skills/trend-docs/executor.py "trend-vision-one-email-domains" --max-pages 2
```
