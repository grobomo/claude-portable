# Teams Integration — Continuous Claude Tasks

## Phase 0: Dedicated Dispatcher Instance

- [x] Create `scripts/dispatcher-daemon.sh` — pulls Graph token from Secrets Manager, pulls SSH keys from S3, starts teams-dispatch.py with watchdog loop (auto-restart on crash), streams logs to /data/dispatcher.log
  - PR title: "feat: add dispatcher daemon script"

- [x] Create `cloudformation/dispatcher.yaml` — CF template for dispatcher IAM role: Secrets Manager read, EC2 describe/start/stop, S3 read/write for keys + heartbeat + logs
  - PR title: "feat: add dispatcher CloudFormation template"

- [x] Update `ccc` launcher to support `--role dispatcher` flag — launches t3.small (no Chrome), runs dispatcher-daemon.sh instead of normal bootstrap, tags instance with Role=dispatcher
  - PR title: "feat: add dispatcher role to ccc launcher"

- [x] Create S3 key-sharing: on worker launch, upload SSH public key to `s3://claude-portable-state-{account}/fleet-keys/`. Dispatcher pulls all keys at boot + every 5 min.
  - PR title: "feat: SSH key sharing via S3 for fleet"

- [x] Update `teams-dispatch.py` to run headless on dispatcher: read Graph token from file (not msgraph-lib), discover workers via EC2 API tags (not ccc list), SSH to workers directly
  - PR title: "feat: make teams-dispatch cloud-native (no laptop deps)"

- [x] Add dispatcher heartbeat: write timestamp to S3 every 60s, create CloudWatch alarm for heartbeat age > 5min, SNS email alert
  - PR title: "feat: add dispatcher heartbeat + CloudWatch monitoring"

- [x] Create Lambda auto-healer: triggered by SNS alarm, checks dispatcher EC2 state, restarts if stopped, launches new if terminated
  - PR title: "feat: add Lambda auto-healer for dispatcher"

- [x] Add health endpoint to dispatcher: HTTP server on port 8080, returns JSON with dispatch loop status, worker reachability, Graph token validity, pending requests, error count
  - PR title: "feat: add dispatcher health endpoint"

- [x] End-to-end test: launch dispatcher + 2 workers via ccc, send @claude prompt in Teams, verify ACK + dispatch + result + Teams reply
  - PR title: "test: end-to-end dispatcher + worker validation"

## Phase 0.5: Dispatcher bugs (must fix before deploy)

- [x] Fix dispatcher-daemon.sh: uses /run/dispatcher which is not writable by claude user. Change to /data/dispatcher. Verify the fix is in the Dockerfile COPY or the git source that gets pulled at container build time.
  - PR title: "fix: dispatcher token path uses /data instead of /run"

- [x] Fix dispatcher container git pull: `/opt/claude-portable` is owned by root but container runs as claude. Either chown during build, or use a separate clone dir. The dispatcher needs to pull latest code at startup.
  - PR title: "fix: dispatcher container file ownership for git pull"

- [x] Fix dispatcher DISPATCHER_CHAT_ID: the chat ID must be passed via .env file or ccc.config.json, not manually injected. Update ccc launcher --role dispatcher to prompt for or read chat ID from config and pass it to docker compose.
  - PR title: "fix: dispatcher reads chat ID from ccc config"

- [x] Verify dispatcher boots clean from `ccc --name dispatcher --role dispatcher` with zero manual intervention. It must: pull graph token from Secrets Manager, start dispatch loop, discover workers, poll Teams, ACK + dispatch + post results. Test by launching fresh and sending @claude in Teams.
  - PR title: "test: dispatcher zero-touch boot verification"

## Phase 1: Teams UX improvements

- [x] Detect quoted replies to [Claude Bot] messages as new prompts — even without @claude tag. Teams wraps replies in `<attachment>` tags referencing the original message. If someone replies to a bot message, treat the reply text as a follow-up request.
  - PR title: "feat: detect quoted replies to bot messages as prompts"

