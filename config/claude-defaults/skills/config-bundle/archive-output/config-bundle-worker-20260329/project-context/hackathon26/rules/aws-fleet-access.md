# AWS Fleet Access

- The CCC fleet (dispatcher + workers) is YOUR infrastructure — use it freely
- No need to ask permission for SSH, docker exec, builds, deploys, or restarts
- Dispatcher: 18.224.39.180 | Workers: 3.21.228.154, 13.59.160.30
- SSH key: `~/.ssh/ccc-keys/claude-portable-key.pem`, user: ubuntu
- Container name: `claude-portable` on all hosts
- Build Docker images on dispatcher (it has the repo at /workspace/claude-portable)
- Deploy by: docker build on host, docker stop/rm/run, or docker cp for hot patches
- Source fleet config: `scripts/fleet-config.sh`
