# Fleet Area

## What it does
EC2 instance lifecycle: launch, connect, monitor, stop. The `ccc` launcher is the single CLI for all fleet operations.

## Key files
- `ccc` — Python launcher: manages EC2 lifecycle, SSH, VNC, SCP, roles (worker/dispatcher/chatbot)
- `ccc.config.json` — launcher config: region, instance type, max_instances, idle timeout
- `cloudformation/claude-portable-spot.yaml` — spot instance CF template with IAM role
- `scripts/idle-monitor.sh` — auto-shutdown after N minutes idle
- `scripts/state-sync.sh` — S3 backup/restore for conversations + sessions
- `scripts/msg.sh` — inter-instance messaging via S3

## Architecture
- `ccc --name X --new` launches a new EC2 instance with docker-compose
- `ccc --name X` connects to existing instance via SSH
- Roles: `--role worker` (default), `--role dispatcher`, `--role chatbot`
- EC2 tags: Name, Project=claude-portable, Role=worker|dispatcher|chatbot
- SSH keys stored in `~/.ssh/ccc-keys/` (local) and S3 fleet-keys bucket (shared)
- Instance names prefixed with `ccc-` by launcher

## Gotchas
- Config key is `max_instances` (not `max_workers`)
- SSH keys use unprefixed name locally (`worker-1.pem`) but prefixed in S3 (`ccc-worker-1.pem`)
- Workers 1-4 currently in maintenance mode (touch /data/.maintenance)
