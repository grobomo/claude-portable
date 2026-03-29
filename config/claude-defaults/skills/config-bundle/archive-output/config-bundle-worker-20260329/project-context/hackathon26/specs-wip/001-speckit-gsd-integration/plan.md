# Implementation Plan: Spec Kit + GSD Integration for CCC Fleet

**Branch**: `001-speckit-gsd-integration` | **Date**: 2026-03-29 | **Spec**: `specs/001-speckit-gsd-integration/spec.md`
**Input**: Feature specification from `specs/001-speckit-gsd-integration/spec.md`

## Summary

Integrate Spec Kit (structured planning) and GSD (enforcement hooks) into the CCC fleet pipeline so that dispatched tasks go through specify->plan->tasks before reaching workers, and workers are gated by GSD hooks that block tool execution until a PLAN.md exists. Most components already exist — the work is testing, gap-filling, and deploying the bundle to the fleet.

## Technical Context

**Language/Version**: Bash (spec-generate.sh), Python 3.11 (git-dispatch.py), JavaScript/Node 20 (GSD hooks)
**Primary Dependencies**: Claude Code CLI (`claude -p`), Docker (bookworm base), SSH/SCP (fleet comms)
**Storage**: S3 (session data), EC2 local filesystem (/workspace), git (bridge repo)
**Testing**: Manual E2E test via bridge submit -> verify spec generated -> verify worker creates PLAN.md -> verify PR
**Target Platform**: Linux x86_64 (EC2 instances, Docker containers)
**Project Type**: Infrastructure/DevOps pipeline (no library, no CLI — operational integration)
**Constraints**: Spec generation must complete in <5 min; GSD gate must not block read-only tools (Glob, Grep, Read); Worker prompt must reference spec path

## Constitution Check

*Constitution is a blank template — no project-specific gates defined. Proceeding.*

## Project Structure

### Documentation (this feature)

```text
specs/001-speckit-gsd-integration/
├── plan.md              # This file
├── research.md          # Phase 0: existing components audit
├── data-model.md        # Phase 1: data flow between components
├── quickstart.md        # Phase 1: how to test the integration
└── tasks.md             # Phase 2: ordered implementation tasks
```

### Source Code (across repos)

```text
claude-portable/                          # grobomo/claude-portable
├── Dockerfile                            # DONE: uv already installed (line 65)
├── scripts/
│   ├── git-dispatch.py                   # DONE: spec gen + SCP integrated (lines 1895-2027)
│   └── spec-generate.sh                  # DONE: 3-phase specify->plan->tasks
├── config/
│   └── claude-defaults/
│       ├── CLAUDE.md                     # DONE: spec-driven workflow instructions
│       ├── hooks/
│       │   └── run-modules/
│       │       └── PreToolUse/
│       │           └── gsd-gate.js       # DONE: blocks tools until PLAN.md exists
│       └── skills/
│           └── auto-gsd/
│               └── CLAUDE.md             # DONE: GSD skill instructions

hackathon26/                              # joel-ginsberg_tmemu/hackathon26
├── scripts/
│   └── fleet-bootstrap.sh                # NEEDS UPDATE: deploy GSD bundle to fleet
└── .claude/commands/
    └── speckit.*.md                      # DONE: speckit slash commands

rone-boothapp-bridge/                     # joel-ginsberg_tmemu/RONE-boothapp-bridge
└── (no changes needed — bridge is a dumb file transport)
```

**Structure Decision**: Cross-repo integration. No new directories needed. Changes are to existing files in `claude-portable/` and `hackathon26/`.

## What Already Exists vs What's Missing

### DONE (already built and in code)

| Component | Location | Status |
|-----------|----------|--------|
| uv in Docker image | `claude-portable/Dockerfile:65` | Installed via astral.sh |
| GSD gate hook | `claude-portable/config/claude-defaults/hooks/run-modules/PreToolUse/gsd-gate.js` | Blocks Bash/Write/Edit/Task/WebFetch until PLAN.md exists |
| Auto-GSD skill | `claude-portable/config/claude-defaults/skills/auto-gsd/CLAUDE.md` | Worker instructions for GSD workflow |
| Worker CLAUDE.md | `claude-portable/config/claude-defaults/CLAUDE.md` | Spec-driven dev section with .specs/ instructions |
| Spec generator | `claude-portable/scripts/spec-generate.sh` | 3-phase claude -p pipeline, timeout, GSD scaffold |
| Dispatcher integration | `claude-portable/scripts/git-dispatch.py:1895-2027` | `_generate_spec_locally()`, `_scp_spec_to_worker()`, prompt preamble |
| Spec kit commands | `hackathon26/.claude/commands/speckit.*.md` | Local slash commands for specifying/planning |

### GAPS (needs work)

| Gap | Problem | Fix |
|-----|---------|-----|
| **E2E test never run** | All pieces exist but have never been tested together | Submit a test task via bridge, trace through dispatcher->spec->worker->PR |
| **spec-generate.sh not deployed** | Script exists in repo but may not be in running container | Rebuild or docker cp to dispatcher |
| **GSD hooks not deployed** | Hooks exist in config/claude-defaults but sync-config.sh may not have run | Verify hooks present in worker container, re-sync if needed |
| **settings.json hook registration** | gsd-gate.js needs to be registered in worker's settings.json | Verify via docker exec, add if missing |
| **SPEC_KIT_ENABLED env var** | Dispatcher checks this env (default "1") but may not be set | Verify in docker-compose or container env |
| **specify-cli not installed** | uv is installed but `specify-cli` package isn't (spec used to say install it, but spec-generate.sh uses claude -p directly, not the CLI) | N/A — not needed, spec-generate.sh is self-contained |
| **Worker hook runner** | Workers need `run-pretooluse.js` (the hook runner that loads modules) | Verify present; if missing, copy from config/claude-defaults |
| **Continuous Claude integration** | Spec says workers should use continuous-claude for multi-step specs | Wire spec tasks.md into TODO.md format that continuous-claude reads |

## Complexity Tracking

> No constitution violations to justify.

## Phase 0: Research

See research.md (next artifact).

## Phase 1: Design

See data-model.md and quickstart.md (next artifacts).
