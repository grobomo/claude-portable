# Continuous Claude + Claude Portable Integration Plan

## Goal

Spin up a claude-portable EC2 instance that:
1. Accepts normal SSH TUI sessions (interactive `claude` usage)
2. Runs `continuous-claude` autonomously against a configurable repo
3. Ships with mcp-manager, blueprint-extra MCP, and Chrome + custom extension pre-installed
4. Browser automation works out of the box on first boot

---

## What Already Works

| Capability | Status | Where |
|---|---|---|
| EC2 lifecycle (launch/stop/kill) | Done | `cpp` launcher |
| Docker container with Claude CLI | Done | `Dockerfile` |
| SSH into container TUI | Done | `cpp --name X` -> `docker exec -it` |
| Chrome + Xvfb + VNC | Done | `Dockerfile` + `scripts/browser.sh` |
| OAuth/API key auth | Done | `push_credentials()` in `cpp` |
| S3 state sync | Done | `scripts/state-sync.sh` |
| Idle monitor (auto-shutdown) | Done | `scripts/idle-monitor.sh` |
| Component system (pull repos at boot) | Done | `components.yaml` + `scripts/sync-config.sh` |
| Web chat (phone access) | Done | `scripts/web-chat.js` + Lambda |

---

## Gaps and Implementation Plan

### Gap 1: continuous-claude runner script not in container

**Problem:** The `run-continuous.sh` script lives in each project repo (e.g. ddei-email-security). The container needs a generic version that works with any repo.

**Fix:** Add `scripts/continuous-claude.sh` to claude-portable:

```bash
#!/bin/bash
# Generic continuous-claude runner.
# Usage: continuous-claude.sh [--repo <clone-url>] [--branch main] [--workdir /workspace/project]
set -uo pipefail

REPO="${1:?Usage: continuous-claude.sh <repo-url> [branch] [workdir]}"
BRANCH="${2:-main}"
WORKDIR="${3:-/workspace/$(basename "$REPO" .git)}"

# Clone or pull
if [ ! -d "$WORKDIR/.git" ]; then
  git clone -b "$BRANCH" "$REPO" "$WORKDIR"
else
  cd "$WORKDIR" && git checkout "$BRANCH" && git pull origin "$BRANCH"
fi
cd "$WORKDIR"

# Add log to gitignore
grep -q 'continuous-claude.log' .gitignore 2>/dev/null || echo 'continuous-claude.log' >> .gitignore

PROMPT='Read TODO.md and .claude/rules/. Pick the FIRST unchecked task. Workflow:
1. Create a new branch from main (git checkout -b continuous-claude/task-N)
2. Push the branch and open a PR with gh pr create
3. Do the actual work. Push commits to the branch as you go.
4. When done, mark the task done in TODO.md, commit, push.
5. Merge the PR with: gh pr merge --squash --delete-branch
Then stop. Do NOT proceed to the next task.
CRITICAL: You MUST merge the PR before stopping.'

MAX_ERRORS=3
errors=0

while true; do
  echo "$(date '+%Y-%m-%d %H:%M:%S') === Starting iteration ===" >> continuous-claude.log
  git checkout "$BRANCH" 2>/dev/null
  git pull origin "$BRANCH" 2>/dev/null

  # Safety net: merge leftover PRs
  open_pr=$(gh pr list --state open --limit 1 --json number --jq '.[0].number' 2>/dev/null)
  if [ -n "$open_pr" ] && [ "$open_pr" != "null" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') Merging leftover PR #$open_pr" >> continuous-claude.log
    gh pr merge "$open_pr" --squash --delete-branch >> continuous-claude.log 2>&1
    git pull origin "$BRANCH" 2>/dev/null
  fi

  if ! grep -q '\[ \]' TODO.md 2>/dev/null; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') CONTINUOUS_CLAUDE_PROJECT_COMPLETE" >> continuous-claude.log
    break
  fi

  claude -p --dangerously-skip-permissions "$PROMPT" >> continuous-claude.log 2>&1
  rc=$?

  if [ $rc -ne 0 ]; then
    errors=$((errors + 1))
    echo "$(date '+%Y-%m-%d %H:%M:%S') Failed (rc=$rc, errors=$errors/$MAX_ERRORS)" >> continuous-claude.log
    [ $errors -ge $MAX_ERRORS ] && break
  else
    errors=0
  fi

  echo "$(date '+%Y-%m-%d %H:%M:%S') === Iteration complete ===" >> continuous-claude.log
  sleep 10
done
```

**Config:** New env vars in `.env` / `docker-compose.yml`:
```
CONTINUOUS_CLAUDE_REPO=https://github.com/org/project.git
CONTINUOUS_CLAUDE_BRANCH=main
CONTINUOUS_CLAUDE_ENABLED=true
```

