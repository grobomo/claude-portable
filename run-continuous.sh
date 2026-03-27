#!/usr/bin/env bash
# Continuous-claude loop: picks one TODO task per iteration, creates a PR, repeats.
set -uo pipefail
cd "$(dirname "$0")"

PROMPT='Read TODO.md and .claude/rules/continuous-claude.md. Pick the FIRST unchecked task. Workflow:
1. Create a new branch from main (git checkout -b continuous-claude/task-N)
2. Push the branch and open a PR with gh pr create -- title = the PR title specified in TODO.md for that task, body = "Starting task..."
3. Do the actual work. Push commits to the branch as you go.
4. When done, mark the task done in TODO.md, commit, push.
5. Merge the PR with: gh pr merge --squash --delete-branch
Then stop. Do NOT proceed to the next task.

CRITICAL: You MUST merge the PR before stopping. If you stop without merging, the task loops forever.
CRITICAL: No secrets, personal paths, or hardcoded credentials in any file. This is a public repo.'

MAX_ERRORS=3
errors=0

while true; do
  echo "$(date '+%Y-%m-%d %H:%M:%S') === Starting iteration ===" >> continuous-claude.log

  # Pull latest main before each iteration
  git checkout main 2>/dev/null
  git pull origin main 2>/dev/null

  # Safety net: merge any open PR left by previous iteration that forgot to merge
  open_pr=$(gh pr list --state open --limit 1 --json number --jq '.[0].number' 2>/dev/null)
  if [ -n "$open_pr" ] && [ "$open_pr" != "null" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') Merging leftover PR #$open_pr from previous iteration" >> continuous-claude.log
    gh pr merge "$open_pr" --squash --delete-branch >> continuous-claude.log 2>&1
    git pull origin main 2>/dev/null
  fi

  # Check if all tasks done
  if ! grep -q '\[ \]' TODO.md 2>/dev/null; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') CONTINUOUS_CLAUDE_PROJECT_COMPLETE" >> continuous-claude.log
    break
  fi

  # Run one iteration
  claude -p --dangerously-skip-permissions "$PROMPT" >> continuous-claude.log 2>&1
  rc=$?

  if [ $rc -ne 0 ]; then
    errors=$((errors + 1))
    echo "$(date '+%Y-%m-%d %H:%M:%S') Iteration failed (rc=$rc, errors=$errors/$MAX_ERRORS)" >> continuous-claude.log
    if [ $errors -ge $MAX_ERRORS ]; then
      echo "$(date '+%Y-%m-%d %H:%M:%S') Too many errors, stopping." >> continuous-claude.log
      break
    fi
  else
    errors=0
  fi

  echo "$(date '+%Y-%m-%d %H:%M:%S') === Iteration complete ===" >> continuous-claude.log
  sleep 10
done
