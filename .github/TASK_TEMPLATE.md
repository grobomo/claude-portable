# Task Template

Every unchecked task in TODO.md must follow this format:

```markdown
- [ ] <one-line summary of the deliverable>
  - What: <one-line description of what will be built/changed>
  - Why: <what problem this solves, what breaks without it>
  - How: <technical approach, key files to modify, patterns to follow>
  - Acceptance: <specific testable criteria — commands to run, expected output>
  - Context: <links to related PRs, previous tasks, design decisions>
  - PR title: "<conventional commit format title>"
```

## Required Fields

| Field | Required | Description |
|-------|----------|-------------|
| What | Yes | One-line deliverable description |
| Why | Yes | Problem statement and motivation |
| How | Yes | Technical approach and key files |
| Acceptance | Yes | Testable pass/fail criteria |
| Context | No | Related PRs, tasks, conversations |
| PR title | Yes | Conventional commit format |

## Examples

Good:
```markdown
- [ ] Add rolling chat cache to dispatcher
  - What: dispatcher writes last 50 Teams messages to /data/chat-cache/group-chat.txt every poll cycle
  - Why: workers answering @claude messages have no conversation context, so replies like "what do those do" fail
  - How: in teams-chat-bridge.py poll_once(), after fetching messages, write them to txt
  - Acceptance: file exists after one poll cycle, contains 50 lines, each has [timestamp] sender: message format
  - Context: see PR #26 for quoted reply detection
  - PR title: "feat: rolling chat cache as txt files on dispatcher"
```

Bad:
```markdown
- [ ] Fix the thing
  - PR title: "fix: stuff"
```

## Enforcement

The task template checker (`.github/workflows/task-check.yml`) validates TODO.md on every push to main. Tasks missing required fields block the PR.
