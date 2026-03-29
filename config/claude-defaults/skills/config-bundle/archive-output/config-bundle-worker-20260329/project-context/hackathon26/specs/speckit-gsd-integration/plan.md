# Plan: Spec Kit + GSD Integration

## Technical Approach

### Phase 1: Docker Image — Add uv + Spec Kit + GSD hooks

**File:** `claude-portable/Dockerfile`

Add after the Claude Code install:
```dockerfile
# uv (Python package manager — needed for specify CLI)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/home/claude/.local/bin:$PATH"

# Spec Kit CLI
RUN uv tool install specify-cli --from git+https://github.com/github/spec-kit.git
```

Copy GSD hooks into the image:
```dockerfile
COPY --chown=claude:claude gsd/ /home/claude/.claude/hooks/gsd/
```

### Phase 2: GSD Hook Bundle for Workers

**New directory:** `claude-portable/gsd/`

Files to create:
- `gsd-gate.js` — copy from existing hook, adapted for Linux paths
- `gsd-config.json` — default `.planning/config.json` template

Worker settings.json addition (via `sync-config.sh` or bootstrap):
```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash|Write|Edit|Task|WebFetch",
      "command": "node /home/claude/.claude/hooks/gsd/gsd-gate.js"
    }]
  }
}
```

### Phase 3: Dispatcher Spec Generator

**New file:** `claude-portable/scripts/spec-generate.sh`

```bash
#!/bin/bash
# Input: $1 = task text, $2 = output dir
# Runs 3 sequential claude -p calls with spec-kit prompt templates
# Output: .specs/<slug>/spec.md, plan.md, tasks.md
```

The spec generator uses the speckit command templates as system prompts, feeding the raw task text as user input. Each step reads the previous step's output.

### Phase 4: Dispatcher Integration

**File:** `claude-portable/scripts/git-dispatch.py`

In the `dispatch_task()` function, before SSH to worker:
1. Run `spec-generate.sh` with the task text
2. SCP the `.specs/` directory to the worker
3. Modify the claude prompt to reference the spec:
   ```
   "Implement the specification at .specs/<slug>/. GSD tracking is enforced —
    create .planning/quick/001-<slug>/001-PLAN.md before any implementation.
    Verify all success criteria from the spec before creating your PR."
   ```

### Phase 5: Worker CLAUDE.md Template

**File:** `claude-portable/config/CLAUDE-worker.md` (addition)

```markdown
## Spec-Driven Workflow
- Read .specs/<task>/ BEFORE starting work
- GSD is enforced: create PLAN.md with success criteria from the spec
- Verify every criterion before PR
```

## Dependency Order

1. Dockerfile changes (Phase 1) — base image must have tools
2. GSD hook bundle (Phase 2) — needed before workers can enforce
3. Spec generator script (Phase 3) — standalone, testable
4. Dispatcher integration (Phase 4) — ties it together
5. Worker CLAUDE.md (Phase 5) — instructions for the AI

## Risk Mitigation

- **Spec generation takes too long:** Set 5-minute timeout, fall back to raw dispatch if spec fails
- **GSD gate too strict:** Include bypass for `Read/Glob/Grep` (already in gate logic)
- **Worker can't find spec:** SCP artifacts before starting claude session
