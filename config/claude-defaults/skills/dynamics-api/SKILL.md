---
name: dynamics-api
description: >
  Query Microsoft Dynamics 365 CRM via OData Web API through Blueprint browser automation.
  Covers cases, emails, accounts, contacts, Jira/PCT tickets, and activities.
keywords:
  - dynamics
  - crm
  - case
  - support
  - account
  - contact
  - hubble
  - pct
  - customer-service
  - tm-case
  - incident
---

# Dynamics 365 CRM API Skill

Query Dynamics CRM data using the OData Web API via Blueprint MCP browser automation. No API keys needed -- uses existing SSO browser session.

## Prerequisites

1. Blueprint MCP running: `mcpm start blueprint`
2. At least one browser tab open on `trendmicro.crm.dynamics.com` (any page works, even the SSO success popup)
3. User must be signed in to Dynamics via SSO

### If Blueprint is not available

This skill REQUIRES Blueprint MCP (Chrome extension). If Blueprint is not installed, not connected, or errors out:

1. **Check if Blueprint is registered:** `mcpm search blueprint`
2. **Start it:** `mcpm start blueprint`
3. **If extension disconnected:** Tell user to click the Blueprint extension icon in Chrome and click "Connect"
4. **If no Dynamics tab open:** Tell user to open any page on `trendmicro.crm.dynamics.com` in Chrome
5. **If SSO expired:** Navigate to the Dynamics tab and look for a "Sign in" dialog -- click it via JS to trigger SSO re-auth

There is NO standalone API fallback. Dynamics CRM uses Azure AD SSO with MFA -- there are no simple API keys. The browser session IS the auth mechanism.

If Blueprint cannot be made to work, the user must query Dynamics manually through the browser UI.

## Connection Pattern

```
# 1. Start Blueprint
mcpm enable client_id='lab-worker'

# 2. Find a Dynamics tab
mcpm browser_tabs action='list'
# Look for any tab on trendmicro.crm.dynamics.com

# 3. Attach to it (prefer lightweight pages like SSO popup over the full workspace)
mcpm browser_tabs action='attach' index=N

# 4. Verify connection
mcpm browser_evaluate expression="fetch('/api/data/v9.2/incidents?$top=1&$select=ticketnumber').then(r=>r.text()).then(t=>window._test=t).catch(e=>window._test='ERR:'+e.message);'go'"
mcpm browser_evaluate expression="window._test"
```

IMPORTANT: Prefer attaching to lightweight pages (SSO success popup, blank CRM pages). The full Customer Service workspace is heavy and causes Blueprint timeouts.

## Query Pattern

All queries use `browser_evaluate` with `.then()` chains. Store results on `window._varName`, then read separately.

```javascript
// Step 1: Fire the query
fetch("/api/data/v9.2/{entity}?{odata_params}", {
  headers: {
    'Accept': 'application/json',
    'OData-MaxVersion': '4.0',
    'OData-Version': '4.0'
  }
}).then(r => r.text())
  .then(t => window._result = t.substring(0, 4000))
  .catch(e => window._result = 'ERR:' + e.message);
'go'

// Step 2: Read the result
window._result || 'waiting'
```

CRITICAL: async/await does NOT work with Blueprint browser_evaluate. Always use `.then()` chains.

## Entity Reference

### Core Entities

| Entity | Collection Name | Key Fields |
|--------|----------------|------------|
| incident | `incidents` | ticketnumber, title, description, statuscode, prioritycode, createdon, modifiedon, _customerid_value |
| email | `emails` | subject, description, createdon, directioncode, _regardingobjectid_value |
| account | `accounts` | name, accountid, accountnumber |
| contact | `contacts` | fullname, emailaddress1, contactid |
| annotation | `annotations` | subject, notetext, createdon, _objectid_value |
| activitypointer | `activitypointers` | subject, activitytypecode, createdon, _regardingobjectid_value |

### Custom Entities (Trend Micro)

