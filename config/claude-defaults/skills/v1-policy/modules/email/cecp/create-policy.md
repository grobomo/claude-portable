# CECP: Create Threat Protection Policy

Create a new CECP scanning policy with 6 configurable modules.

## Policy Modules

| Module | What It Does | Key Settings |
|--------|-------------|-------------|
| Advanced Spam Protection | Spam/phishing filtering | Detection level, quarantine actions, sender lists |
| Anti-Malware Scanning | File-based threat detection | ML + pattern, attachment scanning |
| Web Reputation | URL safety checking | Risk threshold, blocked/allowed URLs |
| Data Loss Prevention | Sensitive data leakage | Compliance templates (HIPAA, PCI, GDPR), custom rules |
| Virtual Analyzer | Cloud sandbox detonation | File types, timeout, URL analysis |
| Content Filtering | Attachment control | Blocked extensions, size limits, macro blocking |

## Workflow

```
1. Navigate to Email & Collaboration Security > Policies
   mcpm call blueprint browser_lookup query="Policies"
   mcpm call blueprint browser_click selector="<result>"
   mcpm call blueprint browser_evaluate code="await new Promise(r => setTimeout(r, 3000))"

2. Click "Add Policy"
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_lookup query="Add Policy"
   mcpm call blueprint browser_click selector="<add-button>"
   mcpm call blueprint browser_evaluate code="await new Promise(r => setTimeout(r, 2000))"

3. Enter policy name
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_type selector="<name-input>" text="<policy-name>"

4. Configure each module:
   For each module:
   a. Read docs first:
      python .claude/skills/trend-docs/executor.py "<doc-slug>" --max-pages 2
   b. Navigate to module tab
      mcpm call blueprint browser_lookup query="<module-name>"
      mcpm call blueprint browser_click selector="<module-tab>"
   c. Set each field per requirements
      mcpm call blueprint browser_snapshot
      # Configure settings...
   d. Screenshot for confirmation
      mcpm call blueprint browser_take_screenshot

5. Save policy
   mcpm call blueprint browser_lookup query="Save"
   mcpm call blueprint browser_click selector="<save-button>"

6. Assign to accounts (see assign-policy.md)
```

## Documentation Slugs

| Module | Doc Slug |
|--------|----------|
| Anti-Spam | `trend-vision-one-advanced-spam-protection` |
| Anti-Malware | `trend-vision-one-anti-malware-scanning` |
| Web Reputation | `trend-vision-one-web-reputation` |
| DLP | `trend-vision-one-data-loss-prevention` |
| Virtual Analyzer | `trend-vision-one-virtual-analyzer-cemp` |
| Content Filtering | `trend-vision-one-content-filtering` |
| Policy Management | `trend-vision-one-manage-policies-cecp` |
