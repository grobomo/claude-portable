---


name: wiki-api
description: Confluence wiki operations - search, read, create, update pages. Use when user asks to interact with Confluence wiki.
keywords:
  - wiki
  - confluence
  - page
  - documentation
  - available
  - operations
  - pages
  - python
  - queryapi
  - spacemyspace
  - child
  - read

---

# Wiki API Skill

Lightweight Confluence API skill for wiki operations.

## Setup

```bash
python .claude/skills/wiki-api/setup.py
```

You'll need:
- Confluence URL (e.g., `https://your-domain.atlassian.net/wiki`)
- Username (email)
- API token from https://id.atlassian.com/manage/api-tokens

## Usage

```bash
# List available operations
python .claude/skills/wiki-api/executor.py --list

# Search pages
python .claude/skills/wiki-api/executor.py search query="API documentation"
python .claude/skills/wiki-api/executor.py search query="API" space=MYSPACE limit=5

# Read a page
python .claude/skills/wiki-api/executor.py read page_id=1234567
python .claude/skills/wiki-api/executor.py read page_id=1234567 format=html

# Get child pages
python .claude/skills/wiki-api/executor.py children page_id=1234567

# Create page
python .claude/skills/wiki-api/executor.py create space_key=~username title="My Page" content="<p>Hello</p>"
python .claude/skills/wiki-api/executor.py create space_key=MYSPACE title="New Page" content="<p>Content</p>" parent_id=1234567

# Update page
python .claude/skills/wiki-api/executor.py update page_id=1234567 title="Updated Title" content="<p>New content</p>"

# Delete page
python .claude/skills/wiki-api/executor.py delete page_id=1234567

# Comments
python .claude/skills/wiki-api/executor.py comments page_id=1234567
python .claude/skills/wiki-api/executor.py comments page_id=1234567 add="Great page!"

# Labels
python .claude/skills/wiki-api/executor.py labels page_id=1234567
python .claude/skills/wiki-api/executor.py labels page_id=1234567 add="documentation"
```

## Operations

| Operation | Description |
|-----------|-------------|
| `search` | Search pages by text or CQL |
| `read` | Read page content (text/html/json) |
| `children` | List child pages |
| `create` | Create new page |
| `update` | Update existing page |
| `delete` | Delete page |
| `comments` | Get or add comments |
| `labels` | Get or add labels |

## Tips

- **Page IDs:** Found in URL after `/pages/` (e.g., `.../pages/1234567/Title`)
- **Personal spaces:** Use `~userid` format (e.g., `~622a1696db58c100687da202`)
- **CQL search:** Use `type=page AND space=KEY AND text ~ "query"` format
- **HTML content:** Use Confluence storage format (XHTML-like)
