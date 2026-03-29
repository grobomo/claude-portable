# AI Security: Audit Status

Check AI security deployment health and guardrail state.

## API-Based Checks

```bash
# Test guardrail evaluation (the only API available)
python .claude/skills/v1-api/executor.py ai_security_apply_guardrails \
  messages='[{"role":"user","content":"test message"}]'
```

## Browser-Based Checks

```
1. Navigate to AI Security > Overview
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_lookup query="AI Security"
   mcpm call blueprint browser_click selector="<ai-security-menu>"
   mcpm call blueprint browser_take_screenshot
   -> Shows: AI usage summary, blocked attempts, active policies

2. Check AI Service Access Control
   Navigate to AI Security > AI Service Access Control
   mcpm call blueprint browser_take_screenshot
   -> Shows: allowed/blocked AI services, policy rules

3. Check Guardrail Configuration
   Navigate to AI Security > AI Application Security
   mcpm call blueprint browser_take_screenshot
   -> Shows: guardrail rules, detection settings

4. Check AI Usage
   Navigate to AI Security > AI Usage Monitoring
   mcpm call blueprint browser_take_screenshot
   -> Shows: which AI services are used, by whom, volume
```

## Health Check Criteria

| Check | Healthy | Unhealthy |
|-------|---------|-----------|
| AI access policies | Policies configured and active | No policies |
| Guardrails | Rules configured for sensitive topics | Default/unconfigured |
| Usage monitoring | Tracking active | Not configured |
| Shadow AI detection | Unapproved services flagged | Not enabled |
| Data leakage prevention | PII/code filters active | Filters off |
