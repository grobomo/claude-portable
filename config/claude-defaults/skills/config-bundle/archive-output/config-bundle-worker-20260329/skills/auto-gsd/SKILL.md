---
name: auto-gsd
description: Auto-GSD task tracking and planning workflow
keywords:
  - gsd
  - planning
  - tracking
  - roadmap
  - milestone
---

<objective>
Enforce GSD task tracking for ALL work. No exceptions.

SLOW AND ACCURATE > FAST AND WRONG

Claude naturally wants to skip steps to be "helpful" - this is wrong.
Every task must have PLAN.md with success criteria BEFORE any tool execution.
</objective>

<rules>
## Non-Negotiable

1. **ANY tool use requires PLAN.md** - No exceptions for "small" or "obvious" tasks
2. **Create plan BEFORE execution** - gsd-gate.js blocks Bash|Write|Edit|Task|WebFetch until PLAN.md exists
3. **Define success criteria** - How will you VERIFY the task is complete?
4. **Verify against criteria** - Not just "I ran the commands"

## What You Must Do

BEFORE any task:
```bash
mkdir -p .planning/quick/NNN-task-slug/
# Write NNN-PLAN.md with Goal + Success Criteria + Tasks
```

AFTER task:
```bash
# Write NNN-SUMMARY.md documenting what was done
# Verify each criterion was met
# Update STATE.md completion table
```

## PLAN.md Format

```markdown
# Quick Task NNN: [Task Name]

## Goal
[What needs to happen - be specific]

## Success Criteria
- [ ] Criterion 1 (how to verify)
- [ ] Criterion 2 (how to verify)
- [ ] Criterion 3 (how to verify)

## Tasks
1. Step one
2. Step two
3. Step three
```

## Gated Tools

These tools are BLOCKED until PLAN.md exists:
- Bash (execution commands)
- Write (creating files)
- Edit (modifying files)
- Task (spawning agents)
- WebFetch (external requests)

These tools are ALLOWED for research:
- Read, Glob, Grep (finding information)
</rules>

<failure_modes>
Without enforcement, Claude will:
- Declare work "done" without verification
- Skip planning because "it's obvious"
- Run commands without defining success criteria
- Lose track of what was accomplished
- Context resets lose all progress
</failure_modes>