**Bootstrap integration:** At the end of `bootstrap.sh`, after daemons start:
```bash
if [ "${CONTINUOUS_CLAUDE_ENABLED:-}" = "true" ] && [ -n "${CONTINUOUS_CLAUDE_REPO:-}" ]; then
  echo "[+] Starting continuous-claude..."
  nohup /opt/claude-portable/scripts/continuous-claude.sh \
    "$CONTINUOUS_CLAUDE_REPO" "${CONTINUOUS_CLAUDE_BRANCH:-main}" \
    >> /data/continuous-claude.log 2>&1 &
  echo "  continuous-claude PID: $!"
fi
```

---

### Gap 2: mcp-manager and blueprint-extra not in components.yaml

**Problem:** `components.yaml` is all commented-out examples. Neither mcp-manager nor blueprint-extra-mcp are configured to pull.

**Fix:** Uncomment and populate `components.yaml`:

```yaml
- name: mcp-manager
  repo: grobomo/mcp-manager
  type: mcp
  target: /opt/mcp/mcp-manager
  enabled: true
  visibility: private
  description: "MCP server lifecycle manager"

- name: blueprint-extra-mcp
  repo: grobomo/blueprint-extra-mcp
  type: mcp
  target: /opt/mcp/blueprint-extra-mcp
  enabled: true
  visibility: private
  description: "Browser automation via Chrome + custom extension"
```

**Dependency:** These are private repos -> requires `GITHUB_TOKEN` in `.env`. Already supported.

---

### Gap 3: Blueprint custom Chrome extension not pre-installed

**Problem:** Blueprint-extra-mcp has a `extensions/` directory with a custom Chrome extension. Chrome needs to launch with `--load-extension=/opt/mcp/blueprint-extra-mcp/extensions` for it to work.

**Fix:** Modify `scripts/browser.sh` Chrome launch flags:

```bash
EXTENSION_DIR="/opt/mcp/blueprint-extra-mcp/extensions"
EXTENSION_FLAG=""
if [ -d "$EXTENSION_DIR" ]; then
  EXTENSION_FLAG="--load-extension=$EXTENSION_DIR"
fi

nohup google-chrome-stable \
  --no-sandbox --disable-gpu --no-first-run --disable-sync \
  --disable-background-networking \
  --remote-debugging-port="${CHROME_DEBUG_PORT}" \
  --window-size=1920,1080 \
  --user-data-dir="$CHROME_PROFILE" \
  $EXTENSION_FLAG \
  &>/dev/null &
```

---

### Gap 4: mcp-manager servers.yaml needs container-aware paths

**Problem:** Current `servers.yaml` has Windows paths (e.g. `C:/nodejs/node.exe`, `C:/Users/joelg/Documents/...`). Container needs Linux paths.

**Fix:** Already partially solved by `scripts/rewrite-paths.sh`. Needs to also rewrite `servers.yaml` paths:
- `C:/nodejs/node.exe` -> `node`
- `C:/Users/joelg/Documents/ProjectsCL1/MCP/blueprint-extra-mcp/` -> `/opt/mcp/blueprint-extra-mcp/`
- Other MCP server paths similarly

The `rewrite-paths.sh` script should handle `servers.yaml` if it exists at `/opt/mcp/mcp-manager/servers.yaml`.

**Alternative:** Ship a container-specific `servers.yaml` template in `config/` that gets copied during sync-config. This is cleaner -- the container `servers.yaml` should reference container paths natively.

---

### Gap 5: .mcp.json not configured in container

**Problem:** Claude Code needs a `.mcp.json` in the workspace or home directory pointing to mcp-manager. The container doesn't have one.

**Fix:** Bootstrap should write `/home/claude/.mcp.json`:

```json
{
  "mcpServers": {
    "mcp-manager": {
      "command": "node",
      "args": ["/opt/mcp/mcp-manager/build/index.js"],
      "env": {}
    }
  }
}
```

Add to `bootstrap.sh` after MCP deps install step.

---

### Gap 6: gh CLI not authenticated in container

**Problem:** continuous-claude needs `gh pr create` and `gh pr merge`. The `gh` CLI inside the container has no auth token.

**Fix:** Bootstrap already has `GITHUB_TOKEN` env var. Add to bootstrap:

```bash
if [ -n "${GITHUB_TOKEN:-}" ]; then
  echo "$GITHUB_TOKEN" | gh auth login --with-token 2>/dev/null
  gh auth setup-git 2>/dev/null
  # Configure git identity for continuous-claude PRs
  git config --global user.name "claude-portable"
  git config --global user.email "noreply@claude-portable"
fi
```

