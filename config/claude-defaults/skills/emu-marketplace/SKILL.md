---

id: emu-marketplace
name: emu-marketplace
description: |
  Publish plugins to the internal emu marketplace (trend-ai-taskforce/ai-skill-marketplace).
  Validates format, fixes CRLF, syncs tags, creates PR, reviews and fixes Copilot comments.
keywords:
  - emu
  - emu-marketplace
  - ai-skill-marketplace
  - internal
  - marketplace
  - taskforce

enabled: true
---

# Emu Marketplace Publisher

Publish plugins to the internal emu marketplace at `trend-ai-taskforce/ai-skill-marketplace`.
Handles validation, format normalization, PR creation, and automated review fixing.

## When to Use

Called by publish-project skill (step 7) when a project has SKILL.md or plugin.json,
or directly when user wants to publish/update a plugin on the emu marketplace.

## Marketplace Details

- **Repo:** `trend-ai-taskforce/ai-skill-marketplace`
- **Auth:** `gh` CLI (logged in as ${TMEMU_ACCOUNT})
- **Categories:** development, documentation, testing, security, productivity, code-analysis, sdlc, ai-agents

## Plugin Structure (required)

```
plugins/<name>/
+-- .claude-plugin/
|   +-- plugin.json          # name, version, description, author, repository, license, keywords
+-- skills/<name>/
    +-- SKILL.md             # YAML frontmatter + skill content
```

## Full Publish Flow

### 1. Validate locally before cloning

Check the project has what's needed:
- SKILL.md or plugin.json exists in project
- If SKILL.md: has valid YAML frontmatter (starts with `---`)
- If standalone tool (no SKILL.md): create a SKILL.md for the marketplace that describes how Claude can help users with the tool

### 2. Clone marketplace repo

```python
import subprocess, os, shutil

clone_dir = os.path.join(os.environ.get('TEMP', '/tmp'), 'marketplace-clone')
if os.path.exists(clone_dir):
    for root, dirs, files in os.walk(clone_dir):
        for f in files:
            try: os.chmod(os.path.join(root, f), 0o777)
            except: pass
    shutil.rmtree(clone_dir, ignore_errors=True)

subprocess.run(['gh', 'repo', 'clone', 'trend-ai-taskforce/ai-skill-marketplace', clone_dir, '--', '--depth', '1'])
```

### 3. Create plugin files

Create `plugins/<name>/.claude-plugin/plugin.json`:

```json
{
  "name": "plugin-name",
  "version": "1.0.0",
  "description": "What it does",
  "author": { "name": "Author Name" },
  "repository": "https://github.com/owner/repo",
  "license": "MIT",
  "keywords": ["keyword1", "keyword2"]
}
```

Create `plugins/<name>/skills/<name>/SKILL.md` with YAML frontmatter.

### 4. CRITICAL: Normalize line endings to LF

**Windows writes CRLF by default. The marketplace repo uses LF exclusively.**
All plugin files MUST be converted to LF before committing:

```python
for filepath in all_plugin_files:
    with open(filepath, 'rb') as f:
        content = f.read()
    with open(filepath, 'wb') as f:
        f.write(content.replace(b'\r\n', b'\n'))
```

Files to normalize:
- `plugins/<name>/.claude-plugin/plugin.json`
- `plugins/<name>/skills/<name>/SKILL.md`
- Any other text files in the plugin

### 5. Register in marketplace.json

**Do NOT rewrite the entire file.** Read with `newline=''` to preserve existing LF endings:

```python
import json

mkt_path = os.path.join(clone_dir, '.claude-plugin', 'marketplace.json')
with open(mkt_path, 'r', encoding='utf-8', newline='') as f:
    data = json.load(f)

# Remove existing entry if updating
data['plugins'] = [p for p in data['plugins'] if p['name'] != plugin_name]

# Add entry -- tags MUST match plugin.json keywords exactly
data['plugins'].append({
    'name': plugin_name,
    'source': f'./plugins/{plugin_name}',
    'category': category,
    'description': description,
    'version': version,
    'author': {'name': author},
    'tags': keywords  # MUST match plugin.json keywords list
})

# Write with LF line endings
out = json.dumps(data, indent=2, ensure_ascii=False) + '\n'
with open(mkt_path, 'w', encoding='utf-8', newline='\n') as f:
    f.write(out)
```