| Entity | Collection Name | Key Fields |
|--------|----------------|------------|
| crm_seg_jira_ticket | `crm_seg_jira_tickets` | crm_name, crm_ticket_number, crm_ticket_link, crm_task_status |
| crm_associate_seg_jira_ticket | `crm_associate_seg_jira_tickets` | _crm_case_value, _crm_seg_ticket_value, crm_name |
| crm_support_product | `crm_support_products` | (product catalog for cases) |
| crm_escalation | `crm_escalations` | (case escalation records) |

### Case -> Jira Ticket Relationship

Cases link to Jira/PCT tickets through a junction table:

```
incident (case)
    |
    |-- _incidentid (case GUID)
    v
crm_associate_seg_jira_tickets (junction)
    |-- _crm_case_value = incidentid
    |-- _crm_seg_ticket_value = jira ticket GUID
    v
crm_seg_jira_tickets (PCT ticket)
    |-- crm_name = "PCT-XXXXX"
    |-- crm_ticket_link = "https://trendmicro.atlassian.net/browse/PCT-XXXXX"
    |-- crm_task_status = "Open" / "Closed" / "Awaiting For Customer's Response"
```

### Key Custom Fields on Incident (Case)

| Field | Type | Description |
|-------|------|-------------|
| crm_case_summary | Memo | AI-generated case summary |
| crm_issue_category | Picklist | Issue category |
| crm_issue_sub_category | Picklist | Issue sub-category |
| crm_product_name | Lookup | Product (e.g., Trend Vision One) |
| crm_product_module | Picklist | Product module |
| crm_contactemail | String | Contact email address |
| crm_email_cc_recipients | Memo | CC recipients |
| crm_problem_description | Memo | Detailed problem description |
| crm_solution_provided | Memo | Solution text |
| crm_solution_provided_date | DateTime | When solution was provided |
| crm_sticky_notes | Memo | Internal sticky notes |
| crm_tenant_id | String | V1 tenant ID |
| crm_sfdccasenumber | String | Legacy SFDC case number |
| crm_non_seg_jira_id | String | Non-SEG Jira ticket ID |
| crm_malware_tip | String | Malware TIP reference |
| crm_autoclosestatus | String | Auto-close status |
| crm_case_support_region | String | Support region |
| crm_service_type | Picklist | Service type |
| crm_last_email_inbound_datetime | DateTime | Last customer email |
| crm_reopened | Boolean | Whether case was reopened |

### Status Codes (statuscode)

| Code | Meaning |
|------|---------|
| 1 | In Progress |
| 2 | Waiting for Customer Information |
| 3 | Waiting for Customer Verification |
| 4 | Research Required |
| 5 | Problem Resolved |
| 1000 | Merged |

### Email Direction

| directioncode | Meaning |
|---------------|---------|
| true | Outbound (Trend -> Customer) |
| false | Inbound (Customer -> Trend) |

## Working Query Examples

### Search case by ticket number

```javascript
fetch("/api/data/v9.2/incidents?$filter=ticketnumber eq 'TM-03900371'&$select=title,ticketnumber,description,statuscode,prioritycode,createdon,modifiedon,_customerid_value", {
  headers: {'Accept': 'application/json', 'OData-MaxVersion': '4.0', 'OData-Version': '4.0'}
}).then(r=>r.text()).then(t => window._case = t.substring(0,4000))
  .catch(e => window._case = 'ERR:'+e.message); 'go'
```

### Get last N emails for a case

Use the case's `incidentid` GUID (without quotes in the filter):

```javascript
fetch("/api/data/v9.2/emails?$filter=_regardingobjectid_value eq CASE_GUID_HERE&$select=subject,description,createdon,directioncode&$orderby=createdon desc&$top=3", {
  headers: {'Accept': 'application/json', 'OData-MaxVersion': '4.0', 'OData-Version': '4.0'}
}).then(r=>r.text()).then(t => window._emails = t.substring(0,6000))
  .catch(e => window._emails = 'ERR:'+e.message); 'go'
```