---

### Gap 7: Idle monitor conflicts with continuous-claude

**Problem:** Idle monitor checks for active `node.*claude` processes, SSH sessions, and interactive shells. When continuous-claude is running, there IS an active Claude process -- but between iterations (during the `sleep 10`), the idle monitor might see zero processes.

**Fix:** When `CONTINUOUS_CLAUDE_ENABLED=true`, the idle monitor should also check for the continuous-claude.sh process:

```bash
CC_PROCS="$(pgrep -c -f 'continuous-claude' 2>/dev/null || true)"
CC_PROCS="${CC_PROCS//[!0-9]/}"
ACTIVE=$(( ${CLAUDE_PROCS:-0} + ${SSH_SESSIONS:-0} + ${INTERACTIVE:-0} + ${CC_PROCS:-0} ))
```

**Also:** Completion detection. When continuous-claude finishes (all tasks done), the idle monitor should start its countdown. Check for `CONTINUOUS_CLAUDE_PROJECT_COMPLETE` in the log.

---

### Gap 8: No status checking from local machine

**Problem:** No way to check continuous-claude progress from the local machine without SSH-ing in.

**Fix:** Add `cpp status [name]` command that:

1. SSHes to the instance
2. Reads `/data/continuous-claude.log` tail
3. Runs `gh pr list` in the workspace
4. Shows idle monitor status
5. Shows running processes

```
$ cpp status dev

  Instance: cpp-dev (i-0abc123) - running
  IP: 3.14.159.26
  Uptime: 2h 15m

  Continuous Claude:
    Status: RUNNING (PID 1234)
    Repo: https://github.com/org/project.git
    Last iteration: 2026-03-27 14:30:00
    Tasks remaining: 3/10
    Last PR: #42 "Deploy testing server" (merged)
    Errors: 0/3

  Open PRs:
    #43 "Upload share/ files" (open, 2 commits)

  Daemons:
    Idle monitor: active (0/30min idle)
    State sync: active (last sync 45s ago)
    Web chat: active (port 8888)
```

**Also add:** `cpp logs [name]` to tail the continuous-claude log:
```
$ cpp logs dev          # tail -50 continuous-claude.log
$ cpp logs dev -f       # follow mode
```

---

### Gap 9: No way to configure continuous-claude per-instance via cpp

**Problem:** Currently `cpp --name dev` launches and connects. Need a way to say "launch this instance with continuous-claude pointed at repo X".

**Fix:** Extend `cpp` launcher:

```bash
# New flags
cpp --name worker1 --continuous https://github.com/org/project.git
cpp --name worker1 --continuous https://github.com/org/project.git --branch feature-x

# Under the hood: sets env vars in the instance's .env before docker compose up
CONTINUOUS_CLAUDE_ENABLED=true
CONTINUOUS_CLAUDE_REPO=https://github.com/org/project.git
CONTINUOUS_CLAUDE_BRANCH=main
```

---

### Gap 10: Multiple Claude processes need separate auth budgets

**Problem:** When both interactive TUI and continuous-claude run simultaneously, they share the same OAuth token / API key. With OAuth (Claude Max), there's a concurrent session limit.

**Mitigation options:**
1. **API key mode** (recommended for continuous-claude): No session limits, just cost. Set `ANTHROPIC_API_KEY` in `.env`.
2. **OAuth mode**: Works but only one Claude process can be active at a time. The interactive TUI session and continuous-claude will conflict. Solution: don't SSH in while continuous-claude is running, use `cpp status` and `cpp logs` instead.
3. **Separate API key for continuous-claude**: Add `CONTINUOUS_CLAUDE_API_KEY` env var. The `continuous-claude.sh` script exports it as `ANTHROPIC_API_KEY` before running `claude -p`.

**Recommendation:** Use API key mode for cloud instances. OAuth is better for interactive use from your laptop.

---

## Authentication Summary

| Auth Method | Interactive TUI | Continuous Claude | Both Simultaneously |
|---|---|---|---|
| API Key (`ANTHROPIC_API_KEY`) | Yes | Yes | Yes (shared quota) |
| OAuth (Claude Max) | Yes | Yes | No (session conflict) |
| Separate keys (API for CC, OAuth for TUI) | OAuth | API key | Yes |

**How auth gets into the container (current flow, keep it):**

1. `cpp` reads `.env` from the project directory
2. `.env` values go into EC2 user-data script
3. User-data writes `.env` on EC2 host
4. `docker-compose.yml` passes env vars from `.env` into container
5. `bootstrap.sh` -> `inject-secrets.sh` writes credential files
6. `cpp` also pushes fresh OAuth creds via SSH after container starts (`push_credentials()`)

