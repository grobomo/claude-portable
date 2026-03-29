---

name: Weekly Data
description: Auto-polling local cache of work activity — emails, cases, Teams chats, calendar, Trello, meeting transcripts. Always-fresh data you can edit to correct AI interpretations. Powers weekly updates, daily action items, or any summary on demand without re-querying APIs.
keywords:
  - weekly
  - data
  - poll
  - cache
  - emails
  - cases
  - teams
  - calendar
  - trello
  - sources
  - refresh

---

# Weekly Data Skill

Local cache of all your work activity, auto-refreshed every 15 minutes. Ask for a summary anytime — no API calls needed.

## What It Does

1. **Polls** your email, cases, Teams chats, calendar, and Trello every 15 min
2. **Caches** everything as editable markdown files with "My read:" fields
3. **You edit** any interpretation you disagree with — corrections persist
4. **AI reads local files** to generate summaries, weekly updates, action items — instantly

## Commands

```
/weekly-data status     # What's cached, when last polled, what's missing
/weekly-data refresh    # Force immediate poll of all sources
/weekly-data setup      # First-time setup (auto-runs if needed)
```

## First Run

The skill auto-discovers dependencies and configures itself. Just run it — it will:

1. **Find msgraph-lib** — scans parent directories for `msgraph-lib/token_manager.py`
2. **Find teams-chat** — scans for `teams-chat/teams_chat.py`
3. **Test Graph API token** — tries a simple query, tells you if expired
4. **Create data directory** — `<project>/reports/weekly-data/<week>/`
5. **Run first poll** — populates all source files
6. **Schedule 15-min polling** — via claude-scheduler

If something's missing, it tells you exactly what and how to fix it. No guessing.

## Data Structure

```
reports/weekly-data/<YYYY-MM-DD>/
  sources/                    # Raw polled data — auto-refreshed every 15 min
    sent-emails.md            # Each email with "My read:" field
    case-updates.md           # Each case with "My read:" field
    calendar.md               # Events with "Relevant?" field
    teams-<name>.md           # Chat messages with "My takeaways" section
    transcript-reports.md     # Meeting reports indexed
    handwritten-notes.md      # Recently modified note files
    trello.md                 # Board state
  corrections/                # YOU edit these — persist across weeks
    terminology.md            # Product terms to use/avoid
    customers.md              # Customer-specific context
    style.md                  # Report formatting preferences
  <customer>.md               # Synthesized per-customer summaries
```

## How Corrections Work

Every polled item has an editable field:
- **Emails:** `**My read:**` — what this email was actually about
- **Calendar:** `**Relevant?**` — yes/no/context
- **Teams:** `## My takeaways` — what matters from this chat
- **Cases:** `**My read:**` — what's really going on with this case

Edit any of these. Next time AI generates a summary, it uses YOUR interpretation, not its guess.

The `corrections/` folder is for cross-cutting rules:
- `terminology.md` — "FSVA = File Security Virtual Appliance, runs on Service Gateway"
- `customers.md` — "Dole ZTSA request is for banking compliance, not general routing"
- `style.md` — "Max 2 sentences per customer in Q1. Use table format for Q3."

## Dependencies

| Dependency | What it is | How to get it |
|-----------|------------|---------------|
| msgraph-lib | Graph API token manager | Clone from ProjectsCL1, run `python token_manager.py` to auth |
| teams-chat | Teams chat reader | Clone from ProjectsCL1 (uses msgraph-lib) |
| claude-scheduler | 15-min polling | Should already be installed as a skill |
| trello-lite MCP | Trello board reader | Managed by mcp-manager |

## How Claude Uses This Skill

### When the user asks for a summary, weekly update, action items, or "what did I do"

**MANDATORY: Use the assembler script. Do NOT read source files individually.**

```bash
# Full data (corrections + sources + customer files)
node <skill_dir>/assemble.js

# Compact version (counts + user-annotated items only)
node <skill_dir>/assemble.js --summary

# One customer
node <skill_dir>/assemble.js --customer ep

# One source type
node <skill_dir>/assemble.js --section emails
```

The assembler:
1. Reads corrections/ FIRST (terminology, customers, style)
2. Reads sources/ with user edits already applied
3. Reads per-customer .md files
4. Outputs structured JSON with all data pre-merged

**DO NOT query APIs. DO NOT write Python to call Graph API. DO NOT read source files with the Read tool.** Run the assembler. It handles everything.

If source files don't exist, the assembler will tell you. Run setup.

### When the user says "refresh data" or "refresh"

```bash
node <skill_dir>/poll-sources.js              # All sources
node <skill_dir>/poll-sources.js --source emails  # One source
```

The poller **preserves user edits**. If a user filled in "My read:" on an email, refreshing won't erase it. New API data merges around existing annotations.

### When the user says "status" or "weekly-data status"

```bash
node <skill_dir>/setup.js --check
```

### Before generating a new weekly update report

**MANDATORY: Run the diff-tracker first** to capture corrections from the user's previous edits:

```bash
node <skill_dir>/diff-tracker.js
```

This compares the current report against the last generated version, classifies every change (removed customer, modified text, added detail, restructured section), and writes corrections to:
- `corrections/customers.md` — customer-specific corrections
- `corrections/style.md` — format/voice preferences
- Per-customer `.md` files — individual corrections

Then save the newly generated report as the baseline:
```bash
cp reports/weekly-update--YYYY-MM-DD.md <weekDir>/.last-generated-report.md
```

### When the user corrects something you said

1. Run diff-tracker if they edited the report file
2. For verbal corrections, update the source file's "My read:" field
3. Update corrections/ if it's a reusable rule
4. The poller will preserve these edits on next refresh

### When the skill isn't set up yet

```bash
node <skill_dir>/setup.js
```

Full bootstrapper: installs Python packages, clones repos, authenticates, creates directories, runs first poll, schedules 15-min auto-refresh. User just approves browser auth.

## Files

```
weekly-data/
├── SKILL.md          # This file (instructions for Claude)
├── setup.js          # Full bootstrapper — installs deps, configures, first poll
├── poll-sources.js   # Config-driven poller — preserves user edits on refresh
├── assemble.js       # MANDATORY data reader — corrections + sources → JSON
├── diff-tracker.js   # Detects user edits, auto-writes corrections
└── config.json       # Auto-generated by setup — paths to dependencies
```

Config is auto-discovered — no manual path entry needed. If you move projects, re-run setup.
