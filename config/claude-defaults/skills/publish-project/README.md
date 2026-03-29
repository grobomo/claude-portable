# Publish Project

One command to generate project docs and ship to GitHub + marketplace.

## The Problem

Every project needs docs (README, CLAUDE.md, diagrams, explainer page) but they're created inconsistently, sometimes missing, and publishing is a multi-step chore across GitHub, marketplace, and wiki.

## How It Works

```
/publish sync
  1. Gap analysis: what docs exist? what's missing?
  2. Generate missing layers (5 layers, 3 depth levels)
  3. git commit + push to GitHub
  4. Publish plugin to skill marketplace
```

## Documentation Layers

```
HIGH LEVEL (humans)
  README.md -------- text: what/why/how/install/usage
  Explainer HTML --- visual: same concepts, interactive panels
  "Why" diagram ---- visual: problem/solution at a glance

MID LEVEL (humans + claudes)
  Architecture ----- diagrams: flow, config, lifecycle

LOW LEVEL (claudes)
  CLAUDE.md -------- text: internals, extension points, gotchas
  Code diagrams ---- visual: call paths, state, dependencies
```

## Commands

| Command | What it does |
|---------|-------------|
| `/publish init` | Create GitHub repo + generate all docs |
| `/publish sync` | Update docs, push to GitHub + marketplace |
| `/publish wiki` | Optional: deploy to Confluence wiki |
| `/publish status` | Show doc coverage + publish state |

## Related Skills

| Skill | Role |
|-------|------|
| **publish-project** | User-facing "ship it" command (this skill) |
| **marketplace-manager** | Low-level marketplace plumbing (clone, plugin.json, push) |
| **wiki-api** | Confluence operations (used by `/publish wiki`) |
| **gemini-image-gen** | Generate architecture + code diagrams |

## Folder Structure (generated)

```
project/
+-- README.md                    # HIGH - text
+-- CLAUDE.md                    # LOW - text
+-- docs/
    +-- project-explainer.html   # HIGH - visual
    +-- project-why.webp         # HIGH - problem/solution
    +-- mid-level/               # MID - architecture diagrams
    +-- low-level/               # LOW - code diagrams
```
