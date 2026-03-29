# wiki-api

Claude Code skill for Atlassian Confluence Wiki API.

## Features

- **133 API operations** for wiki management
- YAML-driven configuration per operation
- CRUD operations for pages, spaces, users
- Search and content management

## Installation

```bash
cd .claude/skills/wiki-api
python setup.py
```

## Usage

```python
from executor import execute

# Search for pages
result = execute('search', {'cql': 'title~"test"'})

# Create a page
result = execute('create', {
    'space_key': '~username',
    'title': 'New Page',
    'body': '<p>Hello world</p>'
})

# Read a page
result = execute('read', {'page_id': '123456'})

# Update a page
result = execute('update', {'page_id': '123456', 'body': '<p>Updated</p>'})
```

## API Categories

- **Content** - Pages, blog posts, attachments
- **Spaces** - Space management, permissions
- **Users** - User lookup, group membership
- **Labels** - Content labeling and search
- **Templates** - Page templates

## Configuration

Create `.env` with your Confluence credentials:

```
CONFLUENCE_URL=https://your-domain.atlassian.net
CONFLUENCE_EMAIL=your-email@example.com
CONFLUENCE_API_TOKEN=your-api-token
```

## Repository

https://github.com/${TMEMU_ACCOUNT}/skill-wiki-api

## License

Private - internal use only.
