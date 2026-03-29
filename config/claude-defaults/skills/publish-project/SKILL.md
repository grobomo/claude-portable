---


description: |
  Generate project documentation (5-layer standard) and publish to GitHub + skill marketplace.
  Triggers: publish project, ship it, create docs, generate docs, push to github, create readme,
  publish init, publish sync, publish status.
keywords:
  - publish
  - docs
  - documentation
  - readme
  - diagram
  - explainer
  - architecture
  - github
  - repo
  - skip
  - ship
  - missing
  - layers
  - existing
  - init
  - status
  - wiki


---

# Publish Project

Generate 5-layer documentation and publish projects to GitHub + skill marketplace.

## Commands

### `/publish init`
First-time project setup (safe to re-run):
1. Create GitHub repo if not exists: `gh repo create <name> --public --source=. --push` (skip if remote already set)
2. Generate all 5 documentation layers (see below) -- updates existing files in place
3. Commit + push (skip if working tree is clean)

### `/publish sync`
Update and ship (idempotent -- safe to re-run):
1. Regenerate/update docs (gap analysis -- fill missing layers, update existing)
2. Commit changes (skip if working tree is clean)
3. Push to GitHub (skip if up to date with remote)
4. Publish to skill marketplace -- create or update (via marketplace-manager skill)

### `/publish wiki`
Optional: deploy to Confluence wiki:
1. Convert README.md to Confluence storage format (XHTML)
2. Create or update wiki page via **wiki-api skill**
3. Store page_id in `wiki-pages/` frontmatter for future updates

### `/publish status`
Show what exists and what's missing:
- Git remote status
- Documentation layer checklist (which of the 5 exist)
- Marketplace plugin status
- Wiki page status (if wiki-pages/ exists)

---

## Documentation Standard: 5 Layers at 3 Depth Levels

### HIGH LEVEL -- For Humans

#### 1. README.md (Text)
- **Audience:** Human developers, users, stakeholders
- **Purpose:** What this is, why it exists, how to use it
- **Tone:** Concise, no jargon, assumes no prior context

**Required sections:**

| Section | What to cover |
|---------|--------------|
| One-liner | What is this in one sentence |
| The Problem | What pain point does this solve |
| How It Works | High-level flow, not code details |
| Install | Copy-paste commands to get running |
| Configuration | What files/settings exist and what they control |
| Usage | Common commands / operations with examples |
| Why Use It | 3-4 key benefits over alternatives |
| Project Structure | Annotated file tree |

#### 2. Explainer HTML (Visual README)
- **Location:** `docs/project-name-explainer.html`
- **Purpose:** Visual representation of README concepts in interactive browser format
- **Reference:** `ProjectsCL/MCP/mcp-manager/docs/mcpm-explainer.html`

**Required panels (map to README sections):**

| Panel | Visual format |
|-------|---------------|
| THE PROBLEM | Split-screen before/after with red X vs green checkmarks |
| HOW IT WORKS | Flow diagram with labeled arrows |
| FILES / CONFIG | Cards for each config file with role + snippet |
| WHY USE IT | 4 benefit cards with ASCII icons |
| COMMANDS | Grid of key commands with descriptions |

**CSS style (replicate exactly):**
```css
body { background: #0d1117; color: #e6edf3; font-family: 'Segoe UI', system-ui; }
.panel { background: #161b22; border: 1px solid #30363d; border-radius: 12px; }
.panel-title { color: #58a6ff; }
.box.claude { border-color: #da7756; background: #1a1208; }
.box.core { border-color: #58a6ff; background: #0d1926; }
.box.backend { border-color: #3fb950; background: #0d1a12; }
.box.http { border-color: #d29922; background: #1a1508; }
.box.config { border-color: #8957e5; background: #170e26; }
.side.before { background: #1c1008; border-color: #6e3a00; }
.side.after { background: #0d1a12; border-color: #238636; }
code { background: #21262d; }
```

**Rules:** ASCII icons only (no emojis), self-contained single HTML file, works offline.

---

### MID LEVEL -- For Humans and Claudes

#### 3. Architecture Diagrams (webp via gemini-image-gen)
- **Location:** `docs/mid-level/`
- **Generate with:** gemini-image-gen skill
- **Format:** webp, 16:9, quality 95
- **Naming:** Descriptive: `project-concept.webp` (NEVER `slide-01.webp`)

**Required set (3 min, 5 recommended):**

| Diagram | Shows |
|---------|-------|
| Problem/Solution | Before vs after split-screen |
| Routing/Flow | Request path through the system |
| Config/Files | What each config does, how they relate |
| State Machine | States and transitions |
| Boot Sequence | Startup flow with numbered steps |

**Visual style:**

