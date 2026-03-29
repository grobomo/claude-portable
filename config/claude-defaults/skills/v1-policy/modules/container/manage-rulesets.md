# Container: Manage Rulesets

Create, modify, and manage Container Security rulesets.
Rulesets are reusable rule collections that can be attached to policies.

## List Rulesets

```bash
# All rulesets (custom + managed)
python .claude/skills/v1-api/executor.py list_container_security_rulesets

# Custom rulesets only
python .claude/skills/v1-api/executor.py list_container_security_custom_rulesets

# Trend-managed rules (auto-updated by Trend Micro)
python .claude/skills/v1-api/executor.py list_container_security_managed_rules
```

## Create Custom Ruleset

```bash
python .claude/skills/v1-api/executor.py container_security_rulesets \
  name="<ruleset-name>" \
  description="<description>" \
  rules='[...]'
```

## Modify Ruleset

```bash
python .claude/skills/v1-api/executor.py update_container_security_rulesets \
  ruleset_id="<id>" \
  rules='[...]'
```

## Delete Ruleset

```bash
python .claude/skills/v1-api/executor.py delete_container_security_rulesets \
  ruleset_id="<id>"
```

## Managed vs Custom

| Type | Source | Auto-Updated | Editable |
|------|--------|-------------|----------|
| Managed | Trend Micro | Yes (threat intel updates) | No |
| Custom | User-created | No | Yes |
