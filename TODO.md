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

- [x] Worker registration: on boot, each worker calls `POST /worker/register {worker_id, ip, role, capabilities}` on the dispatcher. Dispatcher maintains a live fleet roster. Workers that don't register within 5 min of launch are terminated.
  - PR title: "feat: worker auto-registration with dispatcher"

### Fleet monitor (safety net)

Monitor runs on the dispatcher as a background thread. Catches cases where self-reporting fails.

- [x] Fleet monitor daemon: every 60s, iterate all registered workers. SSH health check (is the instance responding?). If a worker hasn't self-reported in 35 min AND has no active Claude process, tell dispatcher to stop it. This is the backup — self-reporting is primary.
  - PR title: "feat: fleet monitor daemon as safety net for scale-down"

- [x] Fleet monitor tests: test that monitor correctly identifies idle workers, doesn't kill busy workers, handles unreachable workers, respects the 35-min grace period.
  - PR title: "test: fleet monitor idle detection and safety checks"

### Backup dispatcher

- [x] Backup dispatcher: launch a second dispatcher instance (`ccc --name dispatcher-backup --role dispatcher`). It runs in standby mode — polls the primary dispatcher's heartbeat in S3. If heartbeat is stale (>5 min), the backup promotes itself to primary and takes over polling Teams + managing workers. Only one dispatcher polls Teams at a time (leader election via S3 heartbeat timestamp).
  - PR title: "feat: backup dispatcher with S3-based leader election"

- [x] Backup dispatcher tests: simulate primary failure (stop primary), verify backup takes over within 5 min, verify no duplicate Teams messages (only one poller active), verify backup stops polling when primary recovers.
  - PR title: "test: backup dispatcher failover and leader election"

### Task routing by app area

Dispatcher assigns tasks to the right worker based on which area of the app the task relates to. Each area has its own folder with context notes for workers.

- [x] Create app area folders in the repo: `areas/dispatcher/`, `areas/fleet/`, `areas/teams-integration/`, `areas/tdd-pipeline/`, `areas/infrastructure/`. Each folder has a `CONTEXT.md` with architecture notes, key files, gotchas, and design decisions for that area.
  - PR title: "feat: create app area folders with context docs"

- [x] Task routing: dispatcher reads the task description from TODO.md, matches keywords to app areas (e.g. "dispatcher" → areas/dispatcher, "test" → areas/tdd-pipeline), and includes the relevant `CONTEXT.md` in the prompt sent to the worker. Workers read the area context before starting work.
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

## URGENT: Chat context cache (must be built before any other feature)

The dispatcher must maintain a rolling cache of the Teams chat as txt files on disk. Before processing ANY @claude message, the dispatcher reads the cache to understand full context. This is not prompt engineering — it's a local file cache that Claude reads with its tools.

- [ ] Chat cache daemon: every poll cycle, fetch last 50 messages from the Teams chat via Graph API. Write them to `/data/chat-cache/group-chat.txt` as a simple transcript: `[timestamp] sender: message`. One file, always overwritten with the latest 50. Also maintain per-user files: `/data/chat-cache/users/{name}.txt` with last 20 messages from that specific user + Claude's replies to them.
  - PR title: "feat: rolling chat cache as txt files on dispatcher"

- [ ] Context-aware dispatch: when dispatching an @claude request, the prompt sent to the worker includes: (1) the full group-chat.txt so Claude sees recent conversation, (2) the user's personal history file so Claude knows prior back-and-forth with that user, (3) the new message. Claude reads these files with Read tool, not as inline prompt text. Copy them to the worker at dispatch time via SCP.
  - PR title: "feat: dispatch includes chat cache files for full context"

- [ ] Reply capture: after Claude responds, append both the prompt and response to the user's history file AND to group-chat.txt. This ensures the next request sees the full conversation including Claude's own replies.
  - PR title: "feat: capture Claude replies into chat cache"

- [ ] Test: send a message "what is 2+2", then immediately send "multiply that by 10". Verify Claude answers "40" because it has context from the first exchange.
  - PR title: "test: verify conversation continuity across messages"

## Worker management API

- [ ] Add HTTP health/control endpoint to each worker (port 8081): GET /health returns current task, stage, uptime. POST /interrupt kills the current Claude process and returns to idle. POST /pull forces a git pull on next iteration. This replaces manual SSH + pkill.
  - PR title: "feat: worker HTTP control API for interrupt and health"

- [ ] Wire worker control API into ccc CLI: `ccc interrupt worker-1` calls POST /interrupt. `ccc health worker-1` calls GET /health. No SSH needed.
  - PR title: "feat: ccc interrupt and health commands via worker API"

