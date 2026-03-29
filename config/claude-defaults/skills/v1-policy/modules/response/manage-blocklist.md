# Response: Manage Blocklist

Add and remove suspicious objects from the blocklist.

## Add to Blocklist

```bash
# Block an IP
python .claude/skills/v1-api/executor.py add_to_blocklist \
  ioc_type=ip value=192.168.1.100

# Block a domain
python .claude/skills/v1-api/executor.py add_to_blocklist \
  ioc_type=domain value=evil.com

# Block a URL
python .claude/skills/v1-api/executor.py add_to_blocklist \
  ioc_type=url value=http://evil.com/malware

# Block a file hash
python .claude/skills/v1-api/executor.py add_to_blocklist \
  ioc_type=fileSha256 value=<hash>

# Block an email sender
python .claude/skills/v1-api/executor.py add_to_blocklist \
  ioc_type=senderMailAddress value=bad@evil.com
```

## Remove from Blocklist

```bash
python .claude/skills/v1-api/executor.py delete_response_suspicious_objects_delete \
  ioc_type=<type> value=<value>
```

## Risk Levels

| Level | When to Use |
|-------|-------------|
| high | Confirmed malicious |
| medium | Suspicious, needs investigation |
| low | Precautionary block |

## Scan Actions

| Action | Use Case |
|--------|----------|
| block | Actively prevent (confirmed threat) |
| log | Monitor only (investigation phase) |

## Expiration

Blocks can be set with an expiration date or set to never expire.
Review and clean up expired/stale blocks regularly.
