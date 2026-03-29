# Suggested API Calls - Confluence Wiki

*Auto-generated on 2026-01-03 13:50*

## Quick Start

The most common operations based on user research:

### Essential Operations

**Search documentation** - Find pages containing specific keywords or topics
```bash
python executor.py search query="API documentation" limit=10
```
Operations: `search, list_search`

**Read page content** - Get full content of a wiki page for reference or processing
```bash
python executor.py read page_id=1234567 format=text
```
Operations: `read`

**Create new documentation** - Create new wiki pages from templates or generated content
```bash
python executor.py create space_key=MYSPACE title="New Feature" content="<p>...</p>"
```
Operations: `create`

**Update existing pages** - Modify page content, fix errors, add new sections
```bash
python executor.py update page_id=1234567 title="Updated Title" content="<p>New content</p>"
```
Operations: `update`

**Sync docs from GitHub** - Push README/markdown files to Confluence automatically
```bash
python executor.py # Workflow: search for existing -> update or create
```
Operations: `update, create, search`

### Common Operations

**Navigate page hierarchy** - Browse child pages, find parent pages, understand structure
- Operations: `get_content_descendant, list_content_descendant, children`
- Example: `children page_id=1234567`

**Manage page labels** - Add, remove, or list labels for organization and filtering
- Operations: `list_label, delete_content_label, labels`
- Example: `labels page_id=1234567 add="api-docs"`

**Add comments and feedback** - Post comments on pages for collaboration
- Operations: `comments`
- Example: `comments page_id=1234567 add="Reviewed and approved"`

**Manage attachments** - Upload, download, or list file attachments on pages
- Operations: `create_content_child_attachment, list_content_child_attachment_download`
- Example: `# Use create_content_child_attachment to upload files`

### Advanced Operations

- **Archive or delete pages**: `delete, delete_content_page_tree, create_content_archive`
- **Manage spaces**: `delete_space, list_space_settings, create_space`
- **Set permissions**: `list_content_restriction, create_space_permission, create_content_restriction`
- **Export content**: `list_audit_export`
- **Track page analytics**: `list_analytics_content_viewers, list_analytics_content_views`
- **Manage templates**: `get_template, create_template, list_template_page`

## Coverage Analysis

- **Total operations available**: 133
- **Operations mapped to user stories**: 30
- **Coverage**: 22.6%

### Gaps (not yet implemented)

- `get_page`

### Available but Unmapped

Operations available but not linked to common user stories:

- **create** (20 ops): `create_atlassian_connect_1_app_module_dynamic, create_audit, create_content_blueprint_instance`, ...
- **delete** (18 ops): `delete_atlassian_connect_1_app_module_dynamic, delete_content_restriction, delete_content_restriction_by_operation_by_group_id`, ...
- **get** (14 ops): `get_content_history_macro_id, get_content_history_macro_id_convert, get_content_history_macro_id_convert_async`, ...
- **list** (37 ops): `list_atlassian_connect_1_app_module_dynamic, list_audit, list_audit_retention`, ...
- **update** (14 ops): `update_audit_retention, update_content_blueprint_instance, update_content_child_attachment`, ...

## Research Sources

- https://github.com/atlassian/atlassian-mcp-server
- https://github.com/sooperset/mcp-atlassian
- https://atlassian-python-api.readthedocs.io/confluence.html
- https://n8n.io/integrations/confluence/