## Code quality enforcement

- [ ] Add REVIEW stage to TDD pipeline (runs after RESEARCH, before PLAN): Claude must read ALL files in the repo that relate to the current task. It must identify: (1) existing code that already does what the task asks, (2) dead code from previous tasks that should be removed, (3) conflicting implementations (e.g. two dispatch systems), (4) code that should be refactored to accommodate the new feature. Output to /tmp/task-{N}-review.md. If the review finds the task is already done or conflicts with existing code, the worker must REFACTOR first before adding new code.
  - PR title: "feat: mandatory code review stage in TDD pipeline"

- [ ] Refactor-first rule: if the REVIEW stage finds >3 files that need changes to accommodate the new feature, the worker must create a REFACTOR PR first (separate from the feature PR). Refactor PR cleans up, removes dead code, consolidates duplicates. Feature PR builds on top of the clean base. Never patch on top of spaghetti.
  - PR title: "feat: refactor-first rule when review finds messy codebase"

- [ ] Add `ccc cleanup` command: runs a one-off Claude invocation that reviews the entire codebase for dead code, duplicate implementations, unused files, and inconsistencies. Outputs a report and optionally creates a cleanup PR.
  - PR title: "feat: ccc cleanup command for codebase hygiene"

- [ ] Enforcement gates in continuous-claude.sh (NOT prompts — these are bash checks that block progression):
  Gate 1: RESEARCH output file must exist and be >500 chars. If not, stage fails.
  Gate 2: REVIEW output must list files examined. If it lists 0 files, stage fails.
  Gate 3: PLAN output must exist. If task is "already done" per review, skip to next task.
  Gate 4: Tests must exist in the repo after TESTS stage (count test files before/after, delta must be >0).
  Gate 5: Tests must FAIL before IMPLEMENT stage (run test suite, expect non-zero exit).
  Gate 6: Tests must PASS after IMPLEMENT stage (run test suite, expect zero exit).
  Gate 7: No secrets in diff (`grep -rn` check). No personal paths. Syntax check all changed files.
  Gate 8: PR diff must not contain "TODO" or "FIXME" or "HACK" in new lines.
  All gates are `if ! check; then echo "GATE FAILED"; exit 1; fi` — no exceptions.
  - PR title: "feat: enforcement gates between TDD pipeline stages"

- [ ] Add bash validation gates between each stage in continuous-claude.sh. These are NOT prompts — they are bash checks that block progression with exit 1:
  After RESEARCH: `[ -f research_file ] && [ $(wc -c < research_file) -gt 100 ]`
  After PLAN: `[ -f plan_file ] && [ $(wc -c < plan_file) -gt 100 ]`
  After TESTS: count test files added to branch (git diff --name-only must include test files). Run test command, verify exit code != 0 (tests must fail before implementation).
  After IMPLEMENT: run test command, verify exit code == 0 (all tests pass).
  After VERIFY: run secret scan, syntax check all changed files, no TODO/FIXME/HACK in new lines.
  If any gate fails, retry the stage. If still fails after max retries, skip the task and log the failure.
  - PR title: "feat: bash validation gates between TDD pipeline stages"

## Neural Pipeline integration for worker tracking

Adapt the Neural Pipeline (react/tui.py) architecture for CCC workers. Each worker tracks its task through pipeline phases. Dispatcher aggregates status from all workers into a live dashboard.

- [ ] Create `scripts/worker-pipeline.py` — adapted from Neural Pipeline concepts. Each worker runs this alongside continuous-claude.sh. It tracks the current task through phases (RESEARCH → REVIEW → PLAN → TESTS → IMPLEMENT → VERIFY → PR). Writes phase state to `/data/pipeline-state.json` with: task number, current phase, phase start time, phase output files, pass/fail per gate. Exposes HTTP API on port 8081: GET /status returns pipeline state, POST /interrupt kills current Claude process, POST /pull forces git pull.
  - PR title: "feat: worker pipeline tracker with HTTP control API"

- [ ] Worker polls dispatcher every 30s: POST /worker/heartbeat with current pipeline state (task, phase, idle time). Dispatcher maintains fleet roster from heartbeats. If a worker misses 3 heartbeats, dispatcher marks it unhealthy.
  - PR title: "feat: worker heartbeat polling to dispatcher"

- [ ] Dispatcher aggregates pipeline state from all workers into `/data/board.json`. Updated on every heartbeat received. Shows: all tasks, which worker has which task, what phase each is in, time in phase, blocked tasks, completed tasks.
  - PR title: "feat: dispatcher aggregates worker pipeline state into board"

