# EC2 Instance Naming

- `ccc` launcher prefixes names with `ccc-` (e.g. `worker-1` → `ccc-worker-1`).
- SSH keys in `~/.ssh/ccc-keys/` use the unprefixed name (`worker-1.pem`).
- S3 fleet keys must use the prefixed name (`ccc-worker-1.pem`) to match EC2 tag lookup.
- `max_instances` is the config key (not `max_workers`).
