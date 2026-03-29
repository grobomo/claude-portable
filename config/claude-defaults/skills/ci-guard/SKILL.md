---

name: ci-guard
description: Set up GitHub Actions quality gates for repos. Blocks PRs with personal paths, secrets, bad structure, CRLF. Use when user says "ci guard", "quality gate", "github actions check", "block bad PRs".
keywords:
  - ci
  - guard
  - quality
  - gate
  - github
  - actions
  - workflow
  - sanitize
  - block
  - pr
  - compliance
  - safe
  - publish
  - bad
  - prs
enabled: true
---

# CI Guard

Set up GitHub Actions quality gate workflows that block bad code from merging.
Works on any repo -- marketplace repos, public projects, internal tools.

## What It Creates

A `.github/workflows/quality-gate.yml` that runs on PRs and push-to-main with these checks:

| Check | What It Catches | Exit Code |
|-------|----------------|-----------|
| **Personal path scan** | Hardcoded `C:/Users/...`, `OneDrive - ...`, personal usernames | 1 (fail) |
| **Secret scan** | Plaintext tokens, API keys, .env files, GitHub PATs | 1 (fail) |
| **Structure validation** | Missing plugin.json fields, invalid JSON, missing SKILL.md frontmatter | 1 (fail) |
| **Registry check** | Pre-populated registry files (must ship empty) | 1 (fail) |
| **Line ending check** | CRLF in text files (must be LF) | 1 (fail) |

## When to Use

- Setting up a new public/shared repo
- Adding quality gates to an existing marketplace repo
- User says "ci guard", "quality gate", "block bad PRs", "sanitize check"
- After a publish-sanitize incident (hardcoded paths shipped)

## Usage

```
/ci-guard                     # Set up for current repo
/ci-guard --marketplace       # Marketplace-specific (plugin structure checks)
/ci-guard --paths-only        # Just the personal path scan
```

## Modes

### Default (any repo)
- Personal path scan
- Secret scan
- Line ending check

### Marketplace mode (`--marketplace`)
All default checks PLUS:
- Plugin structure validation (plugin.json, SKILL.md frontmatter)
- Registry file check (must be empty templates)
- Marketplace.json tag sync check

## How to Set Up

### Step 1: Detect repo type

Check what's in the repo:
- Has `plugins/` dir? -> marketplace mode
- Has `.claude-plugin/` dir? -> single plugin mode
- Neither? -> general repo mode

### Step 2: Generate workflow

Create `.github/workflows/quality-gate.yml` with checks appropriate for the repo type.

### Step 3: Configure personal path patterns

The workflow needs to know what personal patterns to scan for. Read from:
1. The publish-sanitize rule (`~/.claude/rules/UserPromptSubmit/publish-sanitize.md`) if it exists
2. Fall back to defaults: `C:/Users/`, `C:\\Users\\`, `OneDrive -`, `/Users/[a-z]`

The user should add their own username patterns to the workflow after generation.

### Step 4: Enable branch protection

```bash
# Require quality-gate to pass before merge
gh api repos/OWNER/REPO/branches/main/protection \
  -X PUT \
  -f "required_status_checks[strict]=true" \
  -f "required_status_checks[contexts][]=sanitize-check" \
  -f "required_status_checks[contexts][]=structure-check" \
  -f "required_status_checks[contexts][]=line-endings" \
  -f "enforce_admins=false" \
  -f "required_pull_request_reviews[required_approving_review_count]=0"
```

### Step 5: Test

Push a test branch with a known-bad file (hardcoded path) and verify the workflow catches it.

## Personal Path Patterns

Default patterns scanned (customize per user):

```yaml
PATTERNS:
  - 'C:/Users/'
  - 'C:\\Users\\'
  - '/Users/[a-z]'
  - 'OneDrive -'
```

Users should add their own patterns:
- Their username (e.g., `${USER_NAME}`, `henryar`)
- Their GitHub username (e.g., `${TMEMU_ACCOUNT}`)
- Their org-specific paths (e.g., `OneDrive - TrendMicro`)
- Their test account names (e.g., `joeltest`)

## Secret Patterns

Scans for:
- `TOKEN="..."`, `KEY="..."`, `SECRET="..."`, `PASSWORD="..."` with long values
- GitHub PATs: `ghp_*`, `github_pat_*`
- OpenAI/Anthropic keys: `sk-*`
- `.env` files in the repo

## Reference Implementation

The grobomo marketplace repo has a working example:
`grobomo/claude-code-skills/.github/workflows/plugin-quality-gate.yml`

## Do NOT

- Do NOT skip the secret scan -- even "internal" repos leak
- Do NOT allow .env files in version control
- Do NOT ship pre-populated registry files
- Do NOT use CRLF line endings in shared repos
