# Endpoint: Version Control

Manage agent update policies -- which agent builds endpoints receive and when.

## Current State (2026-03-02)

- **Policy:** Default (single policy covering all 24 endpoint groups)
- **Update setting:** n-1 (one version behind latest)
- **Available versions:** n, n-1, n-2, or pinned monthly (202601 back to 202501)

## Commands

```bash
# List version control policies and groups
python .claude/skills/v1-api/executor.py list_policies

# List available agent versions
python .claude/skills/v1-api/executor.py list_endpoint_security_version_control_policies_agent_update_policies

# Get priority order of version control policies
python .claude/skills/v1-api/executor.py list_endpoint_security_version_control_policy_priorities

# Delete a custom version control policy
python .claude/skills/v1-api/executor.py delete_endpoint_security_version_control_policies policy_id=<id>
```

## Version Options

| Version | Meaning | Risk |
|---------|---------|------|
| n | Latest available build | Newest features, least tested in production |
| n-1 | One version behind (default) | Balance of features and stability |
| n-2 | Two versions behind | Most conservative, may miss security fixes |
| 202601 | Pinned to January 2026 build | Full control, no auto-updates |

## Create Custom Policy (Browser Required)

```
1. Navigate to Endpoint Security > Version Control
   mcpm call blueprint browser_lookup query="Version Control"
   mcpm call blueprint browser_click selector="<result>"

2. Click "Add Policy"
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_lookup query="Add Policy"
   mcpm call blueprint browser_click selector="<add-button>"

3. Name the policy, select target groups, choose version
   mcpm call blueprint browser_snapshot
   # Fill form fields

4. Save and verify
   python .claude/skills/v1-api/executor.py list_policies
```
