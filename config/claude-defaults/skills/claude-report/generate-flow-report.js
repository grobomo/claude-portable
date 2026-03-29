#!/usr/bin/env node
/**
 * Generate hook-flow-report.html dynamically from settings.json + rule directories.
 * Scans ~/.claude/rules/{EventType}/*.md for rules associated with each hook event.
 * Reads full rule .md content and hook .js source for display.
 * Output: hook-flow-report.html (self-contained, no external dependencies).
 */
var fs = require("fs");
var path = require("path");
var os = require("os");

var HOME = os.homedir();
var CLAUDE_DIR = path.join(HOME, ".claude");
var RULES_DIR = path.join(CLAUDE_DIR, "rules");
var HOOKS_DIR = path.join(CLAUDE_DIR, "hooks");
var SETTINGS_PATH = path.join(CLAUDE_DIR, "settings.json");
var OUTPUT_PATH = path.join(CLAUDE_DIR, "skills", "claude-report", "hook-flow-report.html");

// Allow output path override
if (process.argv[2]) OUTPUT_PATH = process.argv[2];

// ============================================================
// Hook metadata (static descriptions per known hook)
// ============================================================
var HOOK_META = {
  "sm-sessionstart": { description: "Super-manager session init. Scans hook/skill/MCP registries, writes config-report.md, injects config state.", exitBehavior: "exit 0: config report injected as context" },
  "skill-manager-session": { description: "Skill manager auto-maintenance. Scans skills directory, enriches keywords, updates skill-registry.json.", exitBehavior: "exit 0: skill inventory injected" },
  "gsd-check-update": { description: "GSD plugin update checker. Compares installed version against latest.", exitBehavior: "exit 0: update notice if available" },
  "gsd-intel-session": { description: "GSD codebase intelligence. Injects .planning/intel/ context if present.", exitBehavior: "exit 0: codebase intel injected" },
  "backup": { description: "Async backup of hooks, settings, and skills. Content-hashed, incremental.", exitBehavior: "async -- does not block" },
  "sm-userpromptsubmit": { description: "Super-manager prompt handler. Matches skills, MCP servers, and rules by keyword against user prompt. Threshold matching with min_matches.", exitBehavior: "exit 0: matched skills + MCP + rules injected as context" },
  "tool-reminder": { description: "Injects CLAUDE.md content and tool routing reminders. Caches per-session to avoid re-injection.", exitBehavior: "exit 0: CLAUDE.md + tool reminders injected" },
  "sm-pretooluse": { description: "Super-manager pre-tool gate. Validates tool calls against rules, can inject guidance or block.", exitBehavior: "exit 0: guidance injected | exit 2: tool call blocked" },
  "super-manager-enforcement-gate": { description: "Enforcement gate. Blocks tools until pending enforcement actions from super-manager are completed.", exitBehavior: "exit 0: proceed | exit 2: blocked until enforcement satisfied" },
  "gsd-intel-index": { description: "GSD codebase intelligence indexer. Updates .planning/intel/ after file operations.", exitBehavior: "exit 0: index updated silently" },
  "gsd-verifier-check": { description: "GSD verifier. Monitors Task tool for verifier completion, disables autonomous mode when done.", exitBehavior: "exit 0: verification status injected" },
  "sm-posttooluse": { description: "Super-manager post-tool observer. Logs skill/MCP usage, tracks enforcement state.", exitBehavior: "exit 0: usage logged, enforcement state updated" },
  "super-manager-check-enforcement": { description: "Checks if a Skill/Task call satisfies pending enforcement requirements.", exitBehavior: "exit 0: enforcement state updated" },
  "skill-usage-tracker": { description: "Tracks which skills are invoked and how often. Updates skill-registry.json usage counters.", exitBehavior: "exit 0: usage counter incremented" },
  "sm-stop": { description: "Escalating enforcement stop hook. Tests response against Stop rules (regex). Tracks block count per session. Checks transcript for tool-use to distinguish dodging from compliance.", exitBehavior: "exit 0 + no stdout: allow | exit 0 + {decision:block}: BLOCK response" },
  "session-end-report": { description: "Generates session summary report. Writes to .claude/session-reports/.", exitBehavior: "async -- runs after session closes" }
};

