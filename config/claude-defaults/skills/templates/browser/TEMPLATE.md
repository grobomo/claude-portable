---
name: {{SKILL_NAME}}
description: {{DESCRIPTION}}
---

# {{SKILL_NAME}}

{{DESCRIPTION}}

## Usage

User says: "/{{SKILL_NAME}}" or relevant trigger phrases.

## Workflow

### Step 1: Start the server in background

```bash
cd "<project_root>" && python .{{SKILL_NAME}}/server.py "$(pwd)" &
# Run with: run_in_background: true
```

### Step 2: Generate HTML

```bash
python .{{SKILL_NAME}}/generate.py [args]
```

### Step 3: Open in browser

```bash
start "" "chrome" "<full_path>\.{{SKILL_NAME}}\index.html"
```

## Files

- `server.py` - Local HTTP server for file operations
- `generate.py` - Generates the HTML UI
- `index.html` - Main UI (generated)
