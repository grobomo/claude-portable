# Container: Create Policy

Create a new Container Security runtime policy via API.

## API Method

```bash
# Create policy with runtime rules
python .claude/skills/v1-api/executor.py container_security_policies \
  name="<policy-name>" \
  description="<description>" \
  rules='[{"type":"podSecurityContext","action":"block","statement":{"properties":[{"key":"hostNetwork","value":"true"}]},"enabled":true}]'
```

## Common Policy Templates

### Log-Only (Monitoring)

All rules set to `log` -- observe without blocking. Good for initial deployment.

### Baseline Security

Block dangerous privileges, log everything else:
- Block: privileged containers, hostNetwork, hostPID
- Log: capabilities, port-forward, exec, secrets, malware, vulnerabilities

### Strict Production

Block most risky operations:
- Block: all podSecurityContext violations, privileged, capabilities beyond baseline
- Block: unscanned images, high/critical vulnerabilities
- Terminate: malware detected
- Log: port-forward, exec, secrets

## Modify Existing Policy

```bash
python .claude/skills/v1-api/executor.py update_container_security_policies \
  policy_id="<id>" \
  rules='[...]'
```

## Delete Policy

```bash
python .claude/skills/v1-api/executor.py delete_container_security_policies \
  policy_id="<id>"
```
