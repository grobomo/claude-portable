# Claude Code Report

Generated: 2026-03-06 17:52:55


## Summary

| Category | Running | Stopped | Disabled | Unregistered | Total |
|----------|---------|---------|----------|--------------|-------|
| MCP Servers | 0 | 6 | 8 | 33 | 47 |
| Skills | - | 41 | - | 56 | 113 |
| Hooks | 17 | - | 22 | 132 | 171 |

## MCP Servers (47 total)
```
mcp-servers
|   # MCP-MANAGER (router)
|    |-- script: index.js
|    +-- (no routed servers)
|   # STANDALONE STOPPED
|    |-- v1ego - MCP server that controls V1EGO Chrome ex
|    |-- v1-lite - Vision One API wrapper - alerts, endpoin
|    |-- trendgpt - TrendGPT A2A Gateway - Trend Micro produ
|    |-- wiki-lite - Confluence wiki search and sync
|    |-- blueprint - Blueprint MCP with incognito
|    +-- trend-docs - Search and read Trend Micro docs (JS SPA
|   # STANDALONE DISABLED
|    |-- playwriter - Playwriter MCP - full Playwright API via
|    |-- browser - Official Browser MCP via Chrome extensio
|    |-- example-python - Example Python MCP server
|    |-- example-node - Example Node.js MCP server
|    |-- example-remote - Example remote MCP server
|    |-- example-websocket - Example WebSocket MCP server
|    |-- browser-cdp - MCP server for browser automation via Ch
|    +-- browser-local - MCP server for browser automation - loca
|   # STANDALONE UNREGISTERED
|    |-- jira-lite - jira-lite MCP Server

Lightweight read-o
|    |-- trello-lite - trello-lite MCP Server

Lightweight Trel
|    |-- mcp-v1-ego - V1-Ego: Stateful Vision One analysis and
|    |-- mcp-v1-lite - import os
import json
import yaml
from p
|    |-- mcp-bash-helper - Bash Helper MCP Server

Analyzes bash co
|    |-- trend-docs-mcp - mcp-trend-docs - Search and extract Tren
|    |-- mcp-server - import os
import json
import yaml
from p
|    |-- mcp-jira-lite - jira-lite MCP Server

Lightweight read-o
|    |-- mcp - Headless PM MCP Server - Model Context P
|    |-- mcp-syslog-export - MCP Syslog Export Server

Exports Vision
|    |-- mcp-trello-lite - trello-lite MCP Server

Lightweight Trel
|    |-- mcp-v1-admin-lite - v1-admin-lite MCP Server

Vision One adm
|    |-- mcp-v1-cloud-lite - v1-cloud-lite MCP Server

Vision One clo
|    |-- mcp-v1-intel-lite - v1-intel-lite MCP Server

Vision One thr
|    |-- mcp-v1-log-query - v1-log-query MCP Server

Vision One acti
|    |-- mcp-v1-response-lite - v1-response-lite MCP Server

Vision One 
|    |-- mcp-wiki-lite - wiki-lite MCP Server

Lightweight Conflu
|    |-- archive - Browser-Lite MCP Server
Playwright-based
|    |-- mcp-manager-py
|    |-- mcp-syslog-export_20260131 - MCP Syslog Export Server

Exports Vision
|    |-- mcp-v1-admin-lite_20260131 - v1-admin-lite MCP Server

Vision One adm
|    |-- mcp-v1-cloud-lite_20260131 - v1-cloud-lite MCP Server

Vision One clo
|    |-- mcp-v1-intel-lite_20260131 - v1-intel-lite MCP Server

Vision One thr
|    |-- mcp-v1-lite_labworker_20260131 - v1-lite MCP Server

Lightweight Vision O
|    |-- mcp-v1-log-query_20260131 - v1-log-query MCP Server

Vision One acti
|    |-- mcp-v1-response-lite_20260131 - v1-response-lite MCP Server

Vision One 
|    |-- mcp-v1ego-extension - mcp-v1ego - MCP Server for V1EGO Chrome 
|    |-- docker_mcp
|    |-- wiki-lite-old - wiki-lite MCP Server

Lightweight Conflu
|    |-- mcp-browser-helper - Browser Helper MCP - Adds convenience to
|    |-- managed-servers-20260222 - trello-lite MCP Server

Lightweight Trel
|    |-- mcp-trend-docs - mcp-trend-docs - Search and extract Tren
|    +-- esxi-mcp-server - Connect to vCenter/ESXi and retrieve mai
```

