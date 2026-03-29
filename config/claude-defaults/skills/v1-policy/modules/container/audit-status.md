# Container: Audit Status

Check Container Security policies, rulesets, clusters, and compliance state.

## Commands

```bash
# Policies with full rule details
python .claude/skills/v1-api/executor.py list_container_security_policies

# All rulesets
python .claude/skills/v1-api/executor.py list_container_security_rulesets

# Managed (Trend-provided) rules
python .claude/skills/v1-api/executor.py list_container_security_managed_rules

# K8s clusters
python .claude/skills/v1-api/executor.py list_k8s_clusters

# ECS clusters
python .claude/skills/v1-api/executor.py list_container_security_amazon_ecs_clusters

# Compliance scan config and results
python .claude/skills/v1-api/executor.py list_container_security_compliance_scan_configuration
python .claude/skills/v1-api/executor.py list_container_security_compliance_scan_summary

# Container vulnerabilities
python .claude/skills/v1-api/executor.py list_container_vulns
```

## Health Check Criteria

| Check | Healthy | Unhealthy |
|-------|---------|-----------|
| At least 1 policy exists | Yes (LogOnlyPolicy) | No policies defined |
| Clusters connected | 1+ K8s or ECS | 0 clusters |
| Runtime rules enabled | All 11 rules active | Rules disabled |
| Compliance scan recent | Within 7 days | Never run or stale |
| Unscanned images | 0 | Images without vulnerability scan |