### Strip HTML from email body

```javascript
// After fetching emails, parse and strip HTML:
.then(r=>r.json()).then(d => {
  window._cleanEmails = JSON.stringify(d.value.map(e => ({
    subject: e.subject,
    date: e.createdon,
    dir: e.directioncode ? 'outbound' : 'inbound',
    body: (e.description||'').replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim().substring(0,500)
  })));
})
```

### Get PCT tickets for a case

Two-step: junction table lookup, then ticket details.

```javascript
// Step 1: Find associated ticket GUIDs
fetch("/api/data/v9.2/crm_associate_seg_jira_tickets?$filter=_crm_case_value eq CASE_GUID_HERE&$select=crm_name,_crm_seg_ticket_value", {
  headers: {'Accept': 'application/json', 'OData-MaxVersion': '4.0', 'OData-Version': '4.0'}
}).then(r=>r.text()).then(t => window._assoc = t.substring(0,2000))
  .catch(e => window._assoc = 'ERR:'+e.message); 'go'

// Step 2: Get ticket details (use _crm_seg_ticket_value from step 1)
fetch("/api/data/v9.2/crm_seg_jira_tickets(TICKET_GUID)?$select=crm_name,crm_ticket_number,crm_ticket_link,crm_task_status", {
  headers: {'Accept': 'application/json', 'OData-MaxVersion': '4.0', 'OData-Version': '4.0'}
}).then(r=>r.text()).then(t => window._pct = t.substring(0,1000))
  .catch(e => window._pct = 'ERR:'+e.message); 'go'
```

### Search accounts by name

```javascript
fetch("/api/data/v9.2/accounts?$filter=contains(name,'Company 3')&$select=name,accountid,accountnumber&$top=5", {
  headers: {'Accept': 'application/json', 'OData-MaxVersion': '4.0', 'OData-Version': '4.0'}
}).then(r=>r.text()).then(t => window._accounts = t.substring(0,2000))
  .catch(e => window._accounts = 'ERR:'+e.message); 'go'
```

### List all activities for a case

```javascript
fetch("/api/data/v9.2/activitypointers?$filter=_regardingobjectid_value eq CASE_GUID_HERE&$select=subject,activitytypecode,createdon,statecode&$orderby=createdon desc&$top=10", {
  headers: {'Accept': 'application/json', 'OData-MaxVersion': '4.0', 'OData-Version': '4.0'}
}).then(r=>r.text()).then(t => window._activities = t.substring(0,4000))
  .catch(e => window._activities = 'ERR:'+e.message); 'go'
```

### Get case notes/annotations

```javascript
fetch("/api/data/v9.2/annotations?$filter=_objectid_value eq CASE_GUID_HERE&$select=subject,notetext,createdon&$orderby=createdon desc&$top=5", {
  headers: {'Accept': 'application/json', 'OData-MaxVersion': '4.0', 'OData-Version': '4.0'}
}).then(r=>r.text()).then(t => window._notes = t.substring(0,4000))
  .catch(e => window._notes = 'ERR:'+e.message); 'go'
```

### Parallel queries (fire multiple, read all at once)

```javascript
// Fire all queries in one browser_evaluate call:
fetch("...query1...").then(r=>r.text()).then(t => window._r1 = t.substring(0,3000)).catch(e => window._r1 = 'ERR:'+e.message);
fetch("...query2...").then(r=>r.text()).then(t => window._r2 = t.substring(0,3000)).catch(e => window._r2 = 'ERR:'+e.message);
fetch("...query3...").then(r=>r.text()).then(t => window._r3 = t.substring(0,3000)).catch(e => window._r3 = 'ERR:'+e.message);
'go'

// Read all results in one call:
JSON.stringify({r1: window._r1, r2: window._r2, r3: window._r3})
```

## Entity Discovery (finding unknown entities)