## Skills (113 total)
```
skills
|   # USER-LEVEL
|    |-- apex-central-api [R]
|    |-- auto-gsd [R]
|    |-- aws [R]
|    |-- chat-export [R]
|    |-- ci-guard [R]
|    |-- claude-backup [R]
|    |-- claude-monitor [R]
|    |-- claude-report [R]
|    |-- claude-scheduler [R]
|    |-- clawdbot-deploy [R]
|    |-- code-review [R]
|    |-- credential-manager [R]
|    |-- diagram-gen [R]
|    |-- diff-view [R]
|    |-- double-space-fixer [R]
|    |-- dynamics-api [R]
|    |-- emu-marketplace [R]
|    |-- gh-ci-setup [R]
|    |-- hook-flow-bundle [R]
|    |-- hook-manager [R]
|    |-- marketplace-manager [R]
|    |-- mcp-manager [R]
|    |-- network-scan [R]
|    |-- open-notepad [R]
|    |-- pm-report [R]
|    |-- pr-review [R]
|    |-- project-maker [R]
|    |-- project-pattern [R]
|    |-- publish-project [R]
|    |-- rule-manager [R]
|    |-- security-scan [R]
|    |-- skill-maker [R]
|    |-- skill-manager [R]
|    |-- super-manager [R]
|    |-- terraform-skill [R]
|    |-- trend-docs [R]
|    |-- v1-api [R]
|    |-- v1-oat-report [R]
|    |-- v1-policy [R]
|    |-- weekly-update [R]
|    +-- wiki-api [R]
|   # MARKETPLACE
|    |-- algorithmic-art [U]
|    |-- brand-guidelines [U]
|    |-- canvas-design [U]
|    |-- doc-coauthoring [U]
|    |-- docx [U]
|    |-- frontend-design [U]
|    |-- internal-comms [U]
|    |-- mcp-builder [U]
|    |-- pdf [U]
|    |-- pptx [R]
|    |-- skill-creator [U]
|    |-- slack-gif-creator [U]
|    |-- theme-factory [U]
|    |-- web-artifacts-builder [U]
|    |-- webapp-testing [U]
|    +-- xlsx [U]
|   # UNREGISTERED
|    |-- aws-skill [U]
|    |-- chat-export [U]
|    |-- credential-manager [U]
|    |-- hook-manager [U]
|    |-- instruction-manager [U]
|    |-- mcp-manager [U]
|    |-- skill-manager [U]
|    |-- super-manager [U]
|    |-- chat-export [U]
|    |-- credential-manager [U]
|    |-- diff-view [U]
|    |-- hook-manager [U]
|    |-- instruction-manager [U]
|    |-- mcp-manager [U]
|    |-- pm-report [U]
|    |-- skill-manager [U]
|    |-- super-manager [U]
|    |-- trend-docs [U]
|    |-- trend-docs-mcp [U]
|    |-- v1-api [U]
|    |-- v1-oat-report [U]
|    |-- enablement [U]
|    |-- vpn-monitor [U]
|    |-- aws-skill [U]
|    |-- credential-manager [U]
|    |-- hook-manager [U]
|    |-- instruction-manager [U]
|    |-- mcp-manager [U]
|    |-- skill-manager [U]
|    |-- super-manager [U]
|    |-- chat-export [U]
|    |-- credential-manager [U]
|    |-- diff-view [U]
|    |-- hook-manager [U]
|    |-- instruction-manager [U]
|    |-- mcp-manager [U]
|    |-- pm-report [U]
|    |-- skill-manager [U]
|    |-- super-manager [U]
|    |-- trend-docs [U]
|    |-- trend-docs-mcp [U]
|    |-- v1-api [U]
|    |-- v1-oat-report [U]
|    |-- enablement [U]
|    |-- diff-view [U]
|    |-- hook-maker [U]
|    |-- network-scan [U]
|    |-- open-notepad [U]
|    |-- security-scan [U]
|    |-- azure-lab-monitor [U]
|    |-- TEMPLATE [U]
|    |-- ecosystem-setup [U]
|    |-- vpn-monitor [U]
|    |-- Microsoft Teams Chat Files [U]
|    |-- v1-query-gen [U]
|    +-- v1-query-gen [U]
```

