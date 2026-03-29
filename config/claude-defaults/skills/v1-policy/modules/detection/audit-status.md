# Detection: Audit Status

Check detection model state, exceptions, and custom filters.

## Commands

```bash
# All detection models (enabled/disabled, risk levels)
python .claude/skills/v1-api/executor.py list_dmm_models

# Custom exceptions (false positive suppressions)
python .claude/skills/v1-api/executor.py list_dmm_exceptions

# Custom detection filters
python .claude/skills/v1-api/executor.py list_dmm_custom_filters

# Custom (user-created) detection models
python .claude/skills/v1-api/executor.py list_dmm_custom_models
```

## Health Check Criteria

| Check | Healthy | Unhealthy |
|-------|---------|-----------|
| TI model enabled | Yes | Disabled |
| SAE models available | Multiple enabled | All disabled or unavailable |
| Exceptions count | Low, well-documented | Many undocumented exceptions |
| Exception descriptions | Clear "why" documented | Empty descriptions |