// Event metadata
var EVENT_META = {
  SessionStart: { order: 1, badge: "inject", badgeLabel: "INJECT", description: "Fires once when session begins. Stdout is injected into Claude's context.", exitCodes: [{ code: 0, meaning: "Allow -- stdout injected as system context" }, { code: 1, meaning: "Error -- hook failure, session continues" }] },
  UserPromptSubmit: { order: 2, badge: "inject", badgeLabel: "INJECT", description: "Fires on every user prompt before Claude processes it. Stdout injected as context alongside the prompt.", exitCodes: [{ code: 0, meaning: "Allow -- stdout injected as context with user prompt" }, { code: 1, meaning: "Error -- prompt continues without injection" }] },
  PreToolUse: { order: 3, badge: "gate", badgeLabel: "GATE", description: "Fires before each tool call. Can BLOCK tool execution (exit 2) or inject context (exit 0 + stdout).", exitCodes: [{ code: 0, meaning: "Allow tool -- stdout injected as context" }, { code: 1, meaning: "Error -- tool proceeds anyway" }, { code: 2, meaning: "BLOCK -- tool call is prevented, stdout shown as reason" }] },
  PostToolUse: { order: 4, badge: "check", badgeLabel: "CHECK", description: "Fires after each tool call completes. Observes results, updates state. Cannot block.", exitCodes: [{ code: 0, meaning: "Success -- stdout injected as context" }, { code: 1, meaning: "Error -- ignored, processing continues" }] },
  Stop: { order: 5, badge: "block", badgeLabel: "BLOCK", description: "Fires when Claude finishes responding. Can BLOCK the response and force retry via {\"decision\":\"block\"}.", exitCodes: [{ code: 0, meaning: "Allow response (no stdout = pass, stdout JSON with decision:block = BLOCK)" }, { code: 1, meaning: "Error -- response allowed anyway" }] },
  SessionEnd: { order: 6, badge: "async", badgeLabel: "ASYNC", description: "Fires when session ends. All hooks are async -- cannot block session termination.", exitCodes: [{ code: 0, meaning: "Success -- cleanup completed" }, { code: 1, meaning: "Error -- ignored, session ends anyway" }] }
};

// Which hook name loads rules from which directory
var HOOK_RULE_DIR_MAP = {
  "sm-userpromptsubmit": "UserPromptSubmit",
  "sm-stop": "Stop",
  "sm-pretooluse": "PreToolUse",
  "sm-posttooluse": "PostToolUse"
};

