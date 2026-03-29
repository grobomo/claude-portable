---
keywords:
  - email
  - owa
  - inbox
  - outlook
  - graph
  - microsoft
  - msgraph
  - mail
  - pdhub
  - gpdh
---

# Email Reader

Read and interact with Outlook emails. Automatically chooses between MS Graph API (fast, programmatic) and OWA via Blueprint (browser automation, required for IRM-protected emails).

## Routing Logic

**Try MS Graph API first** when:
- Reading, searching, listing emails
- The email is NOT IRM-protected (Microsoft Rights Management)
- Sending replies or composing new emails

**Fall back to OWA + Blueprint** when:
- Email is IRM-protected (Graph API returns empty body / 403 for IRM content)
- Graph API token acquisition fails (expired secret, network error)
- User explicitly asks to use OWA/browser
- mcp-manager + Blueprint are available in the session

**Decision flow:**
1. Try Graph API token via GPDH credentials (credential-manager)
2. If token works → use Graph API
3. If token fails (expired secret / AADSTS7000215) → check if Blueprint MCP is available
4. If Blueprint available → use OWA
5. If neither works → prompt user to renew GPDH secret at portal

## Method 1: MS Graph API (preferred)

### Authentication via GPDH (pdhub)

**NOT az CLI** — az CLI is logged into joeltest.org, not corporate. Graph API for corporate email uses GPDH (Global Platform Developer Hub) OAuth app.

#### Credentials (OS credential store via credential-manager)

| Key | Value | Source | TTL |
|-----|-------|--------|-----|
| `gpdh/TENANT_ID` | Corporate tenant ID | pdhub portal (one-time) | Permanent |
| `gpdh/APPLICATION_ID` | Shared GPDH app ID | pdhub portal (one-time) | Permanent |
| `gpdh/SECRET_KEY` | Personal client secret | pdhub portal | **15 days** |
| `msgraph/ACCESS_TOKEN` | Cached JWT token | Token exchange | ~1 hour |

#### Getting a token

```python
import keyring, requests

tenant = keyring.get_password('claude-code', 'gpdh/TENANT_ID')
app_id = keyring.get_password('claude-code', 'gpdh/APPLICATION_ID')
secret = keyring.get_password('claude-code', 'gpdh/SECRET_KEY')

resp = requests.post(
    f'https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token',
    data={
        'grant_type': 'client_credentials',
        'client_id': app_id,
        'client_secret': secret,
        'scope': 'https://graph.microsoft.com/.default'
    }
)
token = resp.json().get('access_token')
```

**NOTE:** GPDH uses delegated permissions but the token grant is `client_credentials`. The GPDH app is pre-configured with Mail.Read, Mail.Send, etc.

#### When the secret expires (AADSTS7000215)

The error `Invalid client secret provided` means the 15-day secret has expired.

**To renew:**
1. Open portal: `start https://pdhub.infosec.trendmicro.com`
2. Log in with corporate SSO
3. Navigate to your app → Certificates & Secrets → New client secret
4. Copy the secret **value** (not the secret ID)
5. Store it:
```bash
python ~/.claude/skills/credential-manager/store_gui.py "gpdh/SECRET_KEY"
```
6. Also update the cached copy:
```bash
python ~/.claude/skills/credential-manager/store_gui.py "msgraph/ACCESS_TOKEN"
```
   (Or just delete the cached token — it will be re-fetched on next use)

### Common Operations

**List recent emails:**
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/v1.0/me/messages?\$top=10&\$select=subject,from,receivedDateTime,bodyPreview,hasAttachments&\$orderby=receivedDateTime desc"
```

**Search by sender:**
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/v1.0/me/messages?\$filter=contains(from/emailAddress/name,'NAME')&\$top=5&\$select=subject,from,receivedDateTime,body,hasAttachments&\$orderby=receivedDateTime desc"
```

**Search by subject:**
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/v1.0/me/messages?\$search=\"subject:KEYWORD\"&\$top=5&\$select=subject,from,receivedDateTime,body,hasAttachments"
```

**Read full email body:**
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/v1.0/me/messages/MESSAGE_ID?\$select=subject,from,toRecipients,receivedDateTime,body,hasAttachments"
```

