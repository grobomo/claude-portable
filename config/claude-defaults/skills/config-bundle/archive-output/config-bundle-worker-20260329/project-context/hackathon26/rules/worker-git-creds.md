# Worker Git Credential Gotcha

- Workers have TWO gitconfigs: `/root/.gitconfig` and `/home/claude/.gitconfig`
- `inject-secrets.sh` writes to root; `cred-refresh` daemon writes to claude user
- `url.insteadOf` rules in gitconfig override `.git-credentials` and credential helpers
- If worker can't access a repo, check BOTH gitconfigs for stale `insteadOf` entries
- Dispatcher needs tmemu token (for RONE-boothapp-bridge). Workers need grobomo token (for altarr/boothapp).
- `GITHUB_TOKEN` env var in docker-compose overrides `gh auth login` — must unset or change at env level
