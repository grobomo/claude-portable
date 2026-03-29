---

name: PM Report
description: Generate evidence-based technical analysis reports for Product Management audiences. PDF output with live proof, screenshots, coverage tables, priority rankings, and actionable recommendations.
keywords: [report, pm, product, management, analysis, gap, coverage, recommendation, evidence, pdf, document, executive, stakeholder, audit, assessment, parity, benchmark, readiness]
keywords:
  - whats
  - covered
  - evidence-based
  - technical
---

# PM Report Skill

Generate professional PDF reports that communicate technical findings to Product Management.

## When to Use

Any time the user needs a structured technical analysis delivered as a polished PDF:
- API gap analysis (what's missing, what works)
- Feature parity assessment (product A vs product B)
- Migration readiness review (what's ready, what blocks)
- Security posture audit (what's covered, what's exposed)
- Performance benchmark report (what meets SLA, what doesn't)
- Compliance gap analysis (what's compliant, what needs work)
- Integration assessment (what connects, what's manual)
- Platform maturity review (what's production-ready, what's not)

## The Report Formula

Every effective PM report follows this structure. This is non-negotiable:

```
INVESTIGATE  ->  COLLECT EVIDENCE  ->  RANK BY IMPACT  ->  SHOW PROOF  ->  RECOMMEND ACTIONS
```

### 1. Investigate (gather raw data)

Before writing anything, collect real evidence:
- Run live API calls / CLI commands / queries to get actual results
- Take screenshots of UIs, dashboards, consoles showing current state
- Gather documentation URLs that back up claims
- Identify what works AND what doesn't -- contrast is the story

### 2. Collect Evidence (organize proof)

Sort evidence into two piles:
- **Working** -- things that function correctly (green, proof of coverage)
- **Gaps** -- things that are missing, broken, or inadequate (red, proof of gap)

Each piece of evidence needs:
- What was tested (endpoint, command, feature)
- What happened (actual result, error, screenshot)
- What it proves (coverage exists / gap exists)

### 3. Rank by Impact (PM's language, not engineer's)

Rank findings by BUSINESS IMPACT, not technical complexity:
- How many customers/users are affected?
- How frequently is this encountered?
- How painful is the workaround?
- What's the cost of NOT fixing it?

Priority framework:
```
P1 (Critical)  -- Affects most users daily, no workaround or workaround is painful
P2 (High)      -- Affects many users weekly, partial workaround exists
P3 (Medium)    -- Affects some users occasionally, workaround is acceptable
P4 (Low)       -- Rare use case, adequate for now
```

### 4. Show Proof (evidence-first, not opinions)

For each finding, provide:
- **Contrast** -- show what WORKS next to what's BROKEN (side-by-side)
- **Live results** -- actual command output, API responses, error messages
- **Screenshots** -- visual proof of UI features that lack API/automation
- **Source links** -- official documentation URLs for verification

### 5. Recommend Actions (tiered, not "fix everything")

Group recommendations into 3 tiers:
- **Tier 1: Ship First** -- highest impact, blocks most users
- **Tier 2: High Demand** -- blocks specific important workflows
- **Tier 3: Growing Need** -- future-facing, get ahead of demand

## How to Use

### Quick Start

```
User: "analyze X and make a PM report"
```

Claude will:
1. Investigate the subject area (API calls, screenshots, research)
2. Collect and organize evidence into working/gap categories
3. Generate the PDF using the report engine

### With Arguments

```
/pm-report [subject]
```

Examples:
```
/pm-report V1 email security gap analysis
/pm-report AWS cost optimization opportunities
/pm-report ZTSA deployment readiness
/pm-report container security vs endpoint security feature parity
/pm-report identity security maturity assessment
```

### With Pre-Gathered Evidence

If evidence is already collected (screenshots in a folder, API results saved):

```
/pm-report --evidence-dir .tmp/my-evidence/ --subject "V1 API coverage"
```

## Report Engine

The report engine is at `generator.py`. It provides building blocks:

### Core Components

| Component | Purpose | When to Use |
|-----------|---------|-------------|
| `cover_page()` | Title, subtitle, date, tenant | Always -- first page |
| `executive_summary()` | Key findings as bullet points | Always -- page 2 |
| `coverage_table()` | Colored table with coverage levels | Feature parity, gap analysis |
| `coverage_bar_chart()` | ASCII bar chart showing ratios | Visual coverage comparison |
| `priority_section()` | Priority-ranked findings with evidence | Always -- the meat of the report |
| `evidence_block()` | API endpoint + result + status tag | API/CLI evidence |
| `screenshot_block()` | Embedded image with caption | UI/console evidence |
| `doc_link()` | Source URL with label | Citations throughout |
| `recommendations()` | Tiered action items | Always -- final section |
| `source_table()` | Full documentation reference table | Always -- last page |

### Evidence Types

| Type | Renderer | Input |
|------|----------|-------|
| API call result | `evidence_block(status="working")` | endpoint, result summary |
| API gap | `evidence_block(status="gap")` | endpoint, error/missing msg |
| Console screenshot | `screenshot_block()` | image path, caption |
| CLI output | `evidence_block()` | command, output |
| Documentation URL | `doc_link()` | label, URL |
| Metric/benchmark | `metric_block()` | name, value, target, status |

### Color Semantics

Consistent across all reports:
```
Green  (#2e7d32)  -- Working, covered, meeting target
Yellow (#f9a825)  -- Partial, medium coverage, approaching limit
Orange (#ef6c00)  -- Low coverage, below target
Red    (#b71c1c)  -- Gap, missing, broken, critical
Blue   (#0d47a1)  -- Headers, section titles, neutral info
Gray   (#888888)  -- Captions, metadata, timestamps
```

### Table Styles

| Style | Use For |
|-------|---------|
| `coverage_table` | Feature/API coverage with colored status column |
| `comparison_table` | Side-by-side product/feature comparison |
| `evidence_table` | Working vs gap evidence summary |
| `bridge_table` | How gaps are being addressed (interim solutions) |
| `source_table` | Documentation URLs with scope descriptions |

## Report Structure (Page Layout)

Standard page flow for any PM report:

```
Page 1     -- Cover (title, subtitle, date, scope)
Page 2     -- Table of Contents
Page 3     -- Executive Summary (key findings + hero screenshot)
Page 4     -- Methodology (how evidence was collected + source links)
Page 5-6   -- Coverage Overview (table + bar chart)
Page 7-N   -- Priority Findings (P1 through P4, each with evidence)
Page N+1   -- Evidence Summary (all working + all gaps, side by side)
Page N+2   -- Screenshots (visual evidence gallery)
Page N+3   -- Recommendations (3 tiers of action items)
Page N+4   -- Bridge/Interim Solutions (how gaps are handled today)
Page N+5   -- Source Documentation (URL reference table)
```

## Writing Style for PM Audiences

### DO
- Lead with impact, not technical details
- Use numbers: "7 of 17 sections have <20% coverage"
- Show contrast: "Container Security has 100% CRUD; Data Security has 0%"
- Use the word "cannot" to describe gaps: "Cannot create policies via API"
- Frame recommendations as business decisions: "Ship these 3 first"
- Include "workaround" for each gap -- PMs want to know interim state

### DO NOT
- Don't use jargon without context (explain CRUD, ZTSA, etc. on first use)
- Don't list technical specs without impact statements
- Don't say "should" -- say "recommend" with tier level
- Don't editorialize ("this is terrible") -- let the evidence speak
- Don't bury the lead -- worst gaps go first, not alphabetically

## File Structure

```
.claude/skills/pm-report/
  SKILL.md           -- This file (instructions + report formula)
  generator.py       -- PDF report engine (reportlab-based)
  templates/         -- Reusable report section templates
    cover.py         -- Cover page builder
    evidence.py      -- Evidence block builders (API, screenshot, metric)
    tables.py        -- Table builders (coverage, comparison, source)
    charts.py        -- Visual builders (bar chart, coverage chart)
    recommendations.py -- Tiered recommendation builder
```

## Automated QA Review (MANDATORY)

Every report is automatically reviewed by `claude -p` after PDF generation. The review checks:

| Check | What It Catches |
|-------|----------------|
| SENSITIVE DATA | Customer names, real IPs, AWS account IDs, API keys, credentials |
| ACCURACY | Claims without evidence, contradictions between sections |
| FORMATTING | Misaligned tables, missing captions, TOC/section mismatch |
| AUDIENCE | Jargon without context, missing impact statements |
| COMPLETENESS | Empty sections, TODO placeholders, missing promised evidence |

The review runs automatically on `report.build()` and saves results to `*_review.txt` alongside the PDF.

- **OVERALL: PASS** -- report is safe to share
- **OVERALL: FAIL** -- fix flagged issues before sharing

To skip review (e.g. during development): `report.build(review=False)`

### What Gets Flagged

Reports MUST NOT contain:
- Customer names (use "customer" or generic terms)
- Real person names other than the report author
- Internal hostnames or private IPs
- AWS account IDs, instance IDs
- API keys, tokens, passwords
- Lab tenant names that identify the org

## Dependencies

- `reportlab` (PDF generation -- already installed)
- `Pillow` / `PIL` (image handling for screenshots -- already installed)
- `claude` CLI (for automated QA review -- already installed)
- Screenshots collected via Blueprint MCP or filesystem

## Examples of Past Reports

| Report | Subject | Location |
|--------|---------|----------|
| V1 API Gap Analysis | 280 APIs vs 17 console sections | `reports/v1_api_gap_analysis_*.pdf` |
