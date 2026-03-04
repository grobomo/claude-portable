---
id: mcp-repo-layout
name: MCP Server Repository Layout
keywords: [mcp, repo, clone, github, server, portable, container, sync]
description: "WHY: MCP servers are NOT individual GitHub repos. Most are in a monorepo. Without this, clone scripts break. WHAT: Documents actual repo structure."
enabled: true
priority: 5
action: Use correct MCP repo layout for cloning
min_matches: 2
---

# MCP Server Repository Layout

## WHY

Claude-portable sync scripts repeatedly fail because they assume each MCP server
(mcp-manager, mcp-v1-lite, etc.) is its own GitHub repo. They are NOT. Most live
in a monorepo or have no remote at all.

## Actual Layout

### Local path
```
ProjectsCL/MCP/
  mcp-ansible/        -> joel-ginsberg_tmemu/mcp-dev (monorepo)
  mcp-atlassian-lite/ -> joel-ginsberg_tmemu/mcp-dev (monorepo)
  mcp-blueprint-fork/ -> railsblueprint/blueprint-mcp (separate repo)
  mcp-browser-helper/ -> joel-ginsberg_tmemu/mcp-dev (monorepo)
  mcp-jira-lite/      -> joel-ginsberg_tmemu/mcp-dev (monorepo)
  mcp-manager/        -> NO REMOTE (local only, build/index.js)
  mcp-trello-lite/    -> joel-ginsberg_tmemu/mcp-dev (monorepo)
  mcp-trend-docs/     -> joel-ginsberg_tmemu/mcp-dev (monorepo)
  mcp-trendgpt/       -> joel-ginsberg_tmemu/mcp-dev (monorepo)
  mcp-v1ego/          -> joel-ginsberg_tmemu/mcp-dev (separate repo: mcp-v1ego)
  mcp-v1-lite/        -> joel-ginsberg_tmemu/mcp-dev (monorepo)
  mcp-wiki-lite/      -> joel-ginsberg_tmemu/mcp-dev (monorepo)
```

### Key facts
- **Monorepo:** `joel-ginsberg_tmemu/mcp-dev` contains most servers as top-level dirs
- **mcp-manager:** Has NO git remote. It was built locally. Must be pushed to its own repo or included in mcp-dev before container cloning works.
- **Entry point:** mcp-manager uses `build/index.js` (Node.js, built with `node build.mjs`)
- **Python servers:** mcp-v1-lite, mcp-wiki-lite, mcp-jira-lite, mcp-trello-lite use `server.py`

## For claude-portable container

To get MCP servers into the container, clone `mcp-dev` monorepo and symlink/copy individual server dirs to `/opt/mcp/`. Do NOT try to clone `mcp-manager`, `mcp-v1-lite`, etc. as individual repos -- they don't exist.

## Do NOT
- Do NOT assume each MCP server folder is its own GitHub repo
- Do NOT try `git clone .../mcp-manager.git` -- it has no remote
- Do NOT try `git clone .../mcp-v1-lite.git` -- it's a dir in mcp-dev
