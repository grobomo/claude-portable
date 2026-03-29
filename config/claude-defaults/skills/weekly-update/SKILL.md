---

name: Weekly Update
description: Generate weekly status update for GM-SPG-Squad 1 Teams chat. Answers 3 questions from THIS WEEK's data only. Sources are meeting transcripts, emails (sent + inbox + case updates), and Teams chats.
keywords:
  - weekly
  - update
  - status
  - squad
  - accomplishments
  - demos
  - povs
  - plan
  - next week

---

# Weekly Update Skill

Generate the weekly status update posted to **Teams chat "GM-SPG-Squad 1"**.

## Format: 3 Questions

1. What have you accomplished this week?
2. What's the plan for next week?
3. What demos were delivered and what PoVs are in progress or closing? What's the status and next steps? Is MS Dynamics up to date? **Include an active projects table: Customer | Project | Status | Next Step.** This tracks all ongoing work with action items.

## CRITICAL: This Week Only

Only include activities from the current Monday-Friday. Do NOT include historical context, background, or status of all customers. Focus narrowly on what was DONE, SENT, DISCUSSED, or DELIVERED this week.

## Data Sources (all filtered to THIS WEEK)

### 1. Meeting Transcripts (this week's recordings only)
```bash
# Find this week's recordings by date in filename
ls reports/*--2026-MM-DD--*.md  # where DD is this week Mon-Fri
```

### 2. Sent Emails (this week only)
```python
import sys
sys.path.insert(0, '/workspace/msgraph-lib')
from token_manager import graph_get

# Sent items this week (skip calendar accepts/declines)
data = graph_get('/me/mailFolders/sentitems/messages', params={
    '$top': '50',
    '$select': 'subject,toRecipients,sentDateTime,bodyPreview',
    '$orderby': 'sentDateTime desc',
    '$filter': "sentDateTime ge 2026-MM-DDT00:00:00Z"  # Monday of this week
})
```

### 3. Case Updates Folder (this week only)
```python
# Get folder ID
folders = graph_get('/me/mailFolders', params={'$top': '50'})
fid = next(f['id'] for f in folders['value'] if 'case' in f['displayName'].lower())

data = graph_get(f'/me/mailFolders/{fid}/messages', params={
    '$top': '50',
    '$select': 'subject,from,receivedDateTime,bodyPreview',
    '$orderby': 'receivedDateTime desc',
    '$filter': "receivedDateTime ge 2026-MM-DDT00:00:00Z"
})
```

### 4. Teams Chats (all chats, this week's messages)
```bash
# List chats
python "/workspace/teams-chat/teams_chat.py" list

# Read specific chat
python "/workspace/teams-chat/teams_chat.py" read "<full_chat_id>"
```

### 5. Outlook Calendar (next 2 weeks)
```python
from token_manager import graph_get
data = graph_get('/me/calendarView', params={
    '$top': '50',
    '$select': 'subject,start,end,organizer,attendees',
    '$orderby': 'start/dateTime',
    'startDateTime': '2026-MM-DDT00:00:00Z',  # Monday of next week
    'endDateTime': '2026-MM-DDT23:59:59Z'       # Friday 2 weeks out
})
```
Use calendar to populate Q2 (plan for next week) with actual scheduled meetings, not guesses.

### 6. Trello Boards (via trello-lite MCP)
Two board types:
- **GM2S1 Accounts** (`NDsDCBOz`) — high-level account plans, one list per customer. Cards = POCs, projects, key notes.
- **Per-customer boards** (Company3, Dole, EP, etc.) — detailed task tracking with To Do / Doing / Done lists.

```
# List boards
trello_boards

# High-level account plans
trello_lists board_id="NDsDCBOz"
trello_cards list_or_board_id="<list_id>"

# Per-customer task status
trello_lists board_id="<board_short_id>"
trello_cards list_or_board_id="<done_list_id>"  # what's been completed
trello_cards list_or_board_id="<doing_list_id>"  # what's in progress
```

Check Trello Done lists to avoid reporting completed items as pending. Check Doing lists for accurate status. Update Trello after generating the weekly update with any new items from meetings/emails.

### 7. Handwritten Notes & Projects
Two key locations with ad-hoc notes, TODOs, and FR tracking:

```
# Active projects and FRs (priority: TODO file first, then FRs)
/home/claude\OneDrive - TrendMicro\Documents\_Deployments\Projects\2026\

# Per-customer notes (search by recent modification, some folders stale)
/home/claude\OneDrive - TrendMicro\Documents\_Companies\
```

Scan for recently modified files (last 7 days) across both directories. The TODO file in Projects/2026 is most important. FR files are second priority. Not all _Companies folders are active — filter by modification date.

