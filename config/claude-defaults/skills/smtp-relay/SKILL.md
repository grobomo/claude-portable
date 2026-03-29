---


name: smtp-relay
description: Send test emails via external VPS relay to bypass cloud provider port 25 blocks. Delivers directly to target SMTP hosts.
keywords:
  - email
  - smtp
  - relay
  - send
  - test
  - mail
  - ddei
  - tmes
  - port25
  - vps
  - racknerd
  - eml
  - inputemailtest


---

# SMTP Relay

Send test emails through an external VPS (e.g. RackNerd) to bypass AWS/Azure port 25 blocks. Delivers directly to a specified SMTP host, not via MX lookup.

## Why

Cloud providers (AWS, Azure, GCP) block outbound port 25 on VMs. Budget VPS providers (RackNerd, BuyVM) don't. This skill SSHes into a VPS and sends SMTP directly to a target mail host.

## Setup

### 1. Store VPS credentials (one-time)

```bash
# Store IP
python ~/.claude/skills/credential-manager/cred_cli.py store smtp-relay/VPS_IP --clipboard

# Store username (copy "root" to clipboard first)
python ~/.claude/skills/credential-manager/cred_cli.py store smtp-relay/VPS_USER --clipboard

# Store password
python ~/.claude/skills/credential-manager/cred_cli.py store smtp-relay/VPS_PASSWORD --clipboard
```

All three read from clipboard and clear it after storing. Claude never sees the values.

### 2. Verify setup

```bash
python ~/.claude/skills/smtp-relay/send.py --check
```

## Usage

### Send a simple test email

```bash
python ~/.claude/skills/smtp-relay/send.py \
  --from joel@joeltest.org \
  --to juan.mora@dole.com \
  --host dole.in.tmes.trendmicro.com \
  --subject "test"
```

### Send with body text

```bash
python ~/.claude/skills/smtp-relay/send.py \
  --from joel@joeltest.org \
  --to juan.mora@dole.com \
  --host dole.in.tmes.trendmicro.com \
  --subject "test" \
  --body "This is a test email."
```

### Send an .eml file

```bash
python ~/.claude/skills/smtp-relay/send.py \
  --from external@test.com \
  --to joel@joeltest.org \
  --host dole.in.tmes.trendmicro.com \
  --eml /path/to/sample.eml
```

### Send multiple copies

```bash
python ~/.claude/skills/smtp-relay/send.py \
  --from joel@joeltest.org \
  --to juan.mora@dole.com \
  --host dole.in.tmes.trendmicro.com \
  --subject "test" \
  --count 5
```

## Parameters

| Flag | Required | Description |
|------|----------|-------------|
| `--from` | Yes | Envelope sender (MAIL FROM) |
| `--to` | Yes | Envelope recipient (RCPT TO). Comma-separated for multiple. |
| `--host` | Yes | Target SMTP host to deliver to directly |
| `--port` | No | SMTP port (default: 25) |
| `--subject` | No | Email subject (default: "test") |
| `--body` | No | Email body text (default: "This is a test email.") |
| `--eml` | No | Send raw .eml file instead of generating a message |
| `--helo` | No | HELO hostname (default: "emailTester") |
| `--count` | No | Number of copies to send (default: 1) |
| `--check` | No | Verify VPS credentials and connectivity, don't send |
| `--debug` | No | Show full SMTP conversation |

## Credentials

Stored in OS credential store under service `claude-code`:

| Key | Value |
|-----|-------|
| `smtp-relay/VPS_IP` | VPS IP address |
| `smtp-relay/VPS_USER` | SSH username |
| `smtp-relay/VPS_PASSWORD` | SSH password |

## How It Works

1. Retrieves VPS credentials from OS keyring
2. SSHes into VPS via paramiko
3. Uploads a Python SMTP script to `/tmp/`
4. Executes it — connects directly to target SMTP host on port 25
5. Returns SMTP conversation output

## Requirements

- `paramiko` Python package (SSH)
- `keyring` Python package (credential store)
- VPS with outbound port 25 open
