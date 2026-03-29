# Spec: Spec Kit + GSD Integration for CCC Fleet

## Problem Statement

CCC workers receive tasks via relay as raw text prompts (`claude -p "do X"`). There's no structured planning, no success criteria, and no verification. Workers sometimes declare work "done" without testing, skip edge cases, or produce code that doesn't match the request. The dispatcher has no way to validate quality before marking tasks complete.

## Solution

Integrate Spec Kit (specification) and GSD (enforcement) into the CCC fleet pipeline:

1. **Dispatcher creates the spec** — when a task arrives via the bridge, the dispatcher runs Spec Kit's specify + plan + tasks workflow to produce structured `.specs/` artifacts before dispatching to a worker.
2. **Workers execute with GSD enforcement** — workers have GSD hooks installed that block execution tools until a PLAN.md exists. The worker reads the dispatcher-generated spec and creates its GSD plan from it, then implements against the spec's success criteria.
3. **Verification against spec** — after implementation, the worker verifies each success criterion from the spec before marking the task complete.

## Architecture

```
Bridge task (raw text)
  |
  v
Dispatcher:
  1. Pulls task from bridge pending/
  2. Runs spec-kit: specify -> plan -> tasks (using claude -p with speckit prompts)
  3. Commits .specs/<task-slug>/ to worker's branch
  4. Dispatches to worker with: "implement .specs/<task-slug>/ using GSD"
  |
  v
Worker:
  1. Receives task + .specs/ artifacts
  2. GSD gate blocks until PLAN.md created
  3. Worker reads spec, creates GSD PLAN.md with criteria from spec
  4. Implements code against spec
  5. Verifies each criterion
  6. PRs to altarr/boothapp
```

## Components to Build

### 1. Dispatcher Spec Generator (`scripts/spec-generate.sh`)
- Input: raw task text from bridge JSON
- Runs `claude -p` with the speckit.specify prompt template to generate spec.md
- Runs `claude -p` with the speckit.plan prompt template to generate plan.md
- Runs `claude -p` with the speckit.tasks prompt template to generate tasks.md
- Outputs: `.specs/<task-slug>/` directory with all three files
- Timeout: 5 minutes max for spec generation

### 2. Worker GSD + Spec Kit Config Bundle
- GSD hooks: `gsd-gate.js` (PreToolUse blocker) installed in worker's `.claude/` config
- GSD config: `.planning/config.json` with `auto_initialized: true`
- Spec Kit commands: `.claude/commands/speckit.*.md` for reference
- Worker CLAUDE.md addition: instructions to read `.specs/` before starting work

### 3. Dispatcher Integration (`git-dispatch.py` changes)
- After pulling a task from bridge, run spec generation before SSH to worker
- Pass spec artifacts to worker (commit to branch or scp)
- Modified worker prompt: "Implement the spec at .specs/<slug>/ — GSD is enforced, create your PLAN.md first"

### 4. Docker Image Updates (`Dockerfile`)
- Install `uv` and `specify-cli` in the image
- Copy GSD hooks into `/home/claude/.claude/`
- Copy spec-kit commands into worker template

## Success Criteria

- [ ] `specify` CLI available in CCC Docker image
- [ ] GSD hooks (`gsd-gate.js`) installed in worker Claude config
- [ ] Dispatcher generates `.specs/` from raw task text before dispatching
- [ ] Worker blocks on execution tools until PLAN.md exists
- [ ] Worker implementation follows spec success criteria
- [ ] End-to-end test: submit task via bridge -> spec generated -> worker implements with GSD -> PR created

## Out of Scope

- Spec review/approval workflow (no human in the loop for hackathon)
- Spec versioning or conflict resolution
- Modifying the RONE poller or Teams integration
