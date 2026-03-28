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
