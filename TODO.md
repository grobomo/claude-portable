# Teams Integration — Continuous Claude Tasks

## Phase 0: Dedicated Dispatcher Instance

- [x] Create `scripts/dispatcher-daemon.sh` — pulls Graph token from Secrets Manager, pulls SSH keys from S3, starts teams-dispatch.py with watchdog loop (auto-restart on crash), streams logs to /data/dispatcher.log
  - PR title: "feat: add dispatcher daemon script"

- [x] Create `cloudformation/dispatcher.yaml` — CF template for dispatcher IAM role: Secrets Manager read, EC2 describe/start/stop, S3 read/write for keys + heartbeat + logs
  - PR title: "feat: add dispatcher CloudFormation template"

- [x] Update `ccc` launcher to support `--role dispatcher` flag — launches t3.small (no Chrome), runs dispatcher-daemon.sh instead of normal bootstrap, tags instance with Role=dispatcher
  - PR title: "feat: add dispatcher role to ccc launcher"

- [ ] Create S3 key-sharing: on worker launch, upload SSH public key to `s3://claude-portable-state-{account}/fleet-keys/`. Dispatcher pulls all keys at boot + every 5 min.
  - PR title: "feat: SSH key sharing via S3 for fleet"

- [ ] Update `teams-dispatch.py` to run headless on dispatcher: read Graph token from file (not msgraph-lib), discover workers via EC2 API tags (not ccc list), SSH to workers directly
  - PR title: "feat: make teams-dispatch cloud-native (no laptop deps)"

- [ ] Add dispatcher heartbeat: write timestamp to S3 every 60s, create CloudWatch alarm for heartbeat age > 5min, SNS email alert
  - PR title: "feat: add dispatcher heartbeat + CloudWatch monitoring"

- [ ] Create Lambda auto-healer: triggered by SNS alarm, checks dispatcher EC2 state, restarts if stopped, launches new if terminated
  - PR title: "feat: add Lambda auto-healer for dispatcher"

- [ ] Add health endpoint to dispatcher: HTTP server on port 8080, returns JSON with dispatch loop status, worker reachability, Graph token validity, pending requests, error count
  - PR title: "feat: add dispatcher health endpoint"

- [ ] End-to-end test: launch dispatcher + 2 workers via ccc, send @claude prompt in Teams, verify ACK + dispatch + result + Teams reply
  - PR title: "test: end-to-end dispatcher + worker validation"