## Hooks (171 total)
```
hooks
|   # UserPromptSubmit
|    |-- [*] node "/home/claude/.claude/hooks/sm-userpromptsu...
|    +-- [*] node "/home/claude/.claude/hooks/tool-reminder.j...
|   # SessionStart
|    |-- [*] node "/home/claude/.claude/hooks/sm-sessionstart...
|    |-- [*] node "/home/claude/.claude/hooks/skill-manager-s...
|    |-- [*] node "/home/claude/.claude/hooks/gsd-check-updat...
|    |-- [*] node "/home/claude/.claude/hooks/gsd-intel-sessi...
|    +-- [*] TRIGGER=SessionStart bash "$HOME/.claude/skills/cl...
|   # SessionEnd
|    |-- [*] TRIGGER=SessionEnd bash "$HOME/.claude/skills/clau...
|    +-- [*] node "$HOME/.claude/hooks/session-end-report.js"...
|   # PostToolUse
|    |-- [*] node "/home/claude/.claude/hooks/gsd-intel-index...
|    |-- [Task] node "/home/claude/.claude/hooks/gsd-verifier-ch...
|    |-- [Skill|Task|Bash|TaskStop|mcp__mcp-manager__mcpm] node "/home/claude/.claude/hooks/sm-posttooluse....
|    |-- [Skill|Task] node "/home/claude/.claude/hooks/super-manager-c...
|    +-- [Skill|Task] node "/home/claude/.claude/hooks/skill-usage-tra...
|   # PreToolUse
|    |-- [Bash|Edit|Write|Read|Glob|Grep|WebFetch|WebSearch|mcp__mcp-manager__mcpm] node "/home/claude/.claude/hooks/sm-pretooluse.j...
|    +-- [Bash|Edit|Write|Read|Glob|Grep|WebFetch|WebSearch] node "/home/claude/.claude/hooks/super-manager-e...
|   # Stop
|    +-- [*] node "/home/claude/.claude/hooks/sm-stop.js"...
|   # ARCHIVED
|    |-- browser-safety
|    |-- config-awareness
|    |-- empty-prompt-guard
|    |-- mcp-injector
|    |-- read-global-claude-md
|    |-- read-latest-session-doc
|    |-- rule-guidelines-gate
|    |-- rule-stop
|    |-- skill-injector
|    |-- skill-manager-session
|    |-- skill-usage-tracker
|    |-- super-manager-check-enforcement
|    |-- super-manager-enforcement-gate
|    |-- task-output-reminder
|    |-- tool-reminder
|    |-- gsd-check-update
|    |-- gsd-intel-index
|    |-- gsd-intel-prune
|    |-- gsd-intel-session
|    |-- gsd-statusline
|    |-- reset-strikes
|    +-- troubleshoot
|   # ORPHANED (not in config)
|    |-- auto-gsd
|    |-- autonomous-decision
|    |-- gsd-gate
|    |-- gsd-intel-prune
|    |-- gsd-statusline
|    |-- hook-logger
|    |-- hook-report
|    |-- mcp-autostart
|    |-- preference-learner
|    |-- project-sync-postcommit
|    |-- statusline
|    |-- validate-settings
|    |-- instruction-gate.js
|    |-- instruction-loader.js
|    |-- stop-check.js
|    |-- claude-cred.js
|    |-- auto-gsd.js
|    |-- autonomous-decision.js
|    |-- config-awareness.js
|    |-- gsd-check-update.js
|    |-- gsd-gate.js
|    |-- gsd-intel-prune.js
|    |-- gsd-intel-session.js
|    |-- gsd-statusline.js
|    |-- gsd-verifier-check.js
|    |-- hook-logger.js
|    |-- hook-report.js
|    |-- instruction-stop.js
|    |-- mcp-autostart.js
|    |-- preference-learner.js
|    |-- project-sync-postcommit.js
|    |-- session-end-report.js
|    |-- skill-manager-session.js
|    |-- skill-usage-tracker.js
|    |-- sm-posttooluse.js
|    |-- sm-pretooluse.js
|    |-- sm-sessionstart.js
|    |-- sm-stop.js
|    |-- sm-userpromptsubmit.js
|    |-- statusline.js
|    |-- super-manager-check-enforcement.js
|    |-- super-manager-enforcement-gate.js
|    |-- tool-reminder.js
|    |-- validate-settings.js
|    |-- setup.js
|    |-- uninstall.js
|    |-- setup.js
|    |-- uninstall.js
|    |-- setup.js
|    |-- uninstall.js
|    |-- setup.js
|    |-- setup.js
|    |-- setup-utils.js
|    |-- claude-cred.js
|    |-- setup-utils.js
|    |-- test-hook-pipeline.js
|    |-- claude-cred.js
|    |-- setup.js
|    |-- uninstall.js
|    |-- setup.js
|    |-- rollback.js
|    |-- setup.js
|    |-- setup.js
|    |-- post-install.js
|    |-- extensionServer.js
|    |-- relayClient.js
|    |-- stop-check.js
|    |-- claude-cred.js
|    |-- auto-gsd.js
|    |-- autonomous-decision.js
|    |-- config-awareness.js
|    |-- gsd-check-update.js
|    |-- gsd-gate.js
|    |-- gsd-intel-prune.js
|    |-- gsd-intel-session.js
|    |-- gsd-statusline.js
|    |-- gsd-verifier-check.js
|    |-- hook-logger.js
|    |-- hook-report.js
|    |-- instruction-stop.js
|    |-- mcp-autostart.js
|    |-- preference-learner.js
|    |-- project-sync-postcommit.js
|    |-- session-end-report.js
|    |-- skill-manager-session.js
|    |-- skill-usage-tracker.js
|    |-- sm-posttooluse.js
|    |-- sm-pretooluse.js
|    |-- sm-sessionstart.js
|    |-- sm-stop.js
|    |-- sm-userpromptsubmit.js
|    |-- statusline.js
|    |-- super-manager-check-enforcement.js
|    |-- super-manager-enforcement-gate.js
|    |-- tool-reminder.js
|    |-- validate-settings.js
|    |-- setup.js
|    |-- uninstall.js
|    |-- setup.js
|    |-- uninstall.js
|    |-- setup.js
|    |-- uninstall.js
|    |-- setup.js
|    |-- setup.js
|    |-- setup-utils.js
|    |-- claude-cred.js
|    |-- setup-utils.js
|    |-- test-hook-pipeline.js
|    |-- claude-cred.js
|    |-- setup.js
|    |-- uninstall.js
|    |-- setup.js
|    |-- rollback.js
|    |-- setup.js
|    |-- setup.js
|    |-- chat-export.js
|    |-- vendor.js
|    |-- index.js
|    |-- post-install.js
|    |-- extensionServer.js
|    |-- relayClient.js
|    |-- post-install.js
|    |-- extensionServer.js
|    |-- relayClient.js
|    |-- index.js
|    |-- index.js
|    |-- background.js
|    |-- popup.js
|    |-- claude-api-service.js
|    |-- conversation-manager.js
|    |-- webhook-service.js
|    +-- e2e.js
```