Dynamics metadata API does not support `contains()`, `startswith()`, or range filters (`ge`/`le`) on EntityDefinitions. To find custom entities, fetch ALL and filter client-side:

```javascript
fetch("/api/data/v9.2/EntityDefinitions?$select=LogicalName,LogicalCollectionName", {
  headers: {'Accept': 'application/json', 'OData-MaxVersion': '4.0', 'OData-Version': '4.0'}
}).then(r=>r.json()).then(d => {
  const crm = d.value
    .filter(e => e.LogicalName.startsWith('crm_'))
    .map(e => e.LogicalName + '|' + e.LogicalCollectionName);
  window._allEntities = JSON.stringify(crm);
}).catch(e => window._allEntities = 'ERR:'+e.message); 'go'
```

To get all custom fields on an entity:

```javascript
fetch("/api/data/v9.2/EntityDefinitions(LogicalName='incident')/Attributes?$select=LogicalName,AttributeTypeName&$filter=IsCustomAttribute eq true", {
  headers: {'Accept': 'application/json', 'OData-MaxVersion': '4.0', 'OData-Version': '4.0'}
}).then(r=>r.json()).then(d => {
  window._fields = JSON.stringify(d.value.map(a => a.LogicalName + '|' + a.AttributeTypeName.Value));
}).catch(e => window._fields = 'ERR:'+e.message); 'go'
```

## Best Practices

1. **Attach to lightweight pages** - The SSO success popup or a blank CRM page is ideal. The full Customer Service workspace causes Blueprint timeouts and disconnections.

2. **Always use .then() chains** - async/await silently returns `{}` from browser_evaluate. This is a Blueprint CDP limitation.

3. **Always use $select** - Minimize response size. Dynamics entities have 100+ fields.

4. **Always .substring(0, N)** - CDP has message size limits. Use 3000-6000 for most queries, up to 8000 for email bodies.

5. **GUIDs go unquoted in filters** - `_regardingobjectid_value eq 84747f2a-ca0d-f111-8407-000d3a1548b3` (no quotes around the GUID).

6. **Ticketnumbers need quotes** - `ticketnumber eq 'TM-03900371'` (single quotes).

7. **Fire queries in parallel** - Multiple fetch calls in one browser_evaluate, read all results in a second call. Dramatically faster than sequential.

8. **Handle session expiry** - If queries return HTML instead of JSON, the session expired. Find and click the "Sign in" button via JS:
   ```javascript
   document.querySelector('#confirmButton_13')?.click()
   ```
   Then wait 3-5 seconds for SSO to complete.

9. **Email HTML stripping** - Email descriptions contain HTML. Use `.replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim()` to extract plain text.

10. **Use $expand sparingly** - Navigation properties are hard to guess. The junction table approach (two queries) is more reliable than `$expand`.

## Bonus: Querying Jira PCT Tickets via Browser

The jira-lite MCP may not have access to restricted Jira projects (e.g., PCT). But you can query the Jira REST API directly from a browser tab on `trendmicro.atlassian.net` since SSO gives full access.

```javascript
// Attach to any Atlassian tab, then:

// Get last 2 comments on a PCT ticket
fetch('/rest/api/3/issue/PCT-XXXXX/comment?orderBy=-created&maxResults=2', {
  headers: {'Accept': 'application/json'}
}).then(r=>r.json()).then(d => {
  window._comments = JSON.stringify(d.comments.map(c => ({
    author: c.author.displayName,
    date: c.created,
    text: c.body.content.map(p => p.content ? p.content.map(t => t.text || '').join('') : '').join('\n')
  })));
}).catch(e => window._comments = 'ERR:'+e.message); 'go'

// Get PCT ticket details
fetch('/rest/api/3/issue/PCT-XXXXX?fields=summary,status,assignee,priority,comment', {
  headers: {'Accept': 'application/json'}
}).then(r=>r.text()).then(t => window._pctIssue = t.substring(0,4000))
  .catch(e => window._pctIssue = 'ERR:'+e.message); 'go'
```