**List attachments:**
```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://graph.microsoft.com/v1.0/me/messages/MESSAGE_ID/attachments"
```

**Send reply:**
```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://graph.microsoft.com/v1.0/me/messages/MESSAGE_ID/reply" \
  -d '{"comment": "Reply text here"}'
```

**Compose and send:**
```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://graph.microsoft.com/v1.0/me/sendMail" \
  -d '{"message": {"subject": "Subject", "body": {"contentType": "Text", "content": "Body"}, "toRecipients": [{"emailAddress": {"address": "user@example.com"}}]}}'
```

### Parsing Graph API HTML bodies

```python
import json, html, re

data = json.load(sys.stdin)
msgs = data.get('value', [data])
for m in msgs:
    body = m.get('body', {}).get('content', '')
    text = re.sub(r'<[^>]+>', ' ', body)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    # IRM check
    is_irm = (
        not body.strip() or
        'Information Rights Management' in body or
        'This message is protected' in body or
        len(body.strip()) < 50
    )
    if is_irm:
        print('IRM DETECTED — falling back to OWA')
        break
    print(f"From: {m['from']['emailAddress']['name']} <{m['from']['emailAddress']['address']}>")
    print(f"Date: {m['receivedDateTime']}")
    print(f"Subject: {m['subject']}")
    print(f"Body: {text[:3000]}")
```

## Method 2: OWA via Blueprint (fallback for IRM or expired Graph token)

### Dependencies

| Dependency | Required | How to get it |
|-----------|----------|---------------|
| Blueprint MCP | YES | `mcp__mcp-manager__mcpm(operation="start", server="blueprint")` |
| Chrome browser | YES | Must be running with Blueprint extension installed |
| OWA sign-in | YES | User must be signed into outlook.office.com in Chrome |

### Blueprint MCP

Browser automation layer. Connects to Chrome via extension.

- **Local path:** `ProjectsCL1/MCP/blueprint-extra-mcp/`
- **Key tools:** `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`, `browser_evaluate`
- **Relay mode:** Multiple Claude Code tabs auto-relay through port 5555

### Starting Blueprint
```
mcp__mcp-manager__mcpm(operation="start", server="blueprint")
```

### OWA Workflow

1. Navigate to OWA:
```
mcp__mcp-manager__mcpm(operation="call", server="blueprint", tool="browser_navigate", arguments={"url": "https://outlook.office.com/mail/"})
```

2. Snapshot to see inbox:
```
mcp__mcp-manager__mcpm(operation="call", server="blueprint", tool="browser_snapshot", arguments={})
```

3. Click email row using ref from snapshot:
```
mcp__mcp-manager__mcpm(operation="call", server="blueprint", tool="browser_click", arguments={"ref": "<ref-from-snapshot>"})
```

4. Snapshot again to read email body.

### OWA Navigation

| Action | URL / Method |
|--------|-------------|
| Inbox | `https://outlook.office.com/mail/` |
| Focused | `https://outlook.office.com/mail/focused` |
| Other | `https://outlook.office.com/mail/other` |
| Sent | `https://outlook.office.com/mail/sentitems` |
| Drafts | `https://outlook.office.com/mail/drafts` |
| Search | Click search bar, type query |
| Reply | Click Reply button in email view |
| Compose | Click "New mail" button |

### OWA DOM Tips

- Use `browser_snapshot` accessibility tree refs for clicking (more reliable than coordinates)
- IRM-protected emails show a lock icon but content is fully visible in OWA
- Reading pane shows on the right or bottom depending on layout

## Do NOT

- Do NOT use `az account get-access-token` for Graph API — az CLI is logged into joeltest.org, not corporate
- Do NOT use `client_credentials` grant without GPDH credentials — it won't have mail permissions
- Do NOT close the user's browser — Blueprint connects to existing Chrome
- Do NOT ask user to authenticate — OWA is already signed in, GPDH creds are in credential-manager
- Do NOT skip IRM detection — always check Graph API response before declaring an email unreadable
- Do NOT store tokens in plaintext files — use credential-manager
