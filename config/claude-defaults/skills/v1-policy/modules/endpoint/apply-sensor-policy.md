# Endpoint: Apply Sensor Policy Override

Override the default sensor policy settings for a specific endpoint.

## API Method

```bash
# Override sensor policy for a specific endpoint
python .claude/skills/v1-api/executor.py endpoint_security_endpoint_apply_sensor_policy \
  endpoint_id=<agentGuid> \
  policy_settings=<json>

# Remove override (revert to group policy)
python .claude/skills/v1-api/executor.py delete_endpoint_security_endpoint_remove_overridden_sensor_policy \
  endpoint_id=<agentGuid>
```

## Browser Method (Full Policy Editor)

For complex policy changes, use the V1 console:

```
1. Navigate to Endpoint Security > Sensor Policy
   mcpm call blueprint browser_lookup query="Sensor Policy"
   mcpm call blueprint browser_click selector="<result>"

2. Find the target policy (e.g., "Sensor Only General Policy")
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_lookup query="<policy-name>"

3. Click to edit
   mcpm call blueprint browser_click selector="<edit-link>"

4. Configure settings (Behavior Monitoring, ML, Web Rep, etc.)
   mcpm call blueprint browser_snapshot
   # Toggle each setting as needed

5. Save
   mcpm call blueprint browser_lookup query="Save"
   mcpm call blueprint browser_click selector="<save-button>"
```

## Use Cases

| Scenario | Action |
|----------|--------|
| Enable web reputation on one endpoint | API override with webReputation: enabled |
| Move endpoint from Sensor Only to SEP | Console: move to SEP group |
| Temporarily disable behavior monitoring | API override, then revert later |
| Pin endpoint to specific agent version | Version control policy change |
