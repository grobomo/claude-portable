# Weekly Update Plugin - Development Plan

## Current State

**Location:** `/home/claude/.claude\skills\weekly-update\`
**Status:** Local skill, testing phase

### Files
```
weekly-update/
├── SKILL.md        # Core skill documentation (complete)
└── PLAN.md         # This file
```

### Registered In
`/home/claude/.claude\hooks\skill-registry.json`

---

## Phase 1: Testing & Refinement (Current)

### Goal
Test the skill with Joel's actual weekly update PowerPoint and refine the workflow.

### Test PowerPoint
`/home/claude\OneDrive - TrendMicro\Documents\_Companies\gm2spg-weeklyupdate-jan26.pptx`

### TA Role Focus (Joel's Role)
| Slide | Section | Test Status |
|-------|---------|-------------|
| 5 | Customer Health table | [ ] |
| 5 | Risk Type / Next Steps | [ ] |
| 8 | Platform Adoption Scorecard | [ ] |
| 8 | V1 Adoption % | [ ] |
| 8 | Integrations count | [ ] |
| 9-11 | Sales Motions - TA column | [ ] |

### Refinements Needed
- [ ] Test reading current PowerPoint gaps
- [ ] Test question flow for TA data gathering
- [ ] Determine best output format (table vs prose)
- [ ] Add scripts for common operations (if needed)
- [ ] Document any edge cases discovered

### Known Template Structure
- Slide 3: Weekly Executive Snapshot (multi-role)
- Slide 5: Customer Health & Coverage (TA primary)
- Slide 6: Pipeline & New Projects (SE/Rep primary)
- Slide 8: Platform Adoption Scorecard (TA primary)
- Slides 9-11: Sales Motions Execution Matrix (all roles, role-specific columns)
- Slides 12-13: Help Needed (all roles)

---

## Phase 2: Add Supporting Scripts

### Potential Scripts
```
weekly-update/
├── scripts/
│   ├── extract-gaps.py      # Parse PPTX, find incomplete cells
│   ├── validate-health.py   # Check health status format (G/Y/R)
│   └── format-output.py     # Generate table-formatted updates
```

### Script Ideas
1. **Gap Extractor** - Scan PPTX XML for `?` placeholders, empty cells, "A B C" patterns
2. **Role Filter** - Given role, return only relevant slide sections
3. **Update Formatter** - Take user input, format as slide-ready tables

---

## Phase 3: Convert to Shareable Plugin

### Target Structure
```
weekly-update-plugin/
├── .claude-plugin/
│   └── plugin.json
├── skills/
│   └── weekly-update/
│       ├── SKILL.md
│       ├── references/
│       │   └── slide-structure.md
│       └── scripts/
│           └── extract-gaps.py
├── README.md
└── LICENSE
```

### plugin.json
```json
{
  "name": "weekly-update",
  "displayName": "Weekly Update PowerPoint Helper",
  "description": "Helps squad members (TA, SE, Sales Rep) fill out weekly update PowerPoints",
  "version": "1.0.0",
  "skills": ["skills/weekly-update"]
}
```

### Distribution Options
1. **Git repo** - Clone/install via `cc plugin install <repo-url>`
2. **Local share** - Copy folder to teammate's `~/.claude/plugins/`
3. **Marketplace** - Submit to claude-code-plugins if broadly useful

---

## Phase 4: Team Rollout

### Prerequisites for Teammates
1. Claude Code installed
2. Plugin installed (git clone or folder copy)
3. Brief training on trigger keywords

### Customization Points
- Role selection (TA/SE/Rep)
- Template variations (if different teams use different formats)
- Company-specific terminology

---

## Quick Reference

### Trigger Keywords
`weekly update`, `weekly status`, `squad update`, `fill out slides`, `ta slides`, `se slides`, `sales rep slides`, `customer health slide`, `platform adoption`, `sales motions`

### Role Mapping
| Role | Primary Slides | Key Data |
|------|----------------|----------|
| TA | 5, 8, 9-11 | Health, Adoption, Integrations |
| SE | 3, 6, 9-11 | Demos, POVs, Competitors |
| Rep | 3, 6, 9-11 | Wins, Forecast, Pipeline |

---

## Session Notes

### 2025-01-26
- Created initial SKILL.md with role-aware workflow
- Registered in skill-registry.json
- Analyzed template structure from `gm2spg-weeklyupdate-jan26.pptx`
- Identified incomplete slides: 5, 8, 9-11, 12-13

### Next Session
- Test TA workflow with actual data
- Refine question flow based on real usage
- Add scripts if manual extraction is tedious
