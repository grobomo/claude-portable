# CEGP: Create DMARC/DKIM/SPF Policy

Configure email authentication policies for domains managed by CEGP.

## Email Authentication Stack

| Protocol | Purpose | Where Configured |
|----------|---------|-----------------|
| SPF | Authorize sending IPs | DNS TXT record |
| DKIM | Sign outbound email | CEGP console + DNS CNAME |
| DMARC | Policy for SPF/DKIM failures | DNS TXT record |

## DKIM Setup via CEGP

```
1. Navigate to Email Gateway > Domain Settings > DKIM
   mcpm call blueprint browser_lookup query="DKIM"

2. Select domain
   mcpm call blueprint browser_lookup query="<domain.com>"

3. Generate DKIM key pair
   mcpm call blueprint browser_lookup query="Generate"
   mcpm call blueprint browser_click selector="<generate-button>"

4. Copy the CNAME record values
   mcpm call blueprint browser_snapshot
   # CEGP provides: selector._domainkey.domain.com -> CNAME value

5. Add CNAME to DNS
   # Route53, Cloudflare, etc.

6. Verify DKIM in CEGP
   mcpm call blueprint browser_lookup query="Verify"
   mcpm call blueprint browser_click selector="<verify-button>"
```

## DMARC Policy (DNS Only)

Add TXT record at `_dmarc.domain.com`:

| Policy | Record | Effect |
|--------|--------|--------|
| Monitor | `v=DMARC1; p=none; rua=mailto:dmarc@domain.com` | Report only |
| Quarantine | `v=DMARC1; p=quarantine; rua=mailto:dmarc@domain.com` | Junk folder |
| Reject | `v=DMARC1; p=reject; rua=mailto:dmarc@domain.com` | Block delivery |

Start with `p=none` (monitor), review reports, then escalate.

## SPF Record

```
v=spf1 include:_spf.trendmicro.com include:spf.protection.outlook.com ~all
```

Must include CEGP's SPF range so outbound mail through the gateway passes SPF checks.

## Verification

```bash
# Check current DNS records
dig TXT joeltest.org +short
dig TXT _dmarc.joeltest.org +short
dig CNAME selector._domainkey.joeltest.org +short

# Check CEGP domain status
python .claude/skills/v1-api/executor.py list_email_asset_inventory_email_domains
```
