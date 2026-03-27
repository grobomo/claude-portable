# continuous-claude rules

## CRITICAL: Micro-PRs every 15-20 minutes

User monitors progress from GitHub Mobile. Create a PR after EVERY meaningful step -- not one giant PR at the end. Each task in TODO.md = exactly 1 PR.

Each PR title should match the "PR title" specified in TODO.md for that task.

## CRITICAL: Security -- no secrets or personal paths

This is a PUBLIC grobomo repo. Before every commit:
- No hardcoded API keys, tokens, or secrets
- No personal Windows paths (C:\Users\username\...)
- No subscription IDs, account IDs, or SAS tokens
- Use env vars and placeholders instead of real values
- Check: `grep -rn 'C:/Users/' . --exclude-dir=.git --include='*.sh' --include='*.json' --include='*.js' --include='*.yml'` should return nothing (except rewrite-paths.sh regex patterns)

## Workflow

1. Read TODO.md -- pick the FIRST unchecked `- [ ]` task
2. Create branch: `git checkout -b continuous-claude/task-N`
3. Push branch and open PR: `gh pr create --title "<PR title from TODO>" --body "Starting task..."`
4. Do the work. Push commits as you go.
5. When done, mark task `- [x]` in TODO.md, commit, push.
6. Merge: `gh pr merge --squash --delete-branch`
7. STOP. Do not proceed to next task.

## Gotchas

- Must be on `main` branch before starting each iteration
- `continuous-claude.log` is in .gitignore -- never commit it
- All scripts must use LF line endings (not CRLF)
- Test script syntax with `bash -n <script>` before committing
- The secret-scan.yml GitHub Action will block PRs with secrets -- check locally first

## Architecture context

- Container runs Debian bookworm with Node 20
- Claude user home: /home/claude
- Config: /home/claude/.claude/
- MCP servers: /opt/mcp/
- Scripts: /opt/claude-portable/scripts/
- Persistent data: /data/
- Workspace: /workspace/
- Chrome + Xvfb + VNC already installed in Dockerfile
- bootstrap.sh is the container entrypoint -- runs steps in order
