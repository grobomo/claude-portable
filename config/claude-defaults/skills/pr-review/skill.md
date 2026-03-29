---

name: pr-review
description: Review and manage pull requests. PRs serve as approval gates for lab infrastructure changes.
triggers:
  - pr-review
  - review pr
  - list prs
  - show pull requests
  - merge pr
keywords:
  - pr
  - review
  - approve
  - change
  - prs
  - awaiting
  - --author
  - me
  - details
  - number
  - report
  - requests

---

# PR Review

PRs serve as **approval gates** for lab infrastructure changes.

## Approval Workflow

| User Action | Claude Response |
|-------------|-----------------|
| **Approve/Merge PR** | Execute the change, verify it works, report results |
| **Reject/Close PR** | Do nothing, discard the proposed change |

This ensures:
- User reviews all infrastructure actions before execution
- Full audit trail of changes over time
- Ability to reject risky changes

## When to Create PRs

Claude MUST create a PR before:
- Running commands on lab VMs (ESXi, AWS, etc.)
- Modifying network configurations
- Deploying/modifying CloudFormation stacks
- Changing Vision One settings
- Any action that impacts services or performance

## PR Structure

```
repo: lab-worker (or dedicated troubleshooting repo)
branch: fix/<issue-description>
content: 
  - README.md with diagnosis and proposed fix
  - Scripts to execute (if any)
  - Rollback plan
```

## Commands

```bash
# List open PRs awaiting approval
gh pr list --author @me --state open

# View PR details
gh pr view <number>

# After user approves - merge and execute
gh pr merge <number> --squash --delete-branch
# Then: Execute the proposed change
# Then: Verify and report results

# After user rejects - close without action
gh pr close <number>
```

## Example Workflow

```
1. User: "fix network on boof VM"

2. Claude: 
   - Diagnoses issue (read-only)
   - Creates PR with findings and proposed fix
   - Waits for user approval

3. User reviews PR:
   - Approve → Claude executes fix, verifies, reports
   - Reject → Claude does nothing

4. Audit trail preserved in git history
```

## Integration with Hooks

The `lab-infrastructure` hook automatically:
- Detects commands targeting lab resources
- Requires PR approval before execution
- Logs all approved actions