No changes needed to auth flow. Just add the new env vars to `docker-compose.yml`.

---

## Implementation Checklist

### Phase 1: Core (make it work)
- [ ] Create `scripts/continuous-claude.sh` (generic runner)
- [ ] Add `CONTINUOUS_CLAUDE_*` env vars to `docker-compose.yml` and `.env.example`
- [ ] Add continuous-claude startup to `bootstrap.sh`
- [ ] Fix idle monitor to detect continuous-claude process
- [ ] Authenticate `gh` CLI in bootstrap
- [ ] Configure git identity in bootstrap

### Phase 2: MCP + Browser (out-of-box automation)
- [ ] Populate `components.yaml` with mcp-manager and blueprint-extra-mcp
- [ ] Create container-specific `config/servers.yaml` (Linux paths)
- [ ] Write `.mcp.json` in bootstrap (pointing to mcp-manager)
- [ ] Modify `browser.sh` to load blueprint extension
- [ ] Ensure `rewrite-paths.sh` handles servers.yaml

### Phase 3: Observability (check status remotely)
- [ ] Add `cpp status [name]` command
- [ ] Add `cpp logs [name]` command
- [ ] Add `--continuous <repo-url>` flag to `cpp` launcher

### Phase 4: Polish
- [ ] Update `CLAUDE.md` with continuous-claude docs
- [ ] Update `.env.example` with new vars
- [ ] Update `test.sh` to validate continuous-claude boot
- [ ] GitHub Mobile notifications (repo watch) for PR tracking

---

## Architecture Diagram

```
Local Machine (Windows)
  |
  | cpp --name worker1 --continuous https://github.com/org/project.git
  | cpp status worker1        (check progress)
  | cpp logs worker1           (tail log)
  | cpp --name worker1         (SSH TUI when needed)
  v
EC2 Instance (t3.large)
  |
  | docker-compose up
  v
claude-portable container
  |
  +-- bootstrap.sh
  |     |
  |     +-- inject-secrets.sh (API key or OAuth)
  |     +-- sync-config.sh (pulls mcp-manager + blueprint-extra from GitHub)
  |     +-- gh auth login (GitHub CLI auth)
  |     +-- browser.sh start (Chrome + VNC + blueprint extension)
  |     +-- idle-monitor.sh (auto-shutdown, CC-aware)
  |     +-- state-sync.sh auto (S3 backup every 60s)
  |     +-- continuous-claude.sh (if CONTINUOUS_CLAUDE_ENABLED=true)
  |           |
  |           +-- git clone <repo>
  |           +-- loop: pick task -> branch -> PR -> work -> merge
  |           +-- log to /data/continuous-claude.log
  |
  +-- MCP servers
  |     +-- mcp-manager (lifecycle manager)
  |     +-- blueprint-extra-mcp (browser automation)
  |           +-- Chrome extension pre-loaded
  |
  +-- Interactive access
        +-- SSH TUI (port 2222)
        +-- Web chat (port 8888, phone access)
        +-- VNC (port 5900, SSH tunnel)
```

---

## Risk / Gotchas

1. **Private repos need GITHUB_TOKEN**: Both mcp-manager and blueprint-extra-mcp are private grobomo repos. The token must have repo scope.

2. **Chrome extension path must exist before Chrome starts**: `browser.sh` runs during bootstrap. `sync-config.sh` must complete before `browser.sh` starts. Current order is correct (step 3 = sync, later = browser start).

3. **continuous-claude eats tokens**: Each iteration runs `claude -p` which costs API credits. A runaway loop (bad prompt, failing tasks) will burn through budget. The `MAX_ERRORS=3` safety net helps but monitor costs.

4. **Git identity for PRs**: continuous-claude creates PRs. The git user.name/email inside the container must match what GitHub expects. Using "claude-portable" / noreply is safe for the grobomo account.

5. **OAuth token expiry during long runs**: OAuth access tokens expire. The container has `cred-refresh.sh` running every 15min, but if the refresh token itself expires (rare), continuous-claude will start failing. API key mode doesn't have this problem.

6. **Concurrent writes to TODO.md**: If you SSH in and manually edit TODO.md while continuous-claude is running, you'll get merge conflicts. Use `cpp logs` to monitor, don't touch the repo while CC is active.

7. **mcp-manager build step**: mcp-manager has TypeScript (`npm run build`). The bootstrap MCP install loop already handles `npm install` + `npm run build` for packages with a `build` script. Should work.

8. **servers.yaml auto_start**: blueprint-extra has `auto_start: true` in the current servers.yaml. In the container, mcp-manager should auto-start it when Claude first needs browser tools. Make sure the container servers.yaml has `auto_start: true` for blueprint-extra.
