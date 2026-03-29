# Dispatcher Deployment Gotchas

- Fleet is in hackathon AWS account (752266476357, us-east-2), deployed via CF stacks: ccc-dispatcher, ccc-worker-1, ccc-worker-2
- SSH key: `~/.ssh/ccc-keys/claude-portable-key.pem` (shared for all instances, user: ubuntu)
- Dispatcher IP: 18.224.39.180 | Workers: 3.21.228.154, 13.59.160.30
- Deployed code can be stale. Deploy: `scp` to host, `docker cp` into container, restart process
- Relay repo needs tmemu token (grobomo can't access tmemu private repos)
- Port 8080 is localhost-only in docker — workers can't auto-register externally
- Workers need manual registration via curl after dispatcher restart
- Per-worker SSH keys must exist at `~/.ssh/ccc-keys/{worker-name}.pem` inside the container
- `pgrep -f 'claude -p '` (with trailing space) is the correct idle check — `claude.*-p` matches `claude-portable` paths
