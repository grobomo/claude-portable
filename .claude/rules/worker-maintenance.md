# Worker Maintenance Mode

- `touch /data/.maintenance` pauses task pickup. `rm /data/.maintenance` resumes.
- Current task finishes normally. SSH/web-chat unaffected.
- As of 2026-03-28: workers 1-4 are in maintenance mode pending dispatcher refactor.
- Resume with: `ccc maint worker-N --off` or SSH and `rm /data/.maintenance`.