## Hook Flow

```
Event Flow:
  [SessionStart] (5 hooks)
    -> [*] sm-sessionstart.js"
    -> [*] skill-manager-session.js"
    -> [*] gsd-check-update.js"
    -> [*] gsd-intel-session.js"
    -> [*] backup.sh"
  |
  v
  [UserPromptSubmit] (2 hooks)
    -> [*] sm-userpromptsubmit.js"
    -> [*] tool-reminder.js"
  |
  v
  [PreToolUse] (2 hooks)
    -> [Bash|Edit|Write|Read|Glob|Grep|WebFetch|WebSearch|mcp__mcp-manager__mcpm] sm-pretooluse.js"
    -> [Bash|Edit|Write|Read|Glob|Grep|WebFetch|WebSearch] super-manager-enforcement-gate
  |
  v
  [PostToolUse] (5 hooks)
    -> [*] gsd-intel-index.js"
    -> [Task] gsd-verifier-check.js"
    -> [Skill|Task|Bash|TaskStop|mcp__mcp-manager__mcpm] sm-posttooluse.js"
    -> [Skill|Task] super-manager-check-enforcemen
    -> [Skill|Task] skill-usage-tracker.js"
  |
  v
  [Stop] (1 hooks)
    -> [*] sm-stop.js"
  |
  v
  [SessionEnd] (2 hooks)
    -> [*] backup.sh"
    -> [*] session-end-report.js"
```

## Security Flags

