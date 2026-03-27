# Continuous Claude Integration - Task List

## Phase 1: Core (continuous-claude runner)

- [ ] Create `scripts/continuous-claude.sh` -- generic runner that clones a repo and loops through TODO.md tasks via PRs. Takes repo URL, branch, and workdir as args. Includes safety net for leftover PRs, MAX_ERRORS=3, and CONTINUOUS_CLAUDE_PROJECT_COMPLETE signal.
  - PR title: "feat: add continuous-claude runner script"

- [ ] Add continuous-claude env vars to docker-compose.yml and .env.example -- CONTINUOUS_CLAUDE_ENABLED, CONTINUOUS_CLAUDE_REPO, CONTINUOUS_CLAUDE_BRANCH. Pass them through to the container.
  - PR title: "feat: add continuous-claude env vars to compose config"

- [ ] Add continuous-claude auto-start to bootstrap.sh -- if CONTINUOUS_CLAUDE_ENABLED=true and CONTINUOUS_CLAUDE_REPO is set, clone the repo and start the runner as a background daemon. Log to /data/continuous-claude.log.
  - PR title: "feat: auto-start continuous-claude in bootstrap"

- [ ] Add gh CLI auth to bootstrap.sh -- if GITHUB_TOKEN is set, run `gh auth login --with-token` and `gh auth setup-git`. Also set git global user.name="claude-portable" and user.email="noreply@claude-portable".
  - PR title: "feat: authenticate gh CLI and git identity in bootstrap"

- [ ] Fix idle-monitor.sh to detect continuous-claude process -- add pgrep for 'continuous-claude' to the activity check so it doesn't auto-shutdown while tasks are running.
  - PR title: "fix: idle monitor detects continuous-claude as active"

## Phase 2: MCP + Browser (out-of-box automation)

- [ ] Populate components.yaml with mcp-manager and blueprint-extra-mcp entries -- both as private repos under grobomo org, type mcp, targets /opt/mcp/mcp-manager and /opt/mcp/blueprint-extra-mcp.
  - PR title: "feat: add mcp-manager and blueprint-extra to components.yaml"

- [ ] Create config/servers.yaml for container -- Linux-native paths, blueprint-extra enabled with auto_start, command=node args=[/opt/mcp/blueprint-extra-mcp/run-server.js]. Copy to /opt/mcp/mcp-manager/servers.yaml during bootstrap.
  - PR title: "feat: container-native servers.yaml for mcp-manager"

- [ ] Write .mcp.json in bootstrap.sh -- create /home/claude/.mcp.json pointing to mcp-manager (command=node, args=[/opt/mcp/mcp-manager/build/index.js]). Must happen after MCP deps install step.
  - PR title: "feat: auto-configure .mcp.json for mcp-manager in bootstrap"

- [ ] Modify browser.sh to load blueprint-extra Chrome extension -- if /opt/mcp/blueprint-extra-mcp/extensions/ exists, add --load-extension flag to Chrome launch command.
  - PR title: "feat: auto-load blueprint Chrome extension in browser.sh"

## Phase 3: Observability (remote status checking)

- [ ] Add `cpp status [name]` command -- SSH to instance, show continuous-claude status (running/stopped/complete, last iteration time, tasks remaining, last PR, error count), daemon status (idle monitor, state sync, web chat), and open PRs.
  - PR title: "feat: add cpp status command for remote monitoring"

- [ ] Add `cpp logs [name]` command -- SSH to instance, tail /data/continuous-claude.log. Support -f flag for follow mode and -n for line count.
  - PR title: "feat: add cpp logs command to tail continuous-claude"

- [ ] Add --continuous flag to cpp launcher -- `cpp --name X --continuous <repo-url>` sets CONTINUOUS_CLAUDE_ENABLED=true and CONTINUOUS_CLAUDE_REPO in the instance .env before docker compose up. Optional --branch flag.
  - PR title: "feat: add --continuous flag to cpp launcher"