- [ ] `ccc board` command: reads board.json from dispatcher health endpoint (GET /board), renders a status bar showing each worker and its current phase. Inspired by Neural Pipeline TUI status bar. Color-coded: RESEARCH=blue, PLAN=cyan, TESTS=yellow, IMPLEMENT=green, VERIFY=magenta, PR=white, IDLE=gray.
  - PR title: "feat: ccc board command with pipeline status visualization"

- [ ] Dispatcher can interrupt workers via API: POST to worker's /interrupt endpoint. Used by `ccc interrupt worker-1` and by dispatcher when reprioritizing tasks.
  - PR title: "feat: dispatcher interrupts workers via HTTP API"

- [ ] Set up Neural Pipeline (react/) as a ccc-managed project. Create TODO.md in react/ with improvement tasks. Workers develop it using continuous-claude with branches/PRs against the react repo. First tasks: fix monitor status bar, make phases actually enforce gates, add API endpoint for status queries.
  - PR title: "feat: bootstrap Neural Pipeline as ccc-managed project"

- [ ] Worker sends immediate phase transition event to dispatcher when moving between stages (not waiting for next heartbeat). POST /worker/phase-change {worker_id, task, old_phase, new_phase, gate_result}. Dispatcher logs these for audit trail and updates board.json instantly.
  - PR title: "feat: immediate phase transition events from workers to dispatcher"

- [ ] Add WHY phase as stage 0 in worker pipeline (before RESEARCH). Claude must answer: Why does this task need to exist? What problem does it solve? Is there already a simpler solution? Should this task be rejected, merged with another task, or split into smaller tasks? If WHY phase concludes the task is unnecessary or duplicate, worker skips it and marks it in TODO.md with a note. Gate: WHY output must explicitly state "PROCEED" or "SKIP" — if neither, gate fails.
  - PR title: "feat: add WHY phase to worker TDD pipeline"

- [ ] Worker pushback flow: if a worker is blocked (WHY phase says task is unclear, SCOPE has ambiguity, gate fails repeatedly, or worker needs human input), it sends POST /worker/blocked {worker_id, task, phase, reason, question} to dispatcher. Dispatcher relays the question to Teams chat and/or interactive chatbot session. The task is paused until a human replies. When human replies, dispatcher sends the answer back to the worker via POST /answer on the worker's API. Worker resumes from where it left off with the new context.
  - PR title: "feat: worker pushback flow for blocked tasks with human-in-the-loop"

- [ ] Pipeline task folder: each task gets `/data/pipeline/task-{N}/` with numbered output files per phase (00-why.md, 01-research.md, 02-review.md, 03-scope.md, 04-tests.md, 05-implement.md, 06-verify.md, 07-pr.md, stage-log.json). Each stage's prompt instructs Claude to read ALL prior .md files in the folder before starting. Gate enforcement: script checks the expected output file exists and is >100 chars before allowing next stage. Reviewer Claude reads all files to check cross-phase consistency.
  - PR title: "feat: structured pipeline task folder with enforced file chain"

- [ ] Reviewer Claude at each gate: after each stage, a SEPARATE claude -p invocation reviews the output. Prompt: "You are a reviewer. You did NOT write this. Read all files in /data/pipeline/task-{N}/. Rate the latest stage output 1-5. If <3, output REJECT with reasons. If >=3, output APPROVE." If rejected, stage retries with the rejection feedback appended. Max 2 rejections before task is marked blocked.
  - PR title: "feat: separate reviewer Claude at each pipeline gate"

- [ ] Commit pipeline folder to PR branch: the task folder `/data/pipeline/task-{N}/` is copied into the repo at `.pipeline/task-{N}/` and committed to the branch before PR creation. All phase outputs (why, research, review, scope, tests, implement, verify), stage-log.json, and reviewer feedback are included in the PR. This provides a full audit trail of how the task was completed. Reviewers can see the thinking process, not just the final code.
  - PR title: "feat: include pipeline audit trail in PR commits"

## Task submission template (enforced)

Every task in TODO.md must follow a standard template. A pre-commit hook or CI check rejects tasks that don't conform. Workers use this context to accurately complete work without guessing.