| Type | File | Message | Severity |
|------|------|---------|----------|
| unexpected_location | ~/Documents/ProjectsCL1/Archive/mcp-mana | File outside expected paths | warning |
| recent_mod | ~/Documents/ProjectsCL1/Archive/mcp-mana | Modified 2026-03-06 15:31 | info |
| external_url | ~/Documents/ProjectsCL1/Archive/mcp-mana | Found: https://your-domain.atlassian.net, https:// | info |
| network_calls | ~/Documents/ProjectsCL1/Archive/mcp-mana | Found: requests. | info |
| unexpected_location | ~/Documents/ProjectsCL1/Archive/mcp-mana | File outside expected paths | warning |
| recent_mod | ~/Documents/ProjectsCL1/Archive/mcp-mana | Modified 2026-03-06 15:31 | info |
| external_url | ~/Documents/ProjectsCL1/Archive/mcp-mana | Found: https://api.trello.com/1, https://trello.co | info |
| network_calls | ~/Documents/ProjectsCL1/Archive/mcp-mana | Found: requests. | info |
| unexpected_location | ~/Documents/ProjectsCL1/Archive/mcp-mana | File outside expected paths | warning |
| recent_mod | ~/Documents/ProjectsCL1/Archive/mcp-mana | Modified 2026-03-06 15:34 | info |
| unexpected_location | ~/Documents/ProjectsCL1/Archive/mcp-mana | File outside expected paths | warning |
| recent_mod | ~/Documents/ProjectsCL1/Archive/mcp-mana | Modified 2026-03-06 15:04 | info |
| unexpected_location | ~/Documents/ProjectsCL1/Archive/mcp-mana | File outside expected paths | warning |
| recent_mod | ~/Documents/ProjectsCL1/Archive/mcp-mana | Modified 2026-03-06 15:02 | info |
| unexpected_location | ~/Documents/ProjectsCL1/claude-code-skil | File outside expected paths | warning |
| recent_mod | ~/Documents/ProjectsCL1/claude-code-skil | Modified 2026-03-06 15:01 | info |
| external_url | ~/Documents/ProjectsCL1/claude-code-skil | Found: https://docs.trendmicro.com/.../page1,https | info |
| shell_injection | ~/Documents/ProjectsCL1/claude-code-skil | Found: subprocess | warning |
| unexpected_location | ~/Documents/ProjectsCL1/claude-code-skil | File outside expected paths | warning |
| recent_mod | ~/Documents/ProjectsCL1/claude-code-skil | Modified 2026-03-06 15:00 | info |
| recent_mod | ~/Documents/ProjectsCL1/MCP/archive/tmp- | Modified 2026-03-06 16:41 | info |
| external_url | ~/Documents/ProjectsCL1/MCP/archive/tmp- | Found: https://your-domain.atlassian.net, https:// | info |
| network_calls | ~/Documents/ProjectsCL1/MCP/archive/tmp- | Found: requests. | info |
| unexpected_location | ~/OneDrive - TrendMicro/Documents/Projec | File outside expected paths | warning |
| unexpected_location | ~/OneDrive - TrendMicro/Documents/Projec | File outside expected paths | warning |
| external_url | ~/OneDrive - TrendMicro/Documents/Projec | Found: https://api.eu.xdr.trendmicro.com, https:// | info |
| network_calls | ~/OneDrive - TrendMicro/Documents/Projec | Found: urllib | info |
| unexpected_location | ~/OneDrive - TrendMicro/Documents/Projec | File outside expected paths | warning |
| external_url | ~/OneDrive - TrendMicro/Documents/Projec | Found: https://api.trello.com/1, https://trello.co | info |
| network_calls | ~/OneDrive - TrendMicro/Documents/Projec | Found: requests. | info |
| unexpected_location | ~/OneDrive - TrendMicro/Documents/Projec | File outside expected paths | warning |
| external_url | ~/OneDrive - TrendMicro/Documents/Projec | Found: https://api.eu.xdr.trendmicro.com, https:// | info |
| base64_string | ~/OneDrive - TrendMicro/Documents/Projec | Found: 0/endpointSecurity/versionControlPolicies | info |
| network_calls | ~/OneDrive - TrendMicro/Documents/Projec | Found: requests. | info |
| unexpected_location | ~/OneDrive - TrendMicro/Documents/Projec | File outside expected paths | warning |
| external_url | ~/OneDrive - TrendMicro/Documents/Projec | Found: https://api.eu.xdr.trendmicro.com, https:// | info |
| network_calls | ~/OneDrive - TrendMicro/Documents/Projec | Found: requests. | info |
| unexpected_location | ~/OneDrive - TrendMicro/Documents/Projec | File outside expected paths | warning |
| external_url | ~/OneDrive - TrendMicro/Documents/Projec | Found: https://api.eu.xdr.trendmicro.com, https:// | info |
| base64_string | ~/OneDrive - TrendMicro/Documents/Projec | Found: 0/threatintel/suspiciousObjectExceptions/de | info |
| network_calls | ~/OneDrive - TrendMicro/Documents/Projec | Found: requests. | info |
| unexpected_location | ~/OneDrive - TrendMicro/Documents/Projec | File outside expected paths | warning |
| external_url | ~/OneDrive - TrendMicro/Documents/Projec | Found: https://api.eu.xdr.trendmicro.com, https:// | info |
| network_calls | ~/OneDrive - TrendMicro/Documents/Projec | Found: requests. | info |
| unexpected_location | ~/OneDrive - TrendMicro/Documents/Projec | File outside expected paths | warning |
| external_url | ~/OneDrive - TrendMicro/Documents/Projec | Found: https://api.eu.xdr.trendmicro.com, https:// | info |
| network_calls | ~/OneDrive - TrendMicro/Documents/Projec | Found: requests. | info |
| unexpected_location | ~/OneDrive - TrendMicro/Documents/Projec | File outside expected paths | warning |
| external_url | ~/OneDrive - TrendMicro/Documents/Projec | Found: https://trendmicro.atlassian.net/wiki, http | info |
| base64_string | ~/OneDrive - TrendMicro/Documents/Projec | Found: net/wiki/spaces/SPACE/pages/1234567/Title | info |