| Element | Style |
|---------|-------|
| Background | Dark (#0d1117) |
| Boxes | Rounded rectangles, colored 2px borders, dark tinted fills |
| Colors | Orange=external, Blue=core, Green=backends, Amber=HTTP, Purple=config |
| Arrows | Clear labels on EVERY arrow |
| Content | Show REAL values (actual names, actual config snippets) |

---

### LOW LEVEL -- For Claude Agents

#### 4. CLAUDE.md (Technical Text)
- **Audience:** Claude Code agents editing this codebase
- **Purpose:** Everything a fresh Claude needs to start coding

**Required sections:**

| Section | What to cover |
|---------|--------------|
| What this is | One sentence |
| Architecture | How components connect |
| Key files | file:purpose table |
| Data flow | Where data lives, how it moves |
| Extension points | How to add features |
| Gotchas | Invariants, non-obvious coupling |
| Build and test | Commands to build, test, deploy |

#### 5. Code Diagrams (webp via gemini-image-gen)
- **Location:** `docs/low-level/`
- **Prefix:** `code-` to distinguish from architecture diagrams

**Required set:**

| Diagram | Shows |
|---------|-------|
| Startup sequence | Init flow, module load order |
| Request handling | Code path for main operation |
| State management | Memory vs disk vs external |
| Module dependencies | Import graph, impact analysis |
| Error handling | Error propagation, retry logic |

---

## Folder Structure

```
project/
+-- README.md                        # HIGH - text
+-- CLAUDE.md                        # LOW - text
+-- docs/
    +-- project-explainer.html       # HIGH - visual
    +-- project-why.webp             # HIGH - problem/solution
    +-- mid-level/                   # MID - architecture
    |   +-- project-routing.webp
    |   +-- project-config.webp
    |   +-- project-lifecycle.webp
    +-- low-level/                   # LOW - code internals
        +-- code-call-path.webp
        +-- code-memory.webp
```

## Execution Order

Generate docs in this order (cheap text first, expensive visuals last).
**After each step that creates or updates a file, reopen it for review** (Notepad++ for text, browser for HTML).

1. **README.md** -- write or update (always) -> open in Notepad++
2. **CLAUDE.md** -- write or update (always for code projects, skip for doc-only/skills) -> open in Notepad++
3. **Explainer HTML** -- generate from README concepts -> open in browser
4. **Architecture diagrams** -- invoke gemini-image-gen skill (code projects only) -> open output dir
5. **Code diagrams** -- invoke gemini-image-gen skill (multi-file code projects only) -> open output dir
6. **Commit + push** to GitHub
7. **Marketplace** -- invoke marketplace-manager skill via Skill tool (only if project has SKILL.md or plugin.json -- standalone tools without either skip this)
8. **Wiki** (if requested) -- invoke wiki-api skill via Skill tool

**WHY reopen after each edit:** The user needs to see the latest version of each file as changes are made. Opening files only once at the end means the user reviews stale content if any edits happened mid-workflow.

## Scoping: Skip What Doesn't Apply

Not every project needs all 5 layers. Match depth to complexity:

| Project type | Layers to generate |
|-------------|-------------------|
| Skill (SKILL.md only, no code) | README only. CLAUDE.md = SKILL.md itself |
| Single-script tool (1-2 files) | README + CLAUDE.md + explainer. 1-2 mid-level diagrams. Skip low-level |
| Multi-file project (3+ files) | All 5 layers. 3-5 mid-level + 3-5 low-level diagrams |
| Large system (10+ files) | All 5 layers. 5+ diagrams per level. Subfolders in low-level/ |

## Staleness Check (run BEFORE gap analysis)

Docs can become stale when code changes after docs were generated. Detect this automatically using **per-folder hashing** to identify exactly what changed.

### How it works

1. **On doc generation**: Compute SHA256 hash of each top-level folder separately + root files
2. **Store hashes**: Write to `docs/.code-hash` as YAML
3. **On next /publish**: Recompute hashes, compare per-folder
4. **Changed folders**: Regenerate docs that describe those areas
5. **Any change at all**: ALWAYS regenerate high-level docs (README, explainer) since they summarize the whole project
6. **If no .code-hash exists**: Treat as fully stale (first publish or hash file deleted)

### What to hash

Hash ALL files that influence documentation content:
- `*.py`, `*.js`, `*.ts`, `*.json` (source code)
- `*.yaml`, `*.yml` (config files)
- `SKILL.md`, `CLAUDE.md` (project docs that feed into README)
- Exclude: `docs/`, `*.webp`, `*.png`, `*.jpg`, `node_modules/`, `__pycache__/`, `.git/`, `state/`, `logs/`, `archive/`, `backups/`, `config/repos/`, `.pytest_cache/`

### docs/.code-hash format

```yaml
generated: 2026-02-23T12:00:00Z
project_hash: a1b2c3d4...        # Combined hash of ALL folders (quick equality check)
folders:
  managers/:     e5f6a7b8...      # Hash of managers/*.py, managers/*.js, etc.
  commands/:     c9d0e1f2...
  hooks/:        a3b4c5d6...
  hooks-src/:    d7e8f9a0...
  shared/:       b1c2d3e4...
  credentials/:  f5a6b7c8...
  registries/:   d9e0f1a2...
  mcp/:          b3c4d5e6...
  skills/:       a7b8c9d0...
  config/:       e1f2a3b4...
  tests/:        c5d6e7f8...
  root:          f9a0b1c2...      # Files in project root (super_manager.py, setup.js, etc.)
file_count: 47
```

### Implementation

```bash
# Per-folder hash (run from project root):
# For each top-level directory:
find ./managers -type f \( -name "*.py" -o -name "*.js" -o -name "*.ts" -o -name "*.json" -o -name "*.yaml" -o -name "*.yml" -o -name "*.md" \) \
  -exec sha256sum {} \; | sort | sha256sum | cut -d' ' -f1

# For root files only (not recursing into subdirs):
find . -maxdepth 1 -type f \( -name "*.py" -o -name "*.js" -o -name "*.ts" -o -name "*.json" -o -name "*.yaml" -o -name "*.yml" -o -name "*.md" \) \
  -exec sha256sum {} \; | sort | sha256sum | cut -d' ' -f1

# Combined project hash (hash of all folder hashes, sorted):
echo "<all folder hashes sorted>" | sha256sum | cut -d' ' -f1
```

### Staleness decision tree

```
/publish invoked
  |
  v
Does docs/.code-hash exist?
  NO  -> FULLY STALE: regenerate ALL docs
  YES -> compute current per-folder hashes
           |
           v
         project_hash matches?
           YES -> CURRENT: gap analysis only (fill missing layers)
           NO  -> compare per-folder hashes
                    |
                    v
                  Which folders changed?
                    |
                    +-> ALWAYS regenerate: README.md, explainer HTML
                    |   (high-level docs summarize entire project)
                    |
                    +-> Changed folder = managers/ ?
                    |     -> Regenerate CLAUDE.md sections about sub-managers
                    |     -> Regenerate mid-level architecture diagram
                    |     -> Regenerate low-level code diagrams for managers
                    |
                    +-> Changed folder = hooks-src/ or hooks/ ?
                    |     -> Regenerate hook pipeline diagram
                    |     -> Update CLAUDE.md hook sections
                    |
                    +-> Changed folder = commands/ ?
                    |     -> Regenerate CLI command docs in README
                    |     -> Update CLAUDE.md command reference
                    |
                    +-> Changed folder = config/ ?
                    |     -> Regenerate config sync diagram
                    |     -> Update config import/export docs
                    |
                    +-> Changed folder = shared/ ?
                    |     -> Update CLAUDE.md utilities section
                    |
                    +-> Changed folder = credentials/ ?
                    |     -> Update credential manager docs
                    |
                    +-> Changed folder = root ?
                          -> Check if setup.js/rollback.js/super_manager.py changed
                          -> Update install/CLI docs accordingly
```

### Folder-to-doc mapping

The staleness checker uses this mapping to decide WHICH docs to regenerate. Projects should customize this in their `.code-hash` or use a sensible default based on folder names.

| Changed folder | Docs to regenerate |
|----------------|-------------------|
| ANY folder | README.md + explainer HTML (always -- they summarize everything) |
| `managers/` | CLAUDE.md (sub-manager sections), mid-level architecture diagram, low-level code diagrams |
| `hooks-src/` or `hooks/` | CLAUDE.md (hook pipeline), hook pipeline diagram |
| `commands/` | CLAUDE.md (CLI reference), README usage section |
| `config/` | Config sync diagram, README config import/export section |
| `shared/` | CLAUDE.md (utilities section) |
| `credentials/` | CLAUDE.md (credential section), README credential docs |
| `registries/` | CLAUDE.md (registry section) |
| `root` (*.py, *.js at top level) | CLAUDE.md (architecture), README install section |

**WHY per-folder**: A single project-wide hash forces regenerating ALL docs when one file changes. Per-folder hashing identifies that only `managers/` changed, so only manager-related docs need updating. High-level docs (README, explainer) always regenerate because they summarize the whole project -- any change could affect the summary.

**WHY always regenerate high-level docs**: README and explainer are summaries. Even a small change in one folder can make the summary inaccurate. It's cheap to regenerate text, expensive to debug misleading docs.

## Gap Analysis (run at START and END of /publish)

1. **Identify concepts:** WHY, WHAT, HOW, CONFIG, LIFECYCLE, EXTEND, GOTCHAS
2. **Map to layers:** Each concept needs text + visual coverage
3. **Check:** Every concept in at least 2 layers (text + visual)
4. **Fill:** Generate missing docs/diagrams, prioritize zero-coverage first

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

## Publishing Steps

After docs are generated (all steps are idempotent):

**MANDATORY: Open files for user review BEFORE committing AND after each edit.**
Use the open-notepad skill (or `start` on Windows) to open ALL generated/updated files:
- Text files (README.md, CLAUDE.md) in Notepad++
- HTML files (explainer) in default browser via `start "" "path/to/file.html"`
- Published URLs (GitHub repo, wiki page) via `start "" "https://..."`
Re-open any file that was edited during the workflow so the user always sees the latest version.
Do NOT proceed to git commit until files have been opened for review.

1. **Open for review** -- open ALL generated/updated files for user to review (see above)
2. `git add` relevant doc files + `git commit` (skip if working tree is clean)
3. `git push origin main` (skip if up to date with remote)
4. **Marketplace** (only if project has SKILL.md or plugin.json -- standalone tools skip this):
   - Check CLAUDE.md visibility field to determine which marketplace:
     - `GitHub: emu` -> invoke **emu-marketplace** skill (trend-ai-taskforce/ai-skill-marketplace)
     - `GitHub: grobomo` -> invoke **marketplace-manager** skill (personal marketplace)
   - Both marketplaces follow the same standards (format, validation, LF line endings)
5. **PR review loop** (after marketplace PR is created):
   - Wait 30 seconds for automated reviewers (Copilot, CI checks)
   - Fetch PR comments via `gh api repos/.../pulls/<N>/comments`
   - Auto-fix all issues (CRLF, missing tags, noisy diffs, validation failures)
   - Amend commit, force push, re-check -- repeat until clean
   - Report final PR URL and merge status
6. (If `/publish wiki`) Invoke **wiki-api** via `Skill tool`:
   - Convert README.md to Confluence storage format (XHTML with ac:structured-macro for code blocks)
   - Create page (first time) or update page (subsequent) via wiki-api executor
   - Save page_id in `wiki-pages/*.md` frontmatter

## One-Click Install Standard

Every published project must have a **one-click install** that handles everything:

### Requirements

1. **Single command** -- `python install.py install` (or equivalent) does deps + config + setup
2. **Zero user interaction** -- no prompts, no manual pip installs, no editing before first run
3. **Fail-fast config** -- if config needs user input (email, API key), copy example + print clear message + exit 1
4. **Auto-detect platform** -- Windows/macOS/Linux deps handled automatically
5. **Idempotent** -- safe to re-run, skips what's already done

### Required Flags

Every install script must support:

| Flag | Behavior |
|------|----------|
| (none) | Interactive: pause for confirmations (UAC, "Press Enter to close") |
| `--headless` | Auto-approve all prompts (UAC/sudo still required by OS) |
| `--headless-safe` | Skip warnings entirely (for CI/scripted/unattended use) |

### Install Script Template

```python
HEADLESS = "--headless" in sys.argv
HEADLESS_SAFE = "--headless-safe" in sys.argv

def install_deps():
    """Auto-detect and install missing pip dependencies."""
    # platform-specific dep list, try import, pip install missing

def ensure_config():
    """Validate config exists with required fields. Fail fast, never prompt."""
    # copy example if missing, check required fields, exit 1 with clear message

def install():
    install_deps()
    ensure_config()
    # platform-specific scheduled task / service setup
    if HEADLESS or HEADLESS_SAFE or not sys.stdin.isatty():
        return
    input("\nPress Enter to close...")
```

## Project Visibility Tracking

Every project must declare its visibility tier in CLAUDE.md (first line after title):

```markdown
> **Visibility:** internal | **GitHub:** emu (${TMEMU_ACCOUNT}) | **Status:** Windows beta, macOS alpha
```

| Field | Values |
|-------|--------|
| Visibility | `internal` (team only) or `public` (open source) |
| GitHub | `emu` (${TMEMU_ACCOUNT}) or `grobomo` (public account) |
| Status | Per-platform maturity: `alpha` (untested), `beta` (tested on 1 machine), `stable` (production) |

This prevents accidentally leaking internal projects to public repos and tracks platform readiness.

## Rules

- README and Explainer cover the SAME concepts at HIGH level
- CLAUDE.md and code diagrams cover the SAME concepts at LOW level
- Architecture diagrams bridge both levels
- Never mix levels: no install instructions in CLAUDE.md, no code internals in README
- All diagrams use descriptive filenames: `project-concept.webp`
- Skip layers that don't apply (see Scoping table above)
- Every project must have one-click install with --headless and --headless-safe flags
