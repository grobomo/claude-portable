---



name: diff-view
description: Side-by-side diff viewer with editable right side, resizable panels, synced heights, and merge workflow.
keywords:
  - diff
  - compare
  - merge
  - viewer


---

# Side-by-Side Diff Viewer

Interactive diff viewer with:
- Left: Old file with line numbers and change highlighting
- Right: Single editable textarea with line numbers
- Scroll sync between panels
- Live folder navigation and direct file saves (with server)
- Click any file to view in left panel

## Usage

User says: "/diff-view" or "show diff" or "compare files"

Arguments: `<old_file> <new_file>` or just `<file>` (compares to git HEAD)

## Workflow (Claude executes these automatically)

### Step 1: Start the server in background

```bash
cd "<project_root>" && python .diff-viewer/server.py "$(pwd)" &
# Run with: run_in_background: true
```

### Step 2: Wait for token file, then generate HTML

```bash
sleep 1 && python .diff-viewer/generate.py <old_file> <new_file>
```

### Step 3: Open in Chrome

```bash
start "" "chrome" "<full_windows_path>\.diff-viewer\diff_viewer.html"
```

The server provides:
- Live folder navigation (click into any subfolder)
- Single-click file viewing in left panel
- Direct file saves (no download needed)
- Token-based authentication
- Path restricted to project root

## Security Features

The server includes these protections:
- **Token authentication** - Random token generated at startup, required for all requests
- **Path whitelist** - Only allows paths under project root directory
- **Extension whitelist** - Only allows safe file types (.json, .md, .py, .txt, .yaml, etc.)
- **Localhost only** - Binds to 127.0.0.1, not accessible from network
- **Auto-backup** - Creates timestamped backup before any save

## Offline Mode

If server is not running:
- Uses pre-loaded folder data (3 parent levels)
- Save button downloads file with timestamp suffix
- Limited folder navigation

## Key Features

- **Resizable divider**: Drag the gray bar to resize panels
- **Scroll sync**: Left and right panels scroll together
- **Line numbers**: Both panels show line numbers
- **Change highlighting**: Red for removed/changed lines on left
- **Collapsible git panel**: Shows recent commits, double-click to view old version
- **File browser**: Navigate folders, search files, editable path bar
- **Direct save**: With server running, saves directly to disk

## Examples

- `/diff-view .mcp.backup .mcp.json` - Compare backup to current
- `/diff-view README.md` - Show changes to specific file vs git HEAD
- `/diff-view old.txt new.txt` - Compare two files

## Files

- `.diff-viewer/generate.py` - Generates the HTML diff viewer
- `.diff-viewer/server.py` - Local server for live navigation and saves
- `.diff-viewer/diff_viewer.html` - Generated output (gitignored)
- `.diff-viewer/.server_token` - Auth token file (gitignored)
