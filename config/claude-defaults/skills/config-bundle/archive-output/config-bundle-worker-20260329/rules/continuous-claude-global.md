# Continuous Claude -- Global Rules (all projects)

## Phone Notifications
- Watch the repo (`gh api repos/OWNER/REPO/subscription -X PUT --input - <<< '{"subscribed":true,"ignored":false}'`)
- GitHub Mobile push notifications for every PR created/merged
- User expects updates every 10-15 minutes -- each PR is a micro-task, not a giant changeset

## PR Strategy
- ONE small task per PR -- never batch multiple TODO items into one PR
- PRs auto-merge (no approval required, `allow_auto_merge=true` on repo)
- `delete_branch_on_merge=true` -- branches auto-clean after merge
- Squash merge strategy

## Prompt Pattern
- Point at TODO.md as the task list
- Each iteration = pick ONE unchecked item, do it, PR it
- Leave notes in TODO.md for the next iteration
- Output CONTINUOUS_CLAUDE_PROJECT_COMPLETE when all items done

## Gotchas
- Must start from `main` branch -- stale iteration branches cause "failed to create branch"
- Add `continuous-claude.log` to .gitignore before starting
- `ps aux` doesn't show child processes on Git Bash -- use `tasklist | grep claude`
- `nohup` log buffers -- use `tail -f` to monitor
- If 3 consecutive errors, it dies -- check log, clean branches, restart
