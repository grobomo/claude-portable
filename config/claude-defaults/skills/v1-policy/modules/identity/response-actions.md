# Identity Security: Response Actions

Automated identity response actions available via API.

## Disable User Account

```bash
python .claude/skills/v1-api/executor.py response_domain_accounts_disable \
  account_name="user@domain.com" \
  description="Compromised credentials detected"
```

## Enable User Account

```bash
python .claude/skills/v1-api/executor.py response_domain_accounts_enable \
  account_name="user@domain.com" \
  description="Investigation complete, account cleared"
```

## Force Password Reset

```bash
python .claude/skills/v1-api/executor.py response_domain_accounts_reset_password \
  account_name="user@domain.com" \
  description="Password found in breach database"
```

## Force Sign Out

```bash
python .claude/skills/v1-api/executor.py response_domain_accounts_sign_out \
  account_name="user@domain.com" \
  description="Suspicious session detected"
```

## Check Response Task Status

```bash
# After any response action, check the task
python .claude/skills/v1-api/executor.py get_task task_id=<returned-task-id>
```

## Response Playbook: Compromised Account

```
1. Force sign out (immediate containment)
   response_domain_accounts_sign_out account_name="user@domain.com"

2. Force password reset
   response_domain_accounts_reset_password account_name="user@domain.com"

3. If severe: disable account
   response_domain_accounts_disable account_name="user@domain.com"

4. Search for lateral movement
   search_identity_logs hours=72 filter="accountName:user@domain.com"

5. Check endpoints the user accessed
   search_endpoint_logs hours=72 filter="logonUser:user"
```
