# Git Credential Helper -- Use gh CLI, Not Windows Credential Manager

## Problem

Git for Windows ships with Git Credential Manager (GCM) which pops up a password dialog when pushing to a repo where the stored credential doesn't match the target account. This happens when the global git user is tmemu but the repo belongs to grobomo.

## Fix

Every grobomo repo must have this local git config:

```bash
git config credential.helper '!gh auth git-credential'
```

This tells git to use `gh auth` for credentials instead of GCM. Combined with `gh auth switch --user grobomo` before push, it works seamlessly with no popups.

## When to Apply

- When cloning or initializing any grobomo repo
- When a `git push` fails with 403 or triggers a credential popup
- As part of the push workflow (check if already set)

## Check

```bash
git config credential.helper
# Should output: !gh auth git-credential
# If it outputs "manager" or "manager-core", fix it
```
