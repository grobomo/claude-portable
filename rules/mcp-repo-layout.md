---
id: mcp-repo-layout
name: MCP Server Repository Layout
keywords: [mcp, repo, clone, github, server, portable, container, sync, monorepo]
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
in a monorepo.

## Monorepo contents (verified 2026-03-04)

`joel-ginsberg_tmemu/mcp-dev` top-level dirs:
- mcp-manager, mcp-v1-lite, mcp-jira-lite, mcp-trend-docs, mcp-trendgpt

**NOT in monorepo** (local only or missing from GitHub):
- mcp-wiki-lite, mcp-trello-lite, mcp-ansible, mcp-atlassian-lite, mcp-browser-helper

## Full Layout

```
ProjectsCL/MCP/
  mcp-manager/        -> joel-ginsberg_tmemu/mcp-dev (monorepo, build/index.js)
  mcp-v1-lite/        -> joel-ginsberg_tmemu/mcp-dev (monorepo)
  mcp-jira-lite/      -> joel-ginsberg_tmemu/mcp-dev (monorepo)
  mcp-trend-docs/     -> joel-ginsberg_tmemu/mcp-dev (monorepo)
  mcp-trendgpt/       -> joel-ginsberg_tmemu/mcp-dev (monorepo)
  mcp-wiki-lite/      -> LOCAL ONLY (not in monorepo)
  mcp-trello-lite/    -> LOCAL ONLY (not in monorepo)
  mcp-ansible/        -> LOCAL ONLY (not in monorepo)
  mcp-atlassian-lite/ -> LOCAL ONLY (not in monorepo)
  mcp-browser-helper/ -> LOCAL ONLY (not in monorepo)
  mcp-blueprint-fork/ -> railsblueprint/blueprint-mcp (separate repo)
  mcp-v1ego/          -> joel-ginsberg_tmemu/mcp-v1ego (separate repo)
```

## Key facts
- **mcp-manager:** In monorepo. Entry: `build/index.js`. Build: `node build.mjs`
- **Python servers:** mcp-v1-lite, mcp-jira-lite use `server.py`
- **For containers:** Clone `mcp-dev` monorepo, copy server dirs to `/opt/mcp/`

## Do NOT
- Do NOT assume each MCP server folder is its own GitHub repo
- Do NOT try `git clone .../mcp-v1-lite.git` -- it's a dir inside mcp-dev
