# Detection: Manage Models

Enable, disable, and review detection models.

## List Models

```bash
# All models with status
python .claude/skills/v1-api/executor.py list_dmm_models
```

## Model States

| Field | Values | Meaning |
|-------|--------|---------|
| enabled | true/false | Whether the model actively generates detections |
| available | true/false | Whether required products are connected |
| modelType | TI, SAE | Threat Intel or Search & Analytics Engine |
| riskLevel | Low, Medium, High, Critical | Alert severity when triggered |

## Enable/Disable Models (Browser Required)

Detection model enable/disable is done via the V1 console:

```
1. Navigate to XDR Threat Investigation > Detection Model Management
   mcpm call blueprint browser_lookup query="Detection Model Management"
   mcpm call blueprint browser_click selector="<result>"

2. Find the target model
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_lookup query="<model-name>"

3. Toggle the enable switch
   mcpm call blueprint browser_click selector="<toggle>"

4. Verify via API
   python .claude/skills/v1-api/executor.py list_dmm_models
```

## Notes

- Disabling a model stops NEW detections but does not remove existing alerts
- Models with `available: false` cannot generate detections regardless of `enabled` status
- The TI (Threat Intelligence) model should always be enabled
- SAE models are auto-updated by Trend Micro -- new models appear automatically
