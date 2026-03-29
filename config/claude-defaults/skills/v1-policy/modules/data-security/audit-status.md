# Data Security: Audit Status

Check data security deployment health and DLP state.

## API-Based Checks

No API available. All checks require browser automation.

## Browser-Based Checks

```
1. Navigate to Data Security > Overview
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_lookup query="Data Security"
   mcpm call blueprint browser_click selector="<data-security-menu>"
   mcpm call blueprint browser_take_screenshot
   -> Shows: data risk summary, active policies, recent incidents

2. Check DLP Policies
   Navigate to Data Security > DLP Policies
   mcpm call blueprint browser_take_screenshot
   -> Shows: policy list, status, scope

3. Check DLP Incidents
   Navigate to Data Security > DLP Incidents
   mcpm call blueprint browser_take_screenshot
   -> Shows: recent violations, severity, action taken

4. Check Data Discovery
   Navigate to Data Security > Data Discovery
   mcpm call blueprint browser_take_screenshot
   -> Shows: scan status, discovered data locations
```

## Health Check Criteria

| Check | Healthy | Unhealthy |
|-------|---------|-----------|
| DLP policies | Active policies configured | No policies |
| DLP incidents | Expected volume | Zero (might mean no policies) or spike |
| Data discovery | Scans running on schedule | Never scanned or scan errors |
| Classification | Rules applied to data | Not configured |
| Templates | Compliance templates enabled | No templates for required regs |