### 6. Verify diff is minimal

Before committing, check `git diff --stat` on marketplace.json.
It should only show lines added for the new entry (typically 15-25 lines).
If it shows hundreds of changes, line endings were corrupted -- fix step 5.

### 7. Create branch and PR

```bash
git checkout -b plugin/<name>
git add plugins/<name> .claude-plugin/marketplace.json
git -c core.hooksPath=/dev/null commit -m "feat(plugin): add <name> -- <description>"
git push -u origin plugin/<name>
gh pr create --repo trend-ai-taskforce/ai-skill-marketplace \
  --head plugin/<name> --base main \
  --title "feat(plugin): add <name> -- <short-desc>" \
  --body "..."
```

### 8. Review and fix PR comments automatically

After creating PR, wait 30 seconds then check for automated review comments:

```bash
# Get review comments
gh api repos/trend-ai-taskforce/ai-skill-marketplace/pulls/<PR_NUM>/comments

# Get review body
gh api repos/trend-ai-taskforce/ai-skill-marketplace/pulls/<PR_NUM>/reviews
```

**Common Copilot review issues and auto-fixes:**

| Issue | Fix |
|-------|-----|
| CRLF line endings | Convert all files to LF (step 4) |
| Tags don't match keywords | Sync tags in marketplace.json with plugin.json keywords |
| Missing YAML frontmatter | Ensure SKILL.md starts with `---` (LF, not `---\r`) |
| Noisy marketplace.json diff | Re-read original with `newline=''`, only append entry |

After fixing, amend commit and force push:

```bash
git add -A
git commit --amend -m "original message"
git fetch origin
git push --force origin plugin/<name>
```

### 9. Report result

Print PR URL and review status. If `mergeable_state` is `blocked`, it needs maintainer approval.

## Pre-Publish Sanitization (MANDATORY)

Before committing to any public/shared repo, scan ALL files for personal/machine-specific content.
This step is NON-NEGOTIABLE -- skip it and the plugin breaks on every other machine.

### Scan command

```bash
grep -rn "/home/claude\|/home/claude\|OneDrive - TrendMicro\|joel-ginsberg\|joeltest\|${USER_NAME}" <dir> \
  --include="*.py" --include="*.js" --include="*.json" --include="*.md" \
  --include="*.sh" --include="*.yaml" --include="*.yml"
```

### What to fix

| Pattern | Replace with |
|---------|-------------|
| Hardcoded home paths (`/home/claude/...`) | `os.path.join(os.homedir(), ...)` or `$HOME/...` |
| Org-specific paths (`OneDrive - OrgName/...`) | Dynamic discovery via `glob` patterns |
| Personal GitHub usernames | `grobomo` or generic placeholder |
| Personal namespaces, account IDs | Generic placeholders (`my-namespace`, `my-account`) |
| Personal IPs or hostnames | `<your-ip>` placeholders |

### Registry files must be empty templates

Files like `hook-registry.json` and `skill-registry.json` are populated at runtime by setup.js.
Never ship pre-populated registries:
```json
{"hooks": [], "version": "1.0"}
```

### Secret scan

```bash
grep -rn "TOKEN=\|KEY=\|SECRET=\|PASSWORD=" <dir> \
  --include="*.py" --include="*.js" --include="*.json" --include="*.env"
```

If the scan finds ANY hits, fix them before proceeding. Do not commit with personal paths.

---

## Validation Checklist (run before commit)

- [ ] **Sanitization scan passed** (no personal paths, no secrets)
- [ ] plugin.json has: name, version, description, author, repository, license, keywords
- [ ] SKILL.md has valid YAML frontmatter (starts with `---\n` not `---\r\n`)
- [ ] All text files use LF line endings (no `\r\n`)
- [ ] marketplace.json tags match plugin.json keywords exactly
- [ ] marketplace.json diff is minimal (only new entry added)
- [ ] Category is valid: development|documentation|testing|security|productivity|code-analysis|sdlc|ai-agents

## Updating an Existing Plugin

Same flow but:
1. Remove old entry from marketplace.json plugins array first
2. Update version in plugin.json
3. PR title: `feat(plugin): update <name> to v<version>`
