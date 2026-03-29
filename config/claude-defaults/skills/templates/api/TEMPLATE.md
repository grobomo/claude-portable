# API Skill Template

Template for creating skills that wrap REST APIs with YAML-driven configurations.

## Structure

```
my-api/
├── SKILL.md               # Skill metadata and documentation
├── executor.py            # CLI executor (handles API calls)
├── setup.py               # Interactive credential setup
├── refresh_api.py         # Sync with official API spec (optional)
├── analyze_userstories.py # Generate SUGGESTED_CALLS.md
├── userstories.yaml       # User story definitions
├── SUGGESTED_CALLS.md     # Auto-generated usage guide
├── .gitignore             # Ignore .env and cache files
└── api_index/             # YAML configs per operation
    ├── operation_name/
    │   ├── config.yaml         # API configuration
    │   ├── example_api_call.py # Working example (optional)
    │   └── example_response.json  # Sample response (optional)
    └── _example/
        └── config.yaml         # Template to copy
```

## Workflow (Good UX)

### New Project Setup
```bash
python setup.py
# 1. Enter credentials
# 2. Test connection
# 3. Auto-runs: refresh --apply (fetches API spec)
# 4. Auto-runs: analyze (generates SUGGESTED_CALLS.md)
```

### Refresh API Spec
```bash
python executor.py --refresh                       # Show diff only
python executor.py --refresh --apply               # Create configs + auto-analyze
python executor.py --refresh --apply --no-analyze  # Skip auto-analyze
```

### Analyze User Stories
```bash
python executor.py --analyze                # Full analysis (research + compare)
python executor.py --analyze --skip-research  # Use cached stories only
python executor.py --analyze --quiet        # Minimal output (no research)
```

## Creating a New Skill

1. **Copy template files:**
   ```bash
   cp -r .claude/skills/templates/api-skill .claude/skills/my-api
   ```

2. **Edit SKILL.md:**
   - Update name, description, and frontmatter
   - Document available operations

3. **Edit setup.py:**
   - Update credential prompts
   - Update base URL/region handling
   - Update connection test

4. **Edit executor.py:**
   - Update REGION_URLS or BASE_URL
   - Update get_headers() for auth method
   - Add templates for your API patterns

5. **Create api_index configs:**
   - Copy `_example/config.yaml` for each operation
   - Update endpoint, method, template, params

6. **Run setup:**
   ```bash
   python .claude/skills/my-api/setup.py
   ```

7. **Test:**
   ```bash
   python .claude/skills/my-api/executor.py --list
   python .claude/skills/my-api/executor.py operation_name key=value
   ```

## Templates

Available execution templates in executor.py:

| Template | Method | Use Case |
|----------|--------|----------|
| `get_single` | GET | Fetch single resource by ID |
| `get_list` | GET | Paginated list with filters |
| `get_search` | GET | Search with query param |
| `post_create` | POST | Create resource |
| `post_action` | POST | Trigger action |
| `put_update` | PUT | Full update |
| `patch_update` | PATCH | Partial update |
| `delete` | DELETE | Delete resource |

## config.yaml Format

```yaml
name: operation_name
description: What this operation does
method: GET|POST|PUT|PATCH|DELETE
endpoint: /api/v1/resources/{id}
template: get_single

params:
  required:
    - name: id
      type: string
      description: Resource ID (path param)
  optional:
    - name: limit
      type: integer
      default: 10
      description: Max results

template_config:
  # Template-specific settings
  pagination:
    param: limit
    max: 100
```

## Auth Methods

### Bearer Token (V1, most APIs)
```python
headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json'
}
```

### Basic Auth (Confluence, Jira)
```python
import base64
auth = base64.b64encode(f"{username}:{token}".encode()).decode()
headers = {
    'Authorization': f'Basic {auth}',
    'Content-Type': 'application/json'
}
```

### API Key Header (some APIs)
```python
headers = {
    'X-API-Key': api_key,
    'Content-Type': 'application/json'
}
```