// ============================================================
// Parse frontmatter from .md files -- returns meta + full body
// ============================================================
function parseFrontmatter(content) {
  if (!content.startsWith("---")) return null;
  var endIdx = content.indexOf("---", 3);
  if (endIdx === -1) return null;
  var yaml = content.substring(3, endIdx).trim();
  var meta = {};
  var lines = yaml.split("\n");
  for (var i = 0; i < lines.length; i++) {
    var col = lines[i].indexOf(":");
    if (col === -1) continue;
    var key = lines[i].substring(0, col).trim();
    var val = lines[i].substring(col + 1).trim();
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
      val = val.slice(1, -1);
    }
    if (val.startsWith("[") && val.endsWith("]")) {
      meta[key] = val.slice(1, -1).split(",").map(function (s) { return s.trim().replace(/^['"]|['"]$/g, ""); });
    } else {
      meta[key] = val;
    }
  }
  // Full body -- everything after second ---
  meta._body = content.substring(endIdx + 3).trim();
  return meta;
}

// ============================================================
// Scan rules directory for a given event type
// ============================================================
function scanRules(eventDir) {
  var dirPath = path.join(RULES_DIR, eventDir);
  var rules = [];
  if (!fs.existsSync(dirPath)) return rules;
  var files;
  try { files = fs.readdirSync(dirPath); } catch (e) { return rules; }
  for (var i = 0; i < files.length; i++) {
    if (!files[i].endsWith(".md")) continue;
    if (files[i] === "README.md") continue;
    if (files[i] === "RULE-GUIDELINES.md") continue;
    var fp = path.join(dirPath, files[i]);
    var content;
    try { content = fs.readFileSync(fp, "utf-8"); } catch (e) { continue; }
    var meta = parseFrontmatter(content);
    if (!meta || !meta.id) continue;
    var rule = {
      id: meta.id,
      name: meta.name || meta.id,
      action: meta.action || "",
      description: meta.description || "",
      fullText: meta._body || ""
    };
    if (meta.pattern) rule.pattern = meta.pattern;
    if (meta.keywords && Array.isArray(meta.keywords)) rule.keywords = meta.keywords;
    if (meta.min_matches) rule.minMatches = parseInt(meta.min_matches, 10) || 2;
    else rule.minMatches = 2;
    if (meta.enabled === "false") rule.disabled = true;
    rules.push(rule);
  }
  rules.sort(function (a, b) { return a.id.localeCompare(b.id); });
  return rules;
}

// ============================================================
// Read hook script source for display
// ============================================================
function readHookSource(cmd) {
  var pathMatch = cmd.match(/["']([^"']+\.(js|sh))["']/);
  var scriptPath = null;
  if (pathMatch) {
    scriptPath = pathMatch[1];
  } else {
    var parts = cmd.split(/\s+/);
    for (var p = 0; p < parts.length; p++) {
      if (parts[p].match(/\.(js|sh)$/)) {
        scriptPath = parts[p];
        break;
      }
    }
  }
  if (!scriptPath) return "";
  // Resolve ~ to HOME
  scriptPath = scriptPath.replace(/^~/, HOME);
  // Try both forward and back slashes
  try {
    return fs.readFileSync(scriptPath, "utf-8");
  } catch (e) {
    try {
      return fs.readFileSync(scriptPath.replace(/\//g, "\\"), "utf-8");
    } catch (e2) {
      return "(source not found: " + scriptPath + ")";
    }
  }
}

// ============================================================
// Parse settings.json to get hooks
// ============================================================
function parseSettings() {
  var data;
  try { data = JSON.parse(fs.readFileSync(SETTINGS_PATH, "utf-8")); } catch (e) {
    console.error("Cannot read settings.json:", e.message);
    process.exit(1);
  }
  var events = {};
  var hookConfig = data.hooks || {};
  var eventNames = Object.keys(hookConfig);
  for (var ei = 0; ei < eventNames.length; ei++) {
    var eventName = eventNames[ei];
    var matchers = hookConfig[eventName];
    if (!events[eventName]) events[eventName] = [];
    for (var mi = 0; mi < matchers.length; mi++) {
      var matcher = matchers[mi].matcher || "*";
      var hooks = matchers[mi].hooks || [];
      for (var hi = 0; hi < hooks.length; hi++) {
        var cmd = hooks[hi].command || "";
        var isAsync = hooks[hi].async || false;
        var nameMatch = cmd.match(/[\/\\]([^\/\\]+?)(?:\.js|\.sh)?['"]*\s*$/);
        var hookName = nameMatch ? nameMatch[1] : cmd.substring(0, 40);
        // Extract display path
        var pathMatch = cmd.match(/["']([^"']+\.(js|sh))["']/);
        var scriptPath = pathMatch ? pathMatch[1].replace(HOME.replace(/\\/g, "/"), "~").replace(HOME.replace(/\//g, "\\"), "~") : cmd;
        if (!pathMatch) {
          var parts = cmd.split(/\s+/);
          for (var p = 0; p < parts.length; p++) {
            if (parts[p].match(/\.(js|sh)$/)) {
              scriptPath = parts[p].replace(HOME.replace(/\\/g, "/"), "~").replace(HOME.replace(/\//g, "\\"), "~");
              break;
            }
          }
        }
        var meta = HOOK_META[hookName] || { description: "Hook: " + hookName, exitBehavior: "exit 0: allow" };
        var rules = [];
        if (HOOK_RULE_DIR_MAP[hookName]) {
          rules = scanRules(HOOK_RULE_DIR_MAP[hookName]);
        }
        // Read hook source code
        var hookSource = readHookSource(cmd);
        events[eventName].push({
          name: hookName,
          script: scriptPath,
          matcher: matcher,
          async: isAsync,
          description: meta.description,
          exitBehavior: meta.exitBehavior,
          rules: rules,
          source: hookSource
        });
      }
    }
  }
  return events;
}

// ============================================================
// Build DATA structure
// ============================================================
function buildData() {
  var hooksByEvent = parseSettings();
  var eventOrder = ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "SessionEnd"];
  var events = [];
  for (var i = 0; i < eventOrder.length; i++) {
    var name = eventOrder[i];
    var meta = EVENT_META[name];
    if (!meta) continue;
    var hooks = hooksByEvent[name] || [];
    if (hooks.length === 0 && !hooksByEvent[name]) continue;
    events.push({
      name: name,
      order: meta.order,
      badge: meta.badge,
      badgeLabel: meta.badgeLabel,
      description: meta.description,
      exitCodes: meta.exitCodes,
      hooks: hooks
    });
  }
  return { events: events };
}

// ============================================================
// HTML Template -- all sections expanded by default, full text, +4pt fonts
// ============================================================
function generateHTML(data) {
  // Encode data as base64 to avoid any escaping issues
  var dataStr = JSON.stringify(data);
  var dataB64 = Buffer.from(dataStr).toString("base64");

  return '<!DOCTYPE html>\n\
<html lang="en">\n\
<head>\n\
<meta charset="UTF-8">\n\
<meta name="viewport" content="width=device-width, initial-scale=1.0">\n\
<title>Claude Code Hook &amp; Rule Flow</title>\n\
<style>\n\
* { margin: 0; padding: 0; box-sizing: border-box; }\n\
body { background: #0d1117; color: #e6edf3; font-family: "Segoe UI", system-ui, -apple-system, sans-serif; padding: 24px; min-height: 100vh; font-size: 16px; }\n\
h1 { text-align: center; font-size: 2em; margin-bottom: 8px; color: #58a6ff; }\n\
.subtitle { text-align: center; color: #8b949e; margin-bottom: 32px; font-size: 1.1em; }\n\
.generated { text-align: center; color: #484f58; font-size: 0.85em; margin-bottom: 24px; }\n\
.flow { max-width: 1100px; margin: 0 auto; position: relative; }\n\
.flow::before { content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 2px; background: #30363d; transform: translateX(-50%); z-index: 0; }\n\
.event-node { position: relative; z-index: 1; margin-bottom: 8px; }\n\
.event-header { background: #161b22; border: 2px solid #30363d; border-radius: 10px; padding: 16px 22px; cursor: pointer; user-select: none; transition: all 0.2s; display: flex; align-items: center; gap: 14px; }\n\
.event-header:hover { border-color: #58a6ff; background: #1a2332; }\n\
.event-header.open { border-color: #58a6ff; background: #0d1926; border-radius: 10px 10px 0 0; }\n\
.event-header .arrow { font-size: 1em; color: #8b949e; transition: transform 0.2s; min-width: 18px; font-family: monospace; }\n\
.event-header.open .arrow { transform: rotate(90deg); }\n\
.event-number { background: #58a6ff; color: #0d1117; font-weight: 700; font-size: 0.9em; padding: 4px 10px; border-radius: 6px; min-width: 24px; text-align: center; }\n\
.event-name { font-weight: 600; font-size: 1.2em; flex: 1; }\n\
.event-badge { font-size: 0.85em; padding: 3px 10px; border-radius: 4px; font-weight: 600; }\n\
.badge-inject { background: #1a3a1a; color: #3fb950; border: 1px solid #238636; }\n\
.badge-gate { background: #3a1a1a; color: #f85149; border: 1px solid #da3633; }\n\
.badge-check { background: #1a2a3a; color: #58a6ff; border: 1px solid #1f6feb; }\n\
.badge-block { background: #3a2a1a; color: #d29922; border: 1px solid #9e6a03; }\n\
.badge-async { background: #2a1a3a; color: #bc8cff; border: 1px solid #8957e5; }\n\
.event-count { color: #8b949e; font-size: 1em; }\n\
.event-body { display: none; background: #161b22; border: 2px solid #58a6ff; border-top: none; border-radius: 0 0 10px 10px; padding: 0; overflow: hidden; }\n\
.event-body.open { display: block; }\n\
.hook-row { border-bottom: 1px solid #21262d; }\n\
.hook-row:last-child { border-bottom: none; }\n\
.hook-header { padding: 12px 22px; cursor: pointer; display: flex; align-items: center; gap: 12px; transition: background 0.15s; }\n\
.hook-header:hover { background: #1a2332; }\n\
.hook-header .arrow { font-size: 0.9em; color: #8b949e; transition: transform 0.2s; min-width: 16px; font-family: monospace; }\n\
.hook-header.open .arrow { transform: rotate(90deg); }\n\
.hook-name { font-weight: 500; font-size: 1.05em; color: #e6edf3; flex: 1; }\n\
.hook-matcher { font-size: 0.85em; color: #8b949e; background: #21262d; padding: 2px 8px; border-radius: 3px; font-family: "Consolas", monospace; }\n\
.exit-code { font-size: 0.8em; padding: 2px 6px; border-radius: 3px; font-family: monospace; font-weight: 600; }\n\
.exit-0 { background: #1a3a1a; color: #3fb950; }\n\
.exit-1 { background: #3a2a1a; color: #d29922; }\n\
.exit-2 { background: #3a1a1a; color: #f85149; }\n\
.hook-detail { display: none; background: #0d1117; border-top: 1px solid #21262d; padding: 14px 22px 14px 46px; }\n\
.hook-detail.open { display: block; }\n\
.hook-detail .detail-section { margin-bottom: 12px; }\n\
.hook-detail .detail-section:last-child { margin-bottom: 0; }\n\
.detail-label { font-size: 0.85em; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }\n\
.detail-value { font-size: 1em; color: #c9d1d9; }\n\
.detail-value code { background: #21262d; padding: 2px 6px; border-radius: 3px; font-family: "Consolas", monospace; font-size: 0.95em; color: #79c0ff; }\n\
.detail-value .filepath { color: #d2a8ff; }\n\
.source-block { background: #0a0e14; border: 1px solid #21262d; border-radius: 6px; padding: 12px 16px; font-family: "Consolas", "Courier New", monospace; font-size: 0.85em; line-height: 1.5; color: #c9d1d9; white-space: pre-wrap; word-break: break-all; max-height: 500px; overflow-y: auto; margin-top: 6px; }\n\
.rule-row { border-top: 1px solid #1a1f26; }\n\
.rule-header { padding: 10px 22px 10px 46px; cursor: pointer; display: flex; align-items: center; gap: 10px; transition: background 0.15s; }\n\
.rule-header:hover { background: #1a2332; }\n\
.rule-header .arrow { font-size: 0.8em; color: #8b949e; transition: transform 0.2s; min-width: 14px; font-family: monospace; }\n\
.rule-header.open .arrow { transform: rotate(90deg); }\n\
.rule-icon { font-size: 0.85em; color: #8b949e; font-family: monospace; min-width: 16px; }\n\
.rule-name { font-size: 0.95em; color: #c9d1d9; flex: 1; }\n\
.rule-action { font-size: 0.82em; color: #8b949e; max-width: 350px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }\n\
.rule-disabled { opacity: 0.5; }\n\
.rule-detail { display: none; background: #0a0e14; border-top: 1px solid #1a1f26; padding: 12px 22px 12px 72px; }\n\
.rule-detail.open { display: block; }\n\
.rule-detail .rule-field { margin-bottom: 8px; }\n\
.rule-detail .rule-field:last-child { margin-bottom: 0; }\n\
.rule-field-label { font-size: 0.82em; color: #6e7681; text-transform: uppercase; letter-spacing: 0.3px; }\n\
.rule-field-value { font-size: 0.95em; color: #c9d1d9; word-break: break-word; }\n\
.rule-field-value.pattern { font-family: "Consolas", monospace; color: #ffa657; font-size: 0.9em; background: #1a1508; padding: 6px 10px; border-radius: 4px; display: block; margin-top: 3px; }\n\
.rule-field-value.keywords { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 3px; }\n\
.rule-field-value.keywords span { background: #1a2332; color: #79c0ff; padding: 2px 8px; border-radius: 3px; font-size: 0.9em; font-family: "Consolas", monospace; }\n\
.rule-full-text { background: #0a0e14; border: 1px solid #21262d; border-radius: 6px; padding: 12px 16px; font-family: "Consolas", "Courier New", monospace; font-size: 0.85em; line-height: 1.5; color: #c9d1d9; white-space: pre-wrap; word-break: break-word; max-height: 600px; overflow-y: auto; margin-top: 6px; }\n\
.connector { text-align: center; padding: 4px 0; position: relative; z-index: 1; }\n\
.connector .line { color: #58a6ff; font-size: 1.8em; line-height: 1; }\n\
.legend { max-width: 1100px; margin: 32px auto 24px; background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 18px 22px; }\n\
.legend h3 { font-size: 1em; color: #8b949e; margin-bottom: 12px; }\n\
.legend-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 10px; }\n\
.legend-item { display: flex; align-items: center; gap: 10px; font-size: 0.95em; }\n\
.stats { max-width: 1100px; margin: 0 auto 24px; display: flex; gap: 14px; flex-wrap: wrap; justify-content: center; }\n\
.stat { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 10px 18px; text-align: center; }\n\
.stat-num { font-size: 1.7em; font-weight: 700; color: #58a6ff; }\n\
.stat-label { font-size: 0.85em; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; }\n\
.collapse-controls { max-width: 1100px; margin: 8px auto 20px; text-align: center; }\n\
.collapse-controls button { background: #21262d; color: #8b949e; border: 1px solid #30363d; border-radius: 6px; padding: 6px 14px; cursor: pointer; font-size: 0.9em; margin: 0 4px; }\n\
.collapse-controls button:hover { background: #30363d; color: #e6edf3; }\n\
.hook-rule-controls { padding: 8px 22px 4px 46px; display: flex; gap: 8px; margin-top: 4px; }\n\
.hook-rule-controls button { background: #21262d; color: #8b949e; border: 1px solid #30363d; border-radius: 4px; padding: 3px 10px; cursor: pointer; font-size: 0.8em; }\n\
.hook-rule-controls button:hover { background: #30363d; color: #e6edf3; }\n\
</style>\n\
</head>\n\
<body>\n\
<h1>Claude Code Hook &amp; Rule Flow</h1>\n\
<p class="subtitle">Interactive session lifecycle -- click headers to expand/collapse</p>\n\
<p class="generated" id="genTime"></p>\n\
<div class="stats" id="stats"></div>\n\
<div class="legend">\n\
  <h3>EXIT CODE REFERENCE</h3>\n\
  <div class="legend-grid">\n\
    <div class="legend-item"><span class="exit-code exit-0">exit 0</span> Allow / pass-through (inject stdout as context)</div>\n\
    <div class="legend-item"><span class="exit-code exit-1">exit 1</span> Error (hook failure, ignored by Claude Code)</div>\n\
    <div class="legend-item"><span class="exit-code exit-2">exit 2</span> BLOCK (PreToolUse only -- prevents tool execution)</div>\n\
    <div class="legend-item"><span class="exit-code exit-0">exit 0</span> + stdout JSON = context injection (UserPromptSubmit, SessionStart)</div>\n\
    <div class="legend-item"><span class="exit-code exit-0">exit 0</span> + {"decision":"block"} = BLOCK response (Stop hook)</div>\n\
    <div class="legend-item"><span class="event-badge badge-async">ASYNC</span> Runs in background, does not block session</div>\n\
  </div>\n\
</div>\n\
<div class="collapse-controls"><button onclick="collapseAll()">Collapse All</button><button onclick="expandAll()">Expand All</button></div>\n\
<div class="flow" id="flow"></div>\n\
<script>\n\
var DATA = JSON.parse(atob("' + dataB64 + '"));\n\
function escapeHtml(s){if(!s)return"";return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}\n\
function toggleEvent(el){var b=document.getElementById("ebody-"+el.getAttribute("data-idx"));el.classList.toggle("open");b.classList.toggle("open");}\n\
function toggleHook(el){var d=document.getElementById(el.getAttribute("data-id"));el.classList.toggle("open");d.classList.toggle("open");}\n\
function toggleRule(el){var d=document.getElementById(el.getAttribute("data-id"));el.classList.toggle("open");d.classList.toggle("open");}\n\
function toggleHookRules(prefix,expand){var els=document.querySelectorAll("[id^=\\"rule-"+prefix+"\\"]");els.forEach(function(el){if(el.classList.contains("rule-detail")){if(expand)el.classList.add("open");else el.classList.remove("open");}});document.querySelectorAll("[data-id^=\\"rule-"+prefix+"\\"]").forEach(function(el){if(expand)el.classList.add("open");else el.classList.remove("open");});}\n\
function collapseAll(){document.querySelectorAll(".open").forEach(function(el){el.classList.remove("open");});}\n\
function expandAll(){document.querySelectorAll(".event-header").forEach(function(el){el.classList.add("open");document.getElementById("ebody-"+el.getAttribute("data-idx")).classList.add("open");});document.querySelectorAll(".hook-header").forEach(function(el){el.classList.add("open");document.getElementById(el.getAttribute("data-id")).classList.add("open");});document.querySelectorAll(".rule-header").forEach(function(el){el.classList.add("open");document.getElementById(el.getAttribute("data-id")).classList.add("open");});}\n\
function render(){\n\
  var flow=document.getElementById("flow"),stats=document.getElementById("stats");\n\
  document.getElementById("genTime").textContent="Generated: "+DATA.generated;\n\
  var tH=0,tR=0,tE=DATA.events.length;\n\
  DATA.events.forEach(function(e){tH+=e.hooks.length;e.hooks.forEach(function(h){tR+=h.rules.length;});});\n\
  stats.innerHTML=\'<div class="stat"><div class="stat-num">\'+tE+\'</div><div class="stat-label">Events</div></div><div class="stat"><div class="stat-num">\'+tH+\'</div><div class="stat-label">Hooks</div></div><div class="stat"><div class="stat-num">\'+tR+\'</div><div class="stat-label">Rules</div></div>\';\n\
  var html="";\n\
  DATA.events.forEach(function(evt,ei){\n\
    if(ei>0)html+=\'<div class="connector"><div class="line">&#9660;</div></div>\';\n\
    html+=\'<div class="event-node"><div class="event-header open" onclick="toggleEvent(this)" data-idx="\'+ei+\'">\';\n\
    html+=\'<span class="arrow">&#9654;</span><span class="event-number">\'+evt.order+\'</span>\';\n\
    html+=\'<span class="event-name">\'+evt.name+\'</span>\';\n\
    html+=\'<span class="event-badge badge-\'+evt.badge+\'">\'+evt.badgeLabel+\'</span>\';\n\
    var rc=0;evt.hooks.forEach(function(h){rc+=h.rules.length;});\n\
    html+=\'<span class="event-count">\'+evt.hooks.length+\' hook\'+(evt.hooks.length!==1?"s":"")+( rc>0 ? ", "+rc+" rule"+(rc!==1?"s":"") : "" )+\'</span></div>\';\n\
    html+=\'<div class="event-body open" id="ebody-\'+ei+\'">\';\n\
    html+=\'<div style="padding:14px 22px;border-bottom:1px solid #21262d;background:#0d1117;"><div style="font-size:0.95em;color:#8b949e;margin-bottom:10px;">\'+evt.description+\'</div><div style="display:flex;gap:10px;flex-wrap:wrap;">\';\n\
    evt.exitCodes.forEach(function(ec){html+=\'<div style="display:flex;align-items:center;gap:5px;"><span class="exit-code exit-\'+ec.code+\'">exit \'+ec.code+\'</span><span style="font-size:0.85em;color:#6e7681;">\'+ec.meaning+\'</span></div>\';});\n\
    html+=\'</div></div>\';\n\
    evt.hooks.forEach(function(hook,hi){\n\
      var hid="hook-"+ei+"-"+hi;\n\
      html+=\'<div class="hook-row"><div class="hook-header open" onclick="toggleHook(this)" data-id="\'+hid+\'">\';\n\
      html+=\'<span class="arrow">&#9654;</span>\';\n\
      if(hook.async)html+=\'<span class="event-badge badge-async" style="font-size:0.75em;padding:2px 6px;">ASYNC</span>\';\n\
      html+=\'<span class="hook-name">\'+hook.name+\'</span>\';\n\
      if(hook.matcher!=="*")html+=\'<span class="hook-matcher">\'+escapeHtml(hook.matcher)+\'</span>\';\n\
      if(hook.rules.length>0)html+=\'<span style="font-size:0.85em;color:#8b949e;">\'+hook.rules.length+\' rule\'+(hook.rules.length!==1?"s":"")+\'</span>\';\n\
      html+=\'</div>\';\n\
      html+=\'<div class="hook-detail open" id="\'+hid+\'">\';\n\
      html+=\'<div class="detail-section"><div class="detail-label">Script</div><div class="detail-value"><span class="filepath">\'+escapeHtml(hook.script)+\'</span></div></div>\';\n\
      html+=\'<div class="detail-section"><div class="detail-label">Exit Behavior</div><div class="detail-value"><code>\'+escapeHtml(hook.exitBehavior)+\'</code></div></div>\';\n\
      if(hook.source){\n\
        html+=\'<div class="detail-section"><div class="detail-label">Source Code</div><div class="source-block">\'+escapeHtml(hook.source)+\'</div></div>\';\n\
      }\n\
      html+=\'</div>\';\n\
      if(hook.rules.length>0){\n\
        var rprefix=ei+"-"+hi+"-";\n\
        html+=\'<div class="hook-rule-controls"><button onclick="toggleHookRules(\\\'\'+ei+"-"+hi+\'\\\',true)">Expand All Rules</button><button onclick="toggleHookRules(\\\'\'+ei+"-"+hi+\'\\\',false)">Collapse All Rules</button></div>\';\n\
        hook.rules.forEach(function(rule,ri){\n\
          var rid="rule-"+ei+"-"+hi+"-"+ri;\n\
          var dis=rule.disabled?" rule-disabled":"";\n\
          html+=\'<div class="rule-row\'+dis+\'"><div class="rule-header open" onclick="toggleRule(this)" data-id="\'+rid+\'">\';\n\
          html+=\'<span class="arrow">&#9654;</span><span class="rule-icon">*</span>\';\n\
          html+=\'<span class="rule-name">\'+escapeHtml(rule.id)+(rule.disabled?" [DISABLED]":"")+\'</span>\';\n\
          html+=\'<span class="rule-action">\'+escapeHtml(rule.action)+\'</span></div>\';\n\
          html+=\'<div class="rule-detail open" id="\'+rid+\'">\';\n\
          if(rule.pattern)html+=\'<div class="rule-field"><div class="rule-field-label">Pattern (regex)</div><div class="rule-field-value pattern">\'+escapeHtml(rule.pattern)+\'</div></div>\';\n\
          if(rule.keywords){\n\
            html+=\'<div class="rule-field"><div class="rule-field-label">Keywords (min_matches: \'+rule.minMatches+\')</div><div class="rule-field-value keywords">\';\n\
            rule.keywords.forEach(function(kw){html+=\'<span>\'+escapeHtml(kw)+\'</span>\';});\n\
            html+=\'</div></div>\';\n\
          }\n\
          html+=\'<div class="rule-field"><div class="rule-field-label">Full Rule Text</div><div class="rule-full-text">\'+escapeHtml(rule.fullText)+\'</div></div>\';\n\
          html+=\'</div></div>\';\n\
        });\n\
      }\n\
      html+=\'</div>\';\n\
    });\n\
    html+=\'</div></div>\';\n\
  });\n\
  flow.innerHTML=html;\n\
}\n\
render();\n\
</script>\n\
</body>\n\
</html>';
}

// ============================================================
// Main
// ============================================================
var data = buildData();
data.generated = new Date().toLocaleString();

var html = generateHTML(data);
fs.writeFileSync(OUTPUT_PATH, html);

// Stats
var totalHooks = 0, totalRules = 0;
data.events.forEach(function (e) {
  totalHooks += e.hooks.length;
  e.hooks.forEach(function (h) { totalRules += h.rules.length; });
});
console.log("Hook Flow Report generated: " + OUTPUT_PATH);
console.log("  " + data.events.length + " events, " + totalHooks + " hooks, " + totalRules + " rules");