*... and 477 more flags*

## MCP Server Details

| Name | Status | Source | Command | Description |
|------|--------|--------|---------|-------------|
| v1ego | stopped | mcp-manager | node | MCP server that controls V1EGO |
| v1-lite | stopped | mcp-manager | python | Vision One API wrapper - alert |
| trendgpt | stopped | mcp-manager | node | TrendGPT A2A Gateway - Trend M |
| wiki-lite | stopped | mcp-manager | python | Confluence wiki search and syn |
| blueprint | stopped | mcp-manager | npx | Blueprint MCP with incognito |
| trend-docs | stopped | mcp-manager | python | Search and read Trend Micro do |
| playwriter | disabled | mcp-manager | npx | Playwriter MCP - full Playwrig |
| browser | disabled | mcp-manager |  | Official Browser MCP via Chrom |
| example-python | disabled | mcp-manager | python | Example Python MCP server |
| example-node | disabled | mcp-manager | node | Example Node.js MCP server |
| example-remote | disabled | mcp-manager |  | Example remote MCP server |
| example-websocket | disabled | mcp-manager |  | Example WebSocket MCP server |
| browser-cdp | disabled | mcp-manager | node | MCP server for browser automat |
| browser-local | disabled | mcp-manager | node | MCP server for browser automat |
| jira-lite | unregistered | discovered | - | jira-lite MCP Server

Lightwei |
| trello-lite | unregistered | discovered | - | trello-lite MCP Server

Lightw |
| mcp-v1-ego | unregistered | discovered | - | V1-Ego: Stateful Vision One an |
| mcp-v1-lite | unregistered | discovered | - | import os
import json
import y |
| mcp-bash-helper | unregistered | discovered | - | Bash Helper MCP Server

Analyz |
| trend-docs-mcp | unregistered | discovered | - | mcp-trend-docs - Search and ex |
| mcp-server | unregistered | discovered | - | import os
import json
import y |
| mcp-jira-lite | unregistered | discovered | - | jira-lite MCP Server

Lightwei |
| mcp | unregistered | discovered | - | Headless PM MCP Server - Model |
| mcp-syslog-export | unregistered | discovered | - | MCP Syslog Export Server

Expo |
| mcp-trello-lite | unregistered | discovered | - | trello-lite MCP Server

Lightw |
| mcp-v1-admin-lite | unregistered | discovered | - | v1-admin-lite MCP Server

Visi |
| mcp-v1-cloud-lite | unregistered | discovered | - | v1-cloud-lite MCP Server

Visi |
| mcp-v1-intel-lite | unregistered | discovered | - | v1-intel-lite MCP Server

Visi |
| mcp-v1-log-query | unregistered | discovered | - | v1-log-query MCP Server

Visio |
| mcp-v1-response-lite | unregistered | discovered | - | v1-response-lite MCP Server

V |
| mcp-wiki-lite | unregistered | discovered | - | wiki-lite MCP Server

Lightwei |
| archive | unregistered | discovered | - | Browser-Lite MCP Server
Playwr |
| mcp-manager-py | unregistered | discovered | - |  |
| mcp-syslog-export_20260131 | unregistered | discovered | - | MCP Syslog Export Server