```bash
# Find recently modified notes
find "/home/claude/OneDrive - TrendMicro/Documents/_Deployments/Projects/2026" -mtime -7 -type f
find "/home/claude/OneDrive - TrendMicro/Documents/_Companies" -maxdepth 2 -mtime -7 -type f
```

### 8. Customer Notes (generated from transcript analysis)
```
~/OneDrive - TrendMicro/Documents/_Companies/<Customer>/notes.txt
~/OneDrive - TrendMicro/Documents/_Companies/squad-todo.txt
```

## How to Generate

### Phase 1: Gather ALL data first (do NOT start writing yet)

1. **Calculate this week's date range** (Monday to today)
2. **Scan ALL sources**, filtered to this week:
   - This week's meeting transcript reports
   - Sent emails (skip calendar accepts/declines)
   - Inbox case updates folder
   - Teams chats (all relevant chats, not just squad)
   - Calendar — next 2 weeks of scheduled meetings
3. **Build a complete picture** — for each customer, compile everything that happened: meetings, emails sent, emails received, cases opened/updated/closed, chats, demos given, action items committed to, follow-ups scheduled on calendar.

### Phase 2: Analyze the complete picture

4. **Cross-reference sources** — a meeting report may mention an action item that shows up as a sent email later that week. A case update may relate to something discussed in a meeting. Connect the dots.
5. **Check calendar for next week** — what's actually scheduled vs what was promised in meetings. If a meeting was promised but not yet scheduled, flag it.
6. **Identify what was actually delivered** vs what was just discussed. The report should reflect DONE things, not plans.

### Phase 3: Write the update from the complete picture

7. **Answer all 3 questions** using the full analysis. Each answer should be informed by ALL sources, not just one.
8. **Write to** `reports/weekly-update--YYYY-MM-DD.md`
9. **Open in Notepad++** for review

### Phase 1.5: Write intermediate data files

Before writing the report, write per-customer data files to `reports/weekly-data/YYYY-MM-DD/`:
- One file per customer (ep.md, dole.md, company3.md, etc.)
- Plus calendar.md, internal.md, sources.md
- Each file has: Meetings, Emails Sent, Cases, Key Facts, Action Items, Corrections Applied
- These are the **raw verified data**. The report is the **authored summary** the user owns.
- When the user edits the report, update the intermediate file + trace root cause — don't rebuild everything.

### Phase 1.75: Verify before writing

- **Use trend-docs skill** to look up any Trend product term you're not 100% certain about
- **Read full email bodies** (not just bodyPreview) for key customer threads — especially where the action or context matters
- **Include all-day calendar events** — fetch them, filter for relevance (travel/hackathons/OOO = relevant, company-wide FYI = noise)
- **Use conservative verbs** when unsure — "discussed" not "created", "working on" not "delivered"

### Rules for writing
- Never state a problem without a solution. If there's no solution, mark it as a blocker.
- Don't include action items that belong to other people unless you're driving them.
- If something was promised in a meeting AND completed (visible in sent email or case update), say it was done — don't list it as a future action.
- Check the transcript reports for what was actually said and committed to — don't hallucinate or assume.
- **NEVER fabricate commitments from other people.** Don't say "Chrissa will cover" or "Andre confirmed" unless you have evidence (email, chat message, meeting transcript) that they actually said that.
- **Every claim must be traceable to a source.** If you can't point to a transcript line, email, or chat message that proves it, don't write it.

## Style Rules (learned from user edits)

- **Q1: Max 2 sentences per customer.** Lead with what was accomplished, not meeting-by-meeting recaps.
- **Q1: Omit customers with only minor email activity.** If no meeting, no case escalation, and no significant deliverable — leave them out.
- **Q2: Lead with key action items as bullets**, then daily calendar breakdown. Include all-day events (hackathons, travel) on affected days.
- **Q3: Use a table format** — Customer | Project | Next Step. Not paragraphs.
- **Don't over-detail.** One sentence for minor-activity customers (DISA, CVS). Reserve paragraphs for accounts with meetings + cases + email threads (EP, Dole).

## Tone

- Concise bullet points, not paragraphs
- Customer name in bold at start of each bullet
- Include case numbers (TM-XXXXXXXX) where relevant
- Don't pad with background context — manager reads this weekly, they know the accounts

## Squad Info

- **Vertical:** General Markets 2
- **TA:** Joel Ginsberg
- **SE:** Chrissa Constantine (new ~2 weeks as of 3/26)
- **AE:** Justin Hook (new ~1 week as of 3/26)
- **Previous SE:** Scarlett Menendez (still at Trend, resource), Andre Fernandes
- **Previous AE:** Mitchell Walker (SAL-NA)

## Auth

Email + Calendar: `msgraph-lib/token_manager.py` (delegated auth, public client)
Teams Chat: same token manager
If token expired: `python /workspace/msgraph-lib/token_manager.py`