- [x] For SSH requests: launch interactive instance, upload the .pem key file to Teams chat as an attachment (Graph API file upload), post the SSH command. Also include web chat URL as an alternative.
  - PR title: "feat: upload SSH key to Teams chat for access requests"

- [x] Add `ccc work` command — show what each worker is doing: current branch, PR status (open/merged), task progress, maintenance mode
  - PR title: "feat: add ccc work command for fleet activity view"

## Phase 2: Team chatbot instance

Chatbot is the SINGLE human-facing interface. All human interaction goes through it — Teams, web chat, SSH. Git is the coordination layer between chatbot, dispatcher, and workers.

Architecture:
- Chatbot receives requests (Teams @claude, web chat, SSH)
- Chatbot answers questions directly (reads git for latest state)
- Chatbot submits work by adding TODO items + committing to git
- Dispatcher watches git for unchecked TODO items, scales workers
- Workers claim tasks via branches, do the work, merge PRs
- Chatbot sees results on next git pull

Dispatcher NO LONGER polls Teams. It only watches git + manages EC2 fleet.

- [x] Create `chatbot` role in ccc launcher: launches t3.large, clones repo, starts web-chat.js + Teams polling, exposes via Lambda URL. Does NOT run continuous-claude (it's not a worker).
  - PR title: "feat: add chatbot role to ccc launcher"

- [x] Move Teams polling from dispatcher to chatbot: chatbot runs teams-dispatch.py (renamed to teams-chat-bridge.py). When it detects @claude, it processes the message itself via Claude (not fire-and-forget to a worker). If work is needed, chatbot adds a TODO item and pushes to git.
  - PR title: "feat: move Teams polling to chatbot, git-based task submission"

- [x] Multi-user sessions in web-chat.js: each WebSocket connection gets its own `claude` process with independent conversation context. Track sessions by user identifier (name prompt on connect or token param). Max 10 concurrent sessions. Logs to `/data/sessions/{user}/`.
  - PR title: "feat: multi-user sessions in web-chat.js"

- [x] Auto git-pull before every response: before Claude processes each prompt, run `git pull --rebase` in the workspace so Claude always sees the latest code from workers.
  - PR title: "feat: chatbot auto-pulls latest git before each response"

- [x] Chatbot CLAUDE.md with full project context: architecture overview, how to read TODO.md, how to check fleet status (git log, open PRs), how to submit feature requests (add TODO item, commit, push). Auto-updated on each git pull.
  - PR title: "feat: chatbot CLAUDE.md with project context"

- [x] Feature request flow: user says "add dark mode" → chatbot adds `- [ ] Add dark mode` to TODO.md → commits to branch → opens PR → merges → dispatcher sees new unchecked item → assigns worker. User gets PR link.
  - PR title: "feat: chatbot submits feature requests as TODO items"

- [x] Fleet status: user asks "what are workers doing?" → chatbot reads git (open branches, recent PRs, TODO.md progress), queries dispatcher health endpoint for live instance status.
  - PR title: "feat: chatbot exposes fleet status"

- [x] SSH auto-starts Claude Code: SSHing into chatbot auto-launches `claude --dangerously-skip-permissions` in the workspace. User lands in a Claude session with full context, not a bare shell.
  - PR title: "feat: SSH to chatbot auto-starts Claude Code"

- [x] Rate limiting: max 20 prompts/hour per user. Configurable via `CHATBOT_RATE_LIMIT` env var.
  - PR title: "feat: per-user rate limiting in chatbot"

Refactored dispatcher role:

- [x] Refactor dispatcher: remove Teams polling. Dispatcher now only watches git (polls `TODO.md` on main every 60s for unchecked items) and manages EC2 fleet (start/stop workers based on queue depth). Simpler, single responsibility.
  - PR title: "refactor: dispatcher watches git instead of Teams"

## Phase 3: Enforced TDD workflow in continuous-claude

The continuous-claude runner must enforce a strict TDD pipeline at the SCRIPT level (not prompts). Each worker takes its time — quality over speed. Scale out workers for parallelism, don't rush individual workers.

- [x] Rewrite continuous-claude.sh task execution as a multi-stage pipeline. For each task, Claude is invoked SEPARATELY for each stage (not one big prompt). Stages run sequentially with validation gates between them. The stages are:
  1. RESEARCH: WebSearch for existing solutions, patterns, best practices. Read all relevant existing code in the repo. Output a research summary to `/tmp/task-{N}-research.md`.
  2. PLAN: Based on research, write a plan: what files to create/modify, what the tests should verify, edge cases. Output to `/tmp/task-{N}-plan.md`.
  3. TESTS FIRST: Write tests that define the expected behavior. Tests MUST fail at this point (no implementation yet). Run tests, verify they fail. Commit tests to branch.
  4. IMPLEMENT: Write the minimum code to make tests pass. Run tests after each change. Iterate until ALL tests pass.
  5. VERIFY: Run full test suite. Run linter/syntax checks. Check for secrets. If anything fails, go back to IMPLEMENT.
  6. PR: Push, create PR, merge.
  Each stage is a separate `claude -p` invocation with the previous stage's output as context. If any stage fails, retry that stage (not the whole pipeline).
  - PR title: "feat: enforce multi-stage TDD pipeline in continuous-claude"

- [x] Add stage-level logging: each stage writes start/end timestamps and pass/fail to `/data/task-{N}-stages.json`. The `ccc work` command shows which stage each worker is on.
  - PR title: "feat: add stage-level logging to TDD pipeline"

- [x] Add test framework auto-detection: before running tests, detect the project's test framework (pytest, jest, go test, bash -n, etc.) from package.json/pyproject.toml/Makefile. If none found, use `bash -n` for shell scripts and basic assertion scripts.
  - PR title: "feat: auto-detect test framework in TDD pipeline"

## Phase 3: Fleet scaling, self-reporting workers, backup dispatcher

### Worker lifecycle (self-reporting)

Workers report their own status to the dispatcher. Dispatcher never has to guess.

- [x] Worker self-report: when a worker finishes a task (PR merged), it calls the dispatcher's health endpoint with `POST /worker/done {worker_id, task, duration}`. Dispatcher updates its fleet state and decides whether to assign another task or mark worker idle.
  - PR title: "feat: worker self-reports task completion to dispatcher"

- [x] Worker idle self-report: if a worker has been idle for 30 min with no new task, it calls `POST /worker/idle {worker_id, idle_since}` on the dispatcher. Dispatcher confirms and issues `stop-instances` via EC2 API. Worker waits for the stop — does NOT self-terminate.
  - PR title: "feat: worker self-reports idle status for scale-down"

### Dispatcher scaling logic

- [x] Scale up: when dispatcher receives an `@claude` request and all workers are busy, it launches a new worker via EC2 API (`ccc --name worker-N --new`). Cap at `max_instances` from ccc.config.json. New worker auto-registers with dispatcher on boot.
  - PR title: "feat: dispatcher auto-scales workers on demand"

- [x] Scale down: when dispatcher receives idle self-report from a worker, it confirms the worker isn't mid-task (checks for open PRs from that worker), then stops the instance. Logs the scale-down event.
  - PR title: "feat: dispatcher scale-down on worker idle self-report"

- [ ] Worker registration: on boot, each worker calls `POST /worker/register {worker_id, ip, role, capabilities}` on the dispatcher. Dispatcher maintains a live fleet roster. Workers that don't register within 5 min of launch are terminated.
  - PR title: "feat: worker auto-registration with dispatcher"

### Fleet monitor (safety net)

Monitor runs on the dispatcher as a background thread. Catches cases where self-reporting fails.

- [ ] Fleet monitor daemon: every 60s, iterate all registered workers. SSH health check (is the instance responding?). If a worker hasn't self-reported in 35 min AND has no active Claude process, tell dispatcher to stop it. This is the backup — self-reporting is primary.
  - PR title: "feat: fleet monitor daemon as safety net for scale-down"

- [ ] Fleet monitor tests: test that monitor correctly identifies idle workers, doesn't kill busy workers, handles unreachable workers, respects the 35-min grace period.
  - PR title: "test: fleet monitor idle detection and safety checks"

### Backup dispatcher

- [ ] Backup dispatcher: launch a second dispatcher instance (`ccc --name dispatcher-backup --role dispatcher`). It runs in standby mode — polls the primary dispatcher's heartbeat in S3. If heartbeat is stale (>5 min), the backup promotes itself to primary and takes over polling Teams + managing workers. Only one dispatcher polls Teams at a time (leader election via S3 heartbeat timestamp).
  - PR title: "feat: backup dispatcher with S3-based leader election"

- [ ] Backup dispatcher tests: simulate primary failure (stop primary), verify backup takes over within 5 min, verify no duplicate Teams messages (only one poller active), verify backup stops polling when primary recovers.
  - PR title: "test: backup dispatcher failover and leader election"

### Task routing by app area

Dispatcher assigns tasks to the right worker based on which area of the app the task relates to. Each area has its own folder with context notes for workers.

- [ ] Create app area folders in the repo: `areas/dispatcher/`, `areas/fleet/`, `areas/teams-integration/`, `areas/tdd-pipeline/`, `areas/infrastructure/`. Each folder has a `CONTEXT.md` with architecture notes, key files, gotchas, and design decisions for that area.
  - PR title: "feat: create app area folders with context docs"

- [ ] Task routing: dispatcher reads the task description from TODO.md, matches keywords to app areas (e.g. "dispatcher" → areas/dispatcher, "test" → areas/tdd-pipeline), and includes the relevant `CONTEXT.md` in the prompt sent to the worker. Workers read the area context before starting work.
  - PR title: "feat: dispatcher routes tasks to app areas with context"

- [ ] Area-specific workers: when a worker is assigned to an area, it stays on that area until idle. This avoids context-switching overhead. Dispatcher prefers re-assigning a worker to the same area it last worked on.
  - PR title: "feat: area-affinity for worker task assignment"

## Phase 5: Task dependency tracking

- [ ] Add dependency syntax to TODO.md: tasks can declare `depends-on: task-N` to indicate they can't start until task N is complete. The continuous-claude runner checks dependencies before claiming a task — if any dependency is unchecked, skip it and try the next task.
  - PR title: "feat: task dependency tracking in continuous-claude"

- [ ] Dependency visualization: `ccc work` shows a task graph with arrows between dependent tasks. Blocked tasks show as "waiting on #N".
  - PR title: "feat: dependency visualization in ccc work"

- [ ] Dispatcher dependency analysis: every 60s, dispatcher runs a Claude invocation that reads TODO.md + codebase and annotates tasks with `depends-on: task-N` where dependencies exist. Commits the annotated TODO.md back to main. This is fleet-level planning, not per-worker.
  - PR title: "feat: dispatcher auto-annotates task dependencies"

- [ ] Workers skip blocked tasks: continuous-claude.sh checks `depends-on:` annotations before claiming. If any dependency task is unchecked, skip to the next unblocked task. Log "task N blocked by task M" in the output.
  - PR title: "feat: workers skip tasks with unmet dependencies"

## URGENT: Conversation context in Teams dispatch

- [ ] Track per-user conversation history in dispatcher state. Each user gets a conversation buffer (last 20 messages + responses). When dispatching a new request, prepend the user's recent conversation as context so Claude knows what was discussed. Format: "Previous conversation with {user}:\n{history}\n\nNew message: {prompt}"
  - PR title: "feat: per-user conversation history in Teams dispatch"

- [ ] Include surrounding chat context: when dispatching, also include the last 5 messages from ALL users in the chat (not just the requester) so Claude has group conversation context. This handles "What do those do" type follow-ups that reference what someone else said.
  - PR title: "feat: include group chat context in dispatched prompts"

- [ ] Reply threading: when Claude replies to a request, store the reply alongside the original prompt in the conversation buffer. Next time that user sends @claude, the full back-and-forth is available as context.
  - PR title: "feat: store Claude replies in conversation buffer for continuity"
