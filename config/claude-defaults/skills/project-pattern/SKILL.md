---
skill: project-pattern
name: Project Pattern
version: 1.0.0
description: Structure any deployable project with one-click scripts, config, and docs
keywords: [deploy, build, setup, easy, simple, share, docker, container, tool, package, run, use, steps, click, scripts, automate, project, create, make]
---

# Project Pattern

How to structure ANY project someone else will use. The goal: a stranger runs one script and everything works.

## Philosophy

Before writing a single script, answer these questions:

1. **What is the full user journey?** Map every step from "I just cloned this" to "I'm done using it and want to clean up"
2. **Which steps always happen together?** Combine them into one script
3. **Which steps are optional or run independently?** Those get their own script
4. **What does the user need to configure?** Put it ALL in config.yaml
5. **What would confuse a stranger?** Eliminate it or document it

## Script Organization

### The default: numbered lifecycle scripts

```
config.yaml          # ALL settings in one file
1_deploy.sh          # Create/start everything
2_status.sh          # Check health
3_connect.sh         # Use the thing (name it for what it does)
4_destroy.sh         # Tear everything down
```

Numbers show the order. A stranger sees the files and knows what to run first.

### When to add a main script

If steps 1-3 always run together (deploy, wait, connect), add:

```
run.sh               # Does everything: deploy + wait + status + connect
1_deploy.sh          # Still exists for running independently
2_status.sh
3_connect.sh
4_destroy.sh
```

`run.sh` calls the numbered scripts in order. User runs ONE command and is done.

### When to simplify further

If the project is simple enough (no multi-step deploy, no teardown needed):

```
config.yaml
run.sh               # Just works
status.sh            # Optional health check
```

Don't add numbered scripts for ceremony. Add them when the user genuinely needs to run steps independently.

### Utility scripts (unnumbered, run anytime)

```
logs.sh              # View logs
sync.sh              # Transfer files
ssh.sh               # Shell access
backup.sh            # Save state
```

These are tools, not lifecycle steps. No numbers needed.

## Naming Scripts

Name scripts for what the USER does, not what the script does internally:

| Bad (implementation detail) | Good (user action) |
|---------------------------|-------------------|
| `create-cf-stack.sh` | `1_deploy.sh` |
| `check-instance-state.sh` | `2_status.sh` |
| `ssh-docker-exec-claude.sh` | `3_claude.sh` |
| `delete-cf-stack.sh` | `4_destroy.sh` |

If the project deploys a database, `3_connect.sh` might be `3_query.sh`.
If it deploys a web app, it might be `3_open.sh`.
Name it for what the user will do with it.

## config.yaml

Single source of truth. Human edits this ONE file. Scripts read it.

```yaml
# Project settings
name: my-project
region: us-east-2

# Cloud (if applicable)
aws_profile: default
instance_type: t3.medium

# Secrets (KEY NAMES only -- values fetched at runtime)
secrets:
  api_token: service/API_TOKEN
```

Scripts read it with:
```bash
read_config() { python3 -c "import yaml; print(yaml.safe_load(open('config.yaml'))$1)"; }
REGION=$(read_config "['region']")
```

Rules:
- Secrets: key names only, values fetched at runtime from credential store
- No hardcoded paths -- use `~` or `$HOME`
- Comments explain what each setting does

## README.md -- for humans

A stranger who has never seen this project reads the README and knows:
- What this is (one sentence)
- Why it exists (what problem it solves)
- How to use it (quick start with copy-paste commands)
- What it costs (if applicable)
- What scripts are available (table)

No architecture details. No implementation. No jargon. Just what and why.

Template:
```markdown
# Project Name

One sentence: what this is.

## Why

What problem does this solve? Why would someone use it?

## Quick Start

\`\`\`bash
# Edit config.yaml, then:
./run.sh
\`\`\`

## Scripts

| Script | What it does |
|--------|-------------|
| run.sh | Everything at once |
| 1_deploy.sh | Create resources |
| 2_status.sh | Check health |
| 3_connect.sh | Use the thing |
| 4_destroy.sh | Tear down |

## Configuration

All settings in config.yaml. See comments in the file.

## Cost

(if applicable)
```

## CLAUDE.md -- for Claude agents

A fresh Claude agent reads CLAUDE.md and can immediately operate and modify this project.

Must contain:
- Architecture (how components connect, what calls what)
- Files (what each file does, one-line per file)
- Config flow (what reads config.yaml, how secrets are resolved)
- Dependencies (what needs to be installed)
- How to extend (where new code goes)

No "what" or "why" (that's README territory). Just "how".

Template:
```markdown
# Project Name

One-line technical summary.

## Architecture

\`\`\`
local machine --> cloud/service --> result
\`\`\`

## Files

\`\`\`
project/
  config.yaml      All settings
  run.sh           Orchestrates numbered scripts
  1_deploy.sh      Creates X via Y
  2_status.sh      Checks Z
  ...
\`\`\`

## Config

Scripts read config.yaml via python3+pyyaml.
Key fields: ...

## Dependencies

- tool1
- tool2
```

## Script Rules

1. **Self-contained**: starts with `cd "$(dirname "${BASH_SOURCE[0]}")"` and reads config.yaml
2. **Idempotent deploy**: `1_deploy.sh` updates if exists, creates if not. Safe to re-run.
3. **Confirmed destroy**: `4_destroy.sh` requires typing "yes". Never auto-deletes.
4. **Read-only status**: `2_status.sh` never modifies anything.
5. **Runtime secrets**: fetched from credential store, never stored in config.yaml.
6. **No hardcoded values**: everything comes from config.yaml.

## The E2E Test

Before delivering, walk through the entire user experience:

1. I just cloned this repo. Can I figure out what to do from the file listing alone?
2. I opened README. Do I know what this is and how to start in 30 seconds?
3. I edited config.yaml. Was it obvious what to change?
4. I ran the deploy script. Did it just work? Did it tell me what's happening?
5. I ran status. Do I know if it's healthy?
6. I connected/used it. Was it obvious how?
7. I'm done. Can I clean up with one command?
8. A Claude agent opened CLAUDE.md. Can it modify this project without asking me questions?

If any answer is "no", fix it before calling it done.

## Do NOT

- Do NOT give the user manual commands to run -- wrap them in a script
- Do NOT add numbered scripts for ceremony -- only when steps genuinely run independently
- Do NOT skip README.md or CLAUDE.md -- both are always required
- Do NOT put human docs (what/why) in CLAUDE.md
- Do NOT put technical docs (architecture/config) in README.md
- Do NOT name scripts for implementation details -- name them for user actions