Expo |
| mcp-v1-admin-lite_20260131 | unregistered | discovered | - | v1-admin-lite MCP Server

Visi |
| mcp-v1-cloud-lite_20260131 | unregistered | discovered | - | v1-cloud-lite MCP Server

Visi |
| mcp-v1-intel-lite_20260131 | unregistered | discovered | - | v1-intel-lite MCP Server

Visi |
| mcp-v1-lite_labworker_20260131 | unregistered | discovered | - | v1-lite MCP Server

Lightweigh |
| mcp-v1-log-query_20260131 | unregistered | discovered | - | v1-log-query MCP Server

Visio |
| mcp-v1-response-lite_20260131 | unregistered | discovered | - | v1-response-lite MCP Server

V |
| mcp-v1ego-extension | unregistered | discovered | - | mcp-v1ego - MCP Server for V1E |
| docker_mcp | unregistered | discovered | - |  |
| wiki-lite-old | unregistered | discovered | - | wiki-lite MCP Server

Lightwei |
| mcp-browser-helper | unregistered | discovered | - | Browser Helper MCP - Adds conv |
| managed-servers-20260222 | unregistered | discovered | - | trello-lite MCP Server

Lightw |
| mcp-trend-docs | unregistered | discovered | - | mcp-trend-docs - Search and ex |
| esxi-mcp-server | unregistered | discovered | - | Connect to vCenter/ESXi and re |

## Skill Details