This works because browser SSO has broader permissions than API tokens. Use this when jira-lite returns 404 on restricted projects.

## Common Pitfalls

- **browser_interact clicks fail on Dynamics** - Dynamics uses heavy React/Fluent UI. Use `browser_evaluate` + JS `.click()` instead of coordinate clicks.
- **Tab indices shift** - Browser tabs reorder when windows open/close. Always re-list tabs after reconnecting.
- **EntityDefinitions queries are limited** - Most filter functions (contains, startswith, ge/le) don't work on metadata. Fetch all and filter in JS.
- **Junction tables for relationships** - Case-to-Jira uses `crm_associate_seg_jira_tickets` as a junction. There's no direct `$expand` navigation property.
- **Empty _crm_related_case_value** - The `crm_seg_jira_tickets` entity has a `_crm_related_case_value` field but it's often null. Use the junction table instead.

## Quick Reference: Full Case Lookup Script

Complete script to get a case with emails, PCT ticket, and activities:

```javascript
// === STEP 1: Get case by ticket number ===
fetch("/api/data/v9.2/incidents?$filter=ticketnumber eq 'TM-XXXXXXXX'&$select=title,ticketnumber,description,statuscode,prioritycode,createdon,incidentid,_customerid_value,crm_contactemail,crm_case_summary,crm_sticky_notes", {
  headers: {'Accept': 'application/json', 'OData-MaxVersion': '4.0', 'OData-Version': '4.0'}
}).then(r=>r.json()).then(d => {
  window._case = d.value[0];
  const id = window._case.incidentid;

  // === STEP 2: Get emails, PCT, activities in parallel ===
  fetch("/api/data/v9.2/emails?$filter=_regardingobjectid_value eq " + id + "&$select=subject,createdon,directioncode&$orderby=createdon desc&$top=5", {
    headers: {'Accept': 'application/json', 'OData-MaxVersion': '4.0', 'OData-Version': '4.0'}
  }).then(r=>r.json()).then(d => window._emails = d.value);

  fetch("/api/data/v9.2/crm_associate_seg_jira_tickets?$filter=_crm_case_value eq " + id + "&$select=_crm_seg_ticket_value", {
    headers: {'Accept': 'application/json', 'OData-MaxVersion': '4.0', 'OData-Version': '4.0'}
  }).then(r=>r.json()).then(d => {
    if (d.value.length > 0) {
      const tid = d.value[0]._crm_seg_ticket_value;
      fetch("/api/data/v9.2/crm_seg_jira_tickets(" + tid + ")?$select=crm_name,crm_ticket_link,crm_task_status", {
        headers: {'Accept': 'application/json', 'OData-MaxVersion': '4.0', 'OData-Version': '4.0'}
      }).then(r=>r.json()).then(t => window._pct = t);
    } else { window._pct = null; }
  });

  fetch("/api/data/v9.2/activitypointers?$filter=_regardingobjectid_value eq " + id + "&$select=subject,activitytypecode,createdon&$orderby=createdon desc&$top=5", {
    headers: {'Accept': 'application/json', 'OData-MaxVersion': '4.0', 'OData-Version': '4.0'}
  }).then(r=>r.json()).then(d => window._activities = d.value);
}).catch(e => window._caseErr = e.message); 'go'

// === STEP 3: Read all results ===
JSON.stringify({
  case: window._case ? {title: window._case.title, status: window._case.statuscode, desc: (window._case.description||'').substring(0,300)} : null,
  emails: window._emails ? window._emails.map(e => ({subject: e.subject, date: e.createdon, dir: e.directioncode ? 'out' : 'in'})) : null,
  pct: window._pct,
  activities: window._activities ? window._activities.map(a => ({subject: a.subject, type: a.activitytypecode, date: a.createdon})) : null,
  error: window._caseErr || null
})
```
