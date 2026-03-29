# Git Credential Helper Escape Gotcha

- `git config credential.helper '!gh auth git-credential'` shows as `\!gh auth git-credential` in output
- The `\!` is git's display escaping, not the actual stored value — it works correctly
- The `store` callback may error (`line 1: !gh: command not found`) but reads still work
- If push fails with "Repository not found", check `gh auth switch` is on the right account first
