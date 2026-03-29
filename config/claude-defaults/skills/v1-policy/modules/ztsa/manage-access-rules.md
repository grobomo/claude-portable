# ZTSA: Manage Access Rules

Create and manage Secure Access Rules via browser automation.

**NO API AVAILABLE** -- All operations require Blueprint.

## List Current Rules

```bash
# Only log data available via API
python .claude/skills/v1-api/executor.py search_network_logs hours=24 limit=10
```

## Create Access Rule (Browser)

```
1. Navigate to Zero Trust Secure Access > Secure Access Rules
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_lookup query="Secure Access Rules"
   mcpm call blueprint browser_click selector="<result>"

2. Click "Add Rule"
   mcpm call blueprint browser_snapshot
   mcpm call blueprint browser_lookup query="Add"
   mcpm call blueprint browser_click selector="<add-button>"

3. Configure rule:
   a. Rule name and description
   b. Select users/groups
   c. Select applications or URL categories
   d. Set action (Allow / Block / Monitor)
   e. Configure schedule (optional)
   f. Set risk conditions (optional)

4. Save rule
   mcpm call blueprint browser_lookup query="Save"
   mcpm call blueprint browser_click selector="<save-button>"

5. Verify rule appears in list
   mcpm call blueprint browser_take_screenshot
```

## Edit Access Rule (Browser)

```
1. Navigate to Secure Access Rules
2. Click the rule name to open editor
3. Modify settings
4. Save
```

## Delete Access Rule (Browser)

```
1. Navigate to Secure Access Rules
2. Select rule checkbox
3. Click Delete
4. Confirm deletion
```

## Rule Templates

### Allow Corporate Apps
- Users: All domain users
- Applications: Internal app list
- Action: Allow
- Risk: Any

### Block High-Risk Cloud Apps
- Users: All
- Applications: Unsanctioned cloud apps category
- Action: Block
- Risk: Any

### Monitor Sensitive Data Access
- Users: Non-admin users
- Applications: File sharing, code repos
- Action: Monitor
- Risk: Medium+