- [ ] Define task template format in `.github/TASK_TEMPLATE.md`. Every unchecked TODO item must have these fields (indented under the checkbox line):
  - **What**: one-line description of the deliverable
  - **Why**: what problem this solves, what breaks without it, user/conversation context that motivated it
  - **How**: technical approach, key files to modify, patterns to follow from existing code
  - **Acceptance**: specific testable criteria (not "it works" — exact commands to run, expected output)
  - **Context**: links to related PRs, previous tasks, conversation excerpts, or design decisions
  - **PR title**: the PR title to use
  Example:
  ```
  - [ ] Add rolling chat cache to dispatcher
    - What: dispatcher writes last 50 Teams messages to /data/chat-cache/group-chat.txt every poll cycle
    - Why: workers answering @claude messages have no conversation context, so replies like "what do those do" fail because Claude doesn't know what "those" refers to (from session 2026-03-28)
    - How: in teams-dispatch.py poll_once(), after fetching messages, write them to txt. Include sender, timestamp, body. Overwrite each cycle.
    - Acceptance: file exists after one poll cycle, contains 50 lines, each line has [timestamp] sender: message format
    - Context: see PR #26 for quoted reply detection, dispatcher-daemon.sh for poll lifecycle
    - PR title: "feat: rolling chat cache as txt files on dispatcher"
  ```
  - PR title: "feat: define task submission template"

- [ ] Task template checker: GitHub Action or pre-commit hook that parses TODO.md and rejects commits where unchecked tasks are missing any of the required fields (What/Why/How/Acceptance). Runs on every push to main. Blocks merge if template is incomplete.
  - What: CI gate that validates task format
  - Why: workers built broken features because tasks said "do X" without explaining why or how to verify
  - How: Python script that parses TODO.md, finds unchecked items, checks for required subsections
  - Acceptance: push a task missing "Why" field, CI fails with clear error message
  - Context: this was identified in session 2026-03-28 after dispatcher bugs stacked up from vague tasks
  - PR title: "feat: task template checker CI gate"

- [ ] Retrofit existing TODO items to follow the template. Go through all unchecked tasks, add missing Why/How/Acceptance fields based on the conversation context from this session and PR history.
  - What: backfill context on all existing tasks
  - Why: current tasks are one-liners that workers will misinterpret
  - How: read each task, find the related conversation context in this chat export, add the fields
  - Acceptance: every unchecked task in TODO.md passes the template checker
  - Context: the entire conversation from session 2026-03-28
  - PR title: "chore: retrofit existing tasks with full template context"

- [ ] Chatbot auto-fills task template: when a user requests a feature via Teams or web chat, the chatbot fills in all template fields (What/Why/How/Acceptance/Context) based on the conversation. It shows the filled template to the user and asks "Does this look right?" before committing to TODO.md. User can say "yes" or correct it. This ensures workers get full context without users having to write structured docs.
  - What: chatbot generates structured task from conversational request
  - Why: users say "add dark mode" but workers need What/Why/How/Acceptance to build it right. The conversation context that explains WHY is in the chat, not in the user's head.
  - How: chatbot reads recent conversation history, extracts the motivation and requirements, fills the template, confirms with user, commits to TODO.md
  - Acceptance: user says "add rolling chat cache", chatbot generates full template with all 6 fields, user confirms, task appears in TODO.md with complete context
  - Context: from session 2026-03-28 — dispatcher bugs stacked up because tasks were one-liners without context
  - PR title: "feat: chatbot auto-fills task template from conversation"

## CRITICAL: Worker zero-touch boot

- [ ] Workers must be fully autonomous from boot. bootstrap.sh must: (1) clone the repo from ccc.config.json repo_url, (2) start continuous-claude.sh as a daemon, (3) register with dispatcher, (4) upload SSH key to S3 fleet-keys bucket. NO manual SSH, NO manual git clone, NO manual process startup. The `ccc --name worker-N --new` command should result in a worker that is picking up tasks within 5 minutes with zero human intervention. Test by launching a fresh worker and verifying it picks up a task and creates a PR without any manual steps.
  - What: workers auto-start continuous-claude and register with dispatcher on boot
  - Why: currently every new worker requires manual SSH to clone repo, set git config, start continuous-claude, upload keys. This is unacceptable — the whole point of the fleet is autonomous operation.
  - How: update bootstrap.sh to detect worker role, clone repo, inject GITHUB_TOKEN, start continuous-claude daemon, call dispatcher registration endpoint, upload SSH public key to S3
  - Acceptance: `ccc --name worker-test --new` → wait 5 min → worker has an open PR on the repo. Zero manual steps.
  - Context: session 2026-03-28 — every worker launch required manual intervention to start working
  - PR title: "fix: worker zero-touch boot with auto-start continuous-claude"
