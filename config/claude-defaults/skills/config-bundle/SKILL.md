---
name: config-bundle
description: Build and deploy portable Claude Code environment bundles for CCC fleet and teammates
keywords:
  - bundle
  - config
  - deploy
  - portable
  - fleet
---

# Config Bundle

Build a complete, portable Claude Code environment from local files. One command to bundle,
one command to install. No GitHub cloning on target machines.

## What's Included

```
config-bundle-{target}-{date}/
  manifest.json              # Build metadata + collector results
  install.js                 # Self-contained installer
  hooks/                     # Hook runners + modules (GSD gate, enforcement)
  settings.json              # Stripped settings (no desktop-only config)
  CLAUDE.md                  # Worker/teammate instructions
  rules/                     # Claude instruction rules
  skills/                    # Selected skills (auto-gsd, code-review, etc.)
  commands/                  # Spec-kit slash commands
  scripts/                   # Runtime scripts (continuous-claude, spec-generate)
  project-context/           # Hackathon26 notes, specs, TODO, architecture
    CONTEXT-SUMMARY.md       # Quick-read overview for workers
    hackathon26/             # Full CLAUDE.md, TODO.md, rules, specs
```

## Build

```bash
# Worker bundle (default -- minimal, for CCC fleet)
node bundle.js

# Teammate bundle (more skills, for hackathon team)
BUNDLE_TARGET=teammate node bundle.js

# Full bundle (everything)
BUNDLE_TARGET=full node bundle.js

# Sync hackathon notes from GitHub before bundling
HACKATHON_SYNC=1 node bundle.js
```

## Deploy to CCC Fleet

```bash
# SCP + install on a worker
scp output/config-bundle-worker-*.tar.gz ubuntu@<worker-ip>:/tmp/
ssh ubuntu@<worker-ip> "
  docker cp /tmp/config-bundle-*.tar.gz claude-portable:/tmp/ &&
  docker exec claude-portable bash -c '
    cd /tmp && tar xzf config-bundle-*.tar.gz &&
    node config-bundle-*/install.js config-bundle-*/
  '
"
```

## Deploy to Teammate

```bash
# Share the tarball -- teammate runs:
tar xzf config-bundle-teammate-*.tar.gz
node config-bundle-*/install.js config-bundle-*/
```

## Architecture

- `bundle.js` -- Single entry point, loads collector modules
- `collectors/*.js` -- Modular collectors (hooks, settings, rules, skills, hackathon context, etc.)
- `install.js` -- Self-contained installer (included in bundle, no external deps)

Adding a new collector: create `collectors/NN-name.js` exporting `function(bundlePath, ctx) -> {name, ok, files}`.
