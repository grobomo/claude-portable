# Hackathon Project Context

**Deadline:** April 1, 2026
**Progress:** 79 tasks done, 11 remaining

## What You Need to Know

This bundle includes full project context from hackathon26 (the coordination workspace).
Read these files in order:

1. `hackathon26/CLAUDE.md` — Architecture, component map, data flow, team info
2. `hackathon26/TODO.md` — Current status, what's done, what's left
3. `hackathon26/rules/` — Operational rules (git creds, deployment, messaging)
4. `hackathon26/specs/` — Spec-kit artifacts for current features
5. `hackathon26/commands/` — Spec-kit slash commands

## Key Architecture Facts

- **BoothApp** = AI trade show demo capture (badge OCR -> session -> analysis -> follow-up)
- **CCC Fleet** = 1 dispatcher + 2 workers on AWS EC2 (Docker containers)
- **RONE** = Internal K8s running Teams chat poller
- **Bridge** = Git repo shuttling tasks between RONE and AWS CCC
- Workers code against `altarr/boothapp` repo using `grobomo` GitHub account
- Dispatcher uses `tmemu` account for bridge repo access

## How Workers Should Use This Context

When you receive a task:
1. Read the spec in `.specs/` (if provided)
2. Reference `hackathon26/CLAUDE.md` for architecture decisions
3. Check `hackathon26/TODO.md` to understand where your task fits
4. Follow GSD: create PLAN.md before implementation
5. Verify against spec success criteria before PR

Generated: 2026-03-29T17:52:58.888Z
