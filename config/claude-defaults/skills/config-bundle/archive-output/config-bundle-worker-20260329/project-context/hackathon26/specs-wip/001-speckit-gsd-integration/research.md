# Research: Spec Kit + GSD Integration

## R1: How does the hook runner work on workers?

**Decision**: Workers use the same hook architecture as Joel's desktop — `run-pretooluse.js` loads all `.js` modules from `run-modules/PreToolUse/` alphabetically.

**Evidence**: `claude-portable/config/claude-defaults/hooks/run-modules/PreToolUse/gsd-gate.js` exists, which means the hook runner must also be deployed. The `sync-config.sh` script copies `config/claude-defaults/` into the container's `~/.claude/` at bootstrap.

**Risk**: If `settings.json` doesn't have the hook entry pointing to `run-pretooluse.js`, the module files exist but never execute. Must verify.

## R2: Does the dispatcher have Claude Code available for spec generation?

**Decision**: Yes. The dispatcher runs inside the same Docker image (`claude-portable`), which has Claude Code installed at line 70 of the Dockerfile. `claude -p` is available.

**Rationale**: `spec-generate.sh` calls `claude -p` three times. The dispatcher container must have `ANTHROPIC_API_KEY` set for this to work.

**Risk**: Dispatcher may run without API key if it was set up before spec generation was added. Verify with `docker exec claude-portable env | grep ANTHROPIC`.

## R3: How are spec artifacts transferred to workers?

**Decision**: SCP from dispatcher to worker host, then `docker cp` into the container.

**Evidence**: `git-dispatch.py:1932-1959` — `_scp_spec_to_worker()` does:
1. `scp -r <tmpdir>/. ubuntu@<worker_ip>:/tmp/spec-<id>/`
2. `ssh ... docker cp /tmp/spec-<id>/.specs claude-portable:/workspace/boothapp/.specs`
3. `ssh ... docker cp /tmp/spec-<id>/.planning claude-portable:/workspace/boothapp/.planning`

**Risk**: If worker doesn't have `/workspace/boothapp/` yet (first task), docker cp may fail. Need to ensure directory exists.

## R4: Does continuous-claude work with spec-kit task format?

**Decision**: It can, with adaptation. Continuous-claude reads `TODO.md` for `- [ ]` items. Spec-kit's `tasks.md` has the same checkbox format. The dispatcher or worker can copy `tasks.md` content into `TODO.md`.

**Alternative rejected**: Having continuous-claude read `tasks.md` directly — this would require modifying continuous-claude's task parser, which is more invasive.

**Approach**: Worker prompt should instruct: "Copy the tasks from .specs/<slug>/tasks.md into TODO.md, then use continuous-claude to implement each one."

## R5: Is `specify-cli` needed?

**Decision**: No. `spec-generate.sh` uses `claude -p` directly with inline prompts. It doesn't call `specify` CLI at all. The spec's original mention of installing `specify-cli` in Docker was aspirational but unnecessary — the shell script approach is simpler and already works.

**Rationale**: Three `claude -p` calls with structured prompts achieve the same result as running the CLI's specify/plan/tasks commands, without adding a Python dependency chain.

## R6: Settings.json hook registration format

**Decision**: Workers need this in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [{
      "type": "command",
      "command": "node /home/claude/.claude/hooks/run-pretooluse.js",
      "matcher": "*"
    }]
  }
}
```

The runner script then loads all modules from `run-modules/PreToolUse/` including `gsd-gate.js`.

**Alternative rejected**: Registering `gsd-gate.js` directly (bypasses the module architecture, can't add more hooks later).

## R7: Environment bundle approach

**Decision**: Rather than installing from GitHub on each worker, bundle the entire environment (hooks, skills, settings, CLAUDE.md) into a deployable tarball. SCP the tarball to workers and extract.

**Rationale**: Workers don't have GitHub access for private config repos. The bundle approach is faster (no network fetch) and deterministic (exact same config on every worker).

**Implementation**: Create `scripts/build-worker-bundle.sh` in hackathon26 that:
1. Collects files from `claude-portable/config/claude-defaults/`
2. Strips desktop-only settings (Windows paths, local MCP servers)
3. Creates a tarball
4. `scp` + `ssh tar xf` to deploy