| Name | Title | Source | Registered | Has Main |
|------|-------|--------|------------|----------|
| apex-central-api | Apex Central API Skill | user | Yes | No |
| auto-gsd | Write NNN-PLAN.md with Go | user | Yes | No |
| aws | AWS Skill | user | Yes | No |
| chat-export | Chat Export Skill | user | Yes | No |
| ci-guard | CI Guard | user | Yes | No |
| claude-backup | Claude Backup Skill | user | Yes | No |
| claude-monitor | Claude Monitor | user | Yes | No |
| claude-report | Claude Report | user | Yes | Yes |
| claude-scheduler | Claude Scheduler | user | Yes | No |
| clawdbot-deploy | Clawdbot AWS Deployment S | user | Yes | No |
| code-review | Code Review Skill | user | Yes | No |
| credential-manager | Credential Manager | user | Yes | No |
| diagram-gen | Diagram Generator | user | Yes | No |
| diff-view | Side-by-Side Diff Viewer | user | Yes | No |
| double-space-fixer | Double-Space Fixer | user | Yes | No |
| dynamics-api | Dynamics 365 CRM API Skil | user | Yes | No |
| emu-marketplace | Emu Marketplace Publisher | user | Yes | No |
| gh-ci-setup | GitHub CI Setup | user | Yes | No |
| hook-flow-bundle | Workflow Bundle | user | Yes | No |
| hook-manager | Hook Manager | user | Yes | No |
| marketplace-manager | Marketplace Manager | user | Yes | No |
| mcp-manager | MCP Manager | user | Yes | No |
| network-scan | Network Scanner | user | Yes | No |
| open-notepad | Open File in Notepad++ | user | Yes | No |
| pm-report | PM Report Skill | user | Yes | No |
| pr-review | PR Review | user | Yes | No |
| project-maker | Project Maker | user | Yes | Yes |
| project-pattern | Project Pattern | user | Yes | No |
| publish-project | Publish Project | user | Yes | No |
| rule-manager | Rule Manager | user | Yes | No |
| security-scan | Security Scanner Skill | user | Yes | No |
| skill-maker | Skill Maker | user | Yes | Yes |
| skill-manager | Skill Manager | user | Yes | No |
| super-manager | Super Manager | user | Yes | No |
| terraform-skill | Terraform Skill for Claud | user | Yes | No |
| trend-docs | Trend Docs Skill | user | Yes | No |
| v1-api | Vision One API Skill | user | Yes | No |
| v1-oat-report | V1 OAT Report Skill | user | Yes | No |
| v1-policy | V1 Policy Management Skil | user | Yes | No |
| weekly-update | Weekly Update PowerPoint  | user | Yes | No |
| wiki-api | Wiki API Skill | user | Yes | No |
| algorithmic-art | algorithmic-art | marketplace | No | No |
| brand-guidelines | Anthropic Brand Styling | marketplace | No | No |
| canvas-design | canvas-design | marketplace | No | No |
| doc-coauthoring | Doc Co-Authoring Workflow | marketplace | No | No |
| docx | DOCX creation, editing, a | marketplace | No | No |
| frontend-design | frontend-design | marketplace | No | No |
| internal-comms | internal-comms | marketplace | No | No |
| mcp-builder | MCP Server Development Gu | marketplace | No | No |
| pdf | PDF Processing Guide | marketplace | No | No |
| pptx | PPTX creation, editing, a | marketplace | Yes | No |
| skill-creator | Skill Creator | marketplace | No | No |
| slack-gif-creator | Slack GIF Creator | marketplace | No | No |
| theme-factory | Theme Factory Skill | marketplace | No | No |
| web-artifacts-builder | Web Artifacts Builder | marketplace | No | No |
| webapp-testing | Web Application Testing | marketplace | No | No |
| xlsx | Requirements for Outputs | marketplace | No | No |
| aws-skill | AWS Skill | unregistered | No | No |
| chat-export | Chat Export Skill | unregistered | No | No |
| credential-manager | Credential Manager | unregistered | No | No |
| hook-manager | Hook Manager | unregistered | No | No |
| instruction-manager | Instruction Manager | unregistered | No | No |
| mcp-manager | MCP Manager | unregistered | No | No |
| skill-manager | Skill Manager | unregistered | No | No |
| super-manager | Super Manager | unregistered | No | No |
| chat-export | Chat Export | unregistered | No | No |
| credential-manager | Credential Manager | unregistered | No | No |
| diff-view | Side-by-Side Diff Viewer | unregistered | No | No |
| hook-manager | Hook Manager | unregistered | No | No |
| instruction-manager | Instruction Manager | unregistered | No | No |
| mcp-manager | MCP Manager (mcpm) | unregistered | No | No |
| pm-report | PM Report Skill | unregistered | No | No |
| skill-manager | Skill Manager | unregistered | No | No |
| super-manager | Super Manager | unregistered | No | No |
| trend-docs | Trend Docs Skill | unregistered | No | No |
| trend-docs-mcp | trend-docs-mcp | unregistered | No | No |
| v1-api | Vision One API Skill | unregistered | No | No |
| v1-oat-report | V1 OAT Report Skill | unregistered | No | No |
| enablement | Chat Export | unregistered | No | No |
| vpn-monitor | VPN Monitor | unregistered | No | No |
| aws-skill | AWS Skill | unregistered | No | No |
| credential-manager | Credential Manager | unregistered | No | No |
| hook-manager | Hook Manager | unregistered | No | No |
| instruction-manager | Instruction Manager | unregistered | No | No |
| mcp-manager | MCP Manager | unregistered | No | No |
| skill-manager | Skill Manager | unregistered | No | No |
| super-manager | Super Manager | unregistered | No | No |
| chat-export | Chat Export | unregistered | No | No |
| credential-manager | Credential Manager | unregistered | No | No |
| diff-view | Side-by-Side Diff Viewer | unregistered | No | No |
| hook-manager | Hook Manager | unregistered | No | No |
| instruction-manager | Instruction Manager | unregistered | No | No |
| mcp-manager | MCP Manager (mcpm) | unregistered | No | No |
| pm-report | PM Report Skill | unregistered | No | No |
| skill-manager | Skill Manager | unregistered | No | No |
| super-manager | Super Manager | unregistered | No | No |
| trend-docs | Trend Docs Skill | unregistered | No | No |
| trend-docs-mcp | trend-docs-mcp | unregistered | No | No |
| v1-api | Vision One API Skill | unregistered | No | No |
| v1-oat-report | V1 OAT Report Skill | unregistered | No | No |
| enablement | Chat Export | unregistered | No | No |
| diff-view | Side-by-Side Diff Viewer | unregistered | No | No |
| hook-maker | Hook Maker | unregistered | No | No |
| network-scan | Network Scanner | unregistered | No | No |
| open-notepad | Open File in Notepad++ | unregistered | No | No |
| security-scan | Security Scanner Skill | unregistered | No | No |
| azure-lab-monitor | Azure Lab Cost Monitor | unregistered | No | No |
| TEMPLATE | CHANGEME Lab Name | unregistered | No | No |
| ecosystem-setup | Ecosystem Setup | unregistered | No | No |
| vpn-monitor | VPN Monitor | unregistered | No | No |
| Microsoft Teams Chat Files | Microsoft Teams Chat File | unregistered | No | Yes |
| v1-query-gen | Vision One Custom Filter  | unregistered | No | No |
| v1-query-gen | Vision One Custom Filter  | unregistered | No | No |