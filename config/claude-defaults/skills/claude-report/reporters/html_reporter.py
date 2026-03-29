"""HTML reporter - generates interactive dark-themed report."""
import html
import base64
import json as json_mod
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any


class HtmlReporter:
    """Generate self-contained HTML report matching hook-flow-report.html style."""

    CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #0d1117; color: #e6edf3; font-family: "Segoe UI", system-ui, -apple-system, sans-serif; padding: 24px; min-height: 100vh; font-size: 16px; }
h1 { text-align: center; font-size: 2em; margin-bottom: 8px; color: #58a6ff; }
.subtitle { text-align: center; color: #8b949e; margin-bottom: 32px; font-size: 1.1em; }
.generated { text-align: center; color: #484f58; font-size: 0.85em; margin-bottom: 24px; }

/* Stats bar */
.stats { max-width: 1100px; margin: 0 auto 24px; display: flex; gap: 14px; flex-wrap: wrap; justify-content: center; }
.stat { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 10px 18px; text-align: center; }
.stat-num { font-size: 1.7em; font-weight: 700; color: #58a6ff; }
.stat-label { font-size: 0.85em; color: #8b949e; }
.stat-num.green { color: #3fb950; }
.stat-num.amber { color: #d29922; }
.stat-num.red { color: #f85149; }
.stat-num.purple { color: #bc8cff; }

/* Sections */
.section { max-width: 1100px; margin: 0 auto 24px; }
.section-header { background: #161b22; border: 2px solid #30363d; border-radius: 10px; padding: 16px 22px; cursor: pointer; user-select: none; transition: all 0.2s; display: flex; align-items: center; gap: 14px; }
.section-header:hover { border-color: #58a6ff; background: #1a2332; }
.section-header.open { border-color: #58a6ff; background: #0d1926; border-radius: 10px 10px 0 0; }
.section-header .arrow { font-size: 1em; color: #8b949e; transition: transform 0.2s; min-width: 18px; font-family: monospace; }
.section-header.open .arrow { transform: rotate(90deg); }
.section-title { font-weight: 600; font-size: 1.2em; flex: 1; }
.section-count { color: #8b949e; font-size: 1em; }
.section-body { display: none; background: #161b22; border: 2px solid #58a6ff; border-top: none; border-radius: 0 0 10px 10px; overflow: hidden; }
.section-body.open { display: block; }

/* Expand/Collapse All button */
.expand-btn { font-size: 0.82em; padding: 3px 10px; border-radius: 4px; border: 1px solid #30363d; background: #21262d; color: #8b949e; cursor: pointer; font-family: "Segoe UI", system-ui, sans-serif; transition: all 0.15s; }
.expand-btn:hover { border-color: #58a6ff; color: #58a6ff; background: #1a2332; }

/* Items */
.item-row { border-bottom: 1px solid #21262d; padding: 10px 22px; display: flex; align-items: center; gap: 12px; }
.item-row:last-child { border-bottom: none; }
.item-row:hover { background: #1a2332; }
.item-name { font-weight: 500; font-size: 1em; color: #e6edf3; min-width: 180px; }
.item-desc { font-size: 0.9em; color: #8b949e; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item-source { font-size: 0.82em; color: #6e7681; font-family: "Consolas", monospace; }

/* Badges */
.badge { font-size: 0.82em; padding: 2px 8px; border-radius: 4px; font-weight: 600; }
.badge-running { background: #1a3a1a; color: #3fb950; border: 1px solid #238636; }
.badge-stopped { background: #3a2a1a; color: #d29922; border: 1px solid #9e6a03; }
.badge-disabled { background: #21262d; color: #8b949e; border: 1px solid #30363d; }
.badge-unregistered { background: #1a1a2a; color: #8b949e; border: 1px solid #30363d; }
.badge-active { background: #1a3a1a; color: #3fb950; border: 1px solid #238636; }
.badge-archived { background: #21262d; color: #8b949e; border: 1px solid #30363d; }
.badge-orphaned { background: #3a1a1a; color: #f85149; border: 1px solid #da3633; }
.badge-user { background: #1a2a3a; color: #58a6ff; border: 1px solid #1f6feb; }
.badge-project { background: #2a1a3a; color: #bc8cff; border: 1px solid #8957e5; }
.badge-marketplace { background: #1a3a2a; color: #3fb950; border: 1px solid #238636; }
.badge-registered { background: #0d1926; color: #58a6ff; }
.badge-warning { background: #3a2a1a; color: #d29922; border: 1px solid #9e6a03; }
.badge-info { background: #1a2a3a; color: #58a6ff; border: 1px solid #1f6feb; }

/* Sub-groups */
.group-label { padding: 8px 22px; font-size: 0.85em; color: #58a6ff; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; background: #0d1926; border-bottom: 1px solid #21262d; }

/* Hook flow timeline */
.flow { position: relative; }
.flow::before { content: ""; position: absolute; left: 50%; top: 0; bottom: 0; width: 2px; background: #30363d; transform: translateX(-50%); z-index: 0; }
.event-node { position: relative; z-index: 1; margin-bottom: 8px; }
.event-header { background: #161b22; border: 2px solid #30363d; border-radius: 10px; padding: 16px 22px; cursor: pointer; user-select: none; transition: all 0.2s; display: flex; align-items: center; gap: 14px; }
.event-header:hover { border-color: #58a6ff; background: #1a2332; }
.event-header.open { border-color: #58a6ff; background: #0d1926; border-radius: 10px 10px 0 0; }
.event-header .arrow { font-size: 1em; color: #8b949e; transition: transform 0.2s; min-width: 18px; font-family: monospace; }
.event-header.open .arrow { transform: rotate(90deg); }
.event-number { background: #58a6ff; color: #0d1117; font-weight: 700; font-size: 0.9em; padding: 4px 10px; border-radius: 6px; min-width: 24px; text-align: center; }
.event-name { font-weight: 600; font-size: 1.2em; flex: 1; }
.event-badge { font-size: 0.85em; padding: 3px 10px; border-radius: 4px; font-weight: 600; }
.badge-inject { background: #1a3a1a; color: #3fb950; border: 1px solid #238636; }
.badge-gate { background: #3a1a1a; color: #f85149; border: 1px solid #da3633; }
.badge-check { background: #1a2a3a; color: #58a6ff; border: 1px solid #1f6feb; }
.badge-block { background: #3a2a1a; color: #d29922; border: 1px solid #9e6a03; }
.badge-async { background: #2a1a3a; color: #bc8cff; border: 1px solid #8957e5; }
.event-count { color: #8b949e; font-size: 1em; }
.event-body { display: none; background: #161b22; border: 2px solid #58a6ff; border-top: none; border-radius: 0 0 10px 10px; padding: 0; overflow: hidden; }
.event-body.open { display: block; }
.hook-row { border-bottom: 1px solid #21262d; }
.hook-row:last-child { border-bottom: none; }
.hook-header { padding: 12px 22px; cursor: pointer; display: flex; align-items: center; gap: 12px; transition: background 0.15s; }
.hook-header:hover { background: #1a2332; }
.hook-header .arrow { font-size: 0.9em; color: #8b949e; transition: transform 0.2s; min-width: 16px; font-family: monospace; }
.hook-header.open .arrow { transform: rotate(90deg); }
.hook-name { font-weight: 500; font-size: 1.05em; color: #e6edf3; flex: 1; }
.hook-matcher { font-size: 0.85em; color: #8b949e; background: #21262d; padding: 2px 8px; border-radius: 3px; font-family: "Consolas", monospace; }
.exit-code { font-size: 0.8em; padding: 2px 6px; border-radius: 3px; font-family: monospace; font-weight: 600; }
.exit-0 { background: #1a3a1a; color: #3fb950; }
.exit-2 { background: #3a1a1a; color: #f85149; }
.hook-detail { display: none; background: #0d1117; border-top: 1px solid #21262d; padding: 14px 22px 14px 46px; }
.hook-detail.open { display: block; }
.hook-detail .detail-section { margin-bottom: 12px; }
.hook-detail .detail-section:last-child { margin-bottom: 0; }
.detail-label { font-size: 0.85em; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
.detail-value { font-size: 1em; color: #c9d1d9; }
.detail-value code { background: #21262d; padding: 2px 6px; border-radius: 3px; font-family: "Consolas", monospace; font-size: 0.95em; color: #79c0ff; }
.detail-value .filepath { color: #d2a8ff; }
.connector { text-align: center; padding: 4px 0; position: relative; z-index: 1; }
.connector .line { color: #58a6ff; font-size: 1.8em; line-height: 1; }

/* Rules nested under events */
.rule-row { border-top: 1px solid #1a1f26; }
.rule-header { padding: 10px 22px 10px 46px; cursor: pointer; display: flex; align-items: center; gap: 10px; transition: background 0.15s; }
.rule-header:hover { background: #1a2332; }
.rule-header .arrow { font-size: 0.8em; color: #8b949e; transition: transform 0.2s; min-width: 14px; font-family: monospace; }
.rule-header.open .arrow { transform: rotate(90deg); }
.rule-icon { font-size: 0.85em; color: #8b949e; font-family: monospace; min-width: 16px; }
.rule-name { font-size: 0.95em; color: #c9d1d9; flex: 1; }
.rule-action { font-size: 0.82em; color: #8b949e; max-width: 350px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rule-disabled { opacity: 0.5; }
.rule-detail { display: none; background: #0a0e14; border-top: 1px solid #1a1f26; padding: 12px 22px 12px 72px; }
.rule-detail.open { display: block; }
.rule-field { margin-bottom: 8px; }
.rule-field:last-child { margin-bottom: 0; }
.rule-field-label { font-size: 0.82em; color: #6e7681; text-transform: uppercase; letter-spacing: 0.3px; }
.rule-field-value { font-size: 0.95em; color: #c9d1d9; word-break: break-word; }
.rule-field-value.pattern { font-family: "Consolas", monospace; color: #ffa657; font-size: 0.9em; background: #1a1508; padding: 6px 10px; border-radius: 4px; display: block; margin-top: 3px; }
.rule-field-value.keywords { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 3px; }
.rule-field-value.keywords span { background: #1a2332; color: #79c0ff; padding: 2px 8px; border-radius: 3px; font-size: 0.9em; font-family: "Consolas", monospace; }
.level-controls { padding: 8px 22px; display: flex; gap: 6px; border-bottom: 1px solid #21262d; align-items: center; }
.level-controls.nested { padding: 8px 0; border-bottom: none; border-top: 1px solid #21262d; margin-top: 8px; }
.file-btn { font-size: 0.82em; padding: 3px 10px; border-radius: 4px; border: 1px solid #30363d; background: #21262d; color: #d2a8ff; cursor: pointer; font-family: "Segoe UI", system-ui, sans-serif; transition: all 0.15s; text-decoration: none; display: inline-block; }
.file-btn:hover { border-color: #bc8cff; color: #bc8cff; background: #2a1a3a; }
.file-btn.copied { color: #3fb950; border-color: #238636; }
.rule-full-text { background: #0a0e14; border: 1px solid #21262d; border-radius: 6px; padding: 12px 16px; font-family: "Consolas", "Courier New", monospace; font-size: 0.85em; line-height: 1.5; color: #c9d1d9; white-space: pre-wrap; word-break: break-word; max-height: 600px; overflow-y: auto; margin-top: 6px; }
.rule-stats { display: flex; gap: 4px; margin-top: 6px; flex-wrap: wrap; }
.rule-stats .stat-cell { display: flex; flex-direction: column; align-items: center; min-width: 48px; padding: 4px 8px; border-radius: 4px; background: #161b22; border: 1px solid #21262d; }
.rule-stats .stat-cell .stat-val { font-size: 1.1em; font-weight: 600; color: #8b949e; font-family: "Consolas", monospace; }
.rule-stats .stat-cell .stat-val.hot { color: #ffa657; }
.rule-stats .stat-cell .stat-val.very-hot { color: #f85149; }
.rule-stats .stat-cell .stat-win { font-size: 0.7em; color: #6e7681; text-transform: uppercase; }
.rule-stats .stat-cell .stat-val.zero { color: #30363d; }
.rule-why { background: #0d1a12; border: 1px solid #238636; border-radius: 6px; padding: 10px 14px; margin-top: 6px; font-size: 0.9em; color: #adbac7; line-height: 1.4; }
.rule-min-matches { display: inline-block; background: #1a1508; color: #d29922; padding: 2px 8px; border-radius: 3px; font-size: 0.85em; font-family: "Consolas", monospace; margin-left: 6px; }
.rule-source-badge { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 0.75em; font-family: "Consolas", monospace; margin-left: 6px; }
.rule-source-badge.src-rulebook { background: #1a2332; color: #58a6ff; }
.rule-source-badge.src-rules { background: #1a1508; color: #d29922; }
.rule-source-badge.src-mcp { background: #0d1a12; color: #3fb950; }
.rule-enabled-badge { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 0.75em; margin-left: 6px; }
.rule-enabled-badge.on { background: #0d1a12; color: #3fb950; }
.rule-enabled-badge.off { background: #1c0c0c; color: #f85149; }
.rule-kw-count { display: inline-block; color: #8b949e; font-size: 0.82em; margin-left: 6px; }
.mcp-rules-section { border-top: 2px solid #238636; margin-top: 16px; padding-top: 12px; }
.mcp-rules-header { font-size: 0.95em; color: #3fb950; margin-bottom: 8px; font-weight: 600; }

/* Rule editor */
.rule-editor { margin-top: 8px; }
.rule-editor textarea { width: 100%; min-height: 300px; background: #0d1117; color: #c9d1d9; border: 1px solid #30363d; border-radius: 6px; padding: 12px; font-family: "Consolas", "Courier New", monospace; font-size: 0.9em; line-height: 1.5; resize: vertical; }
.rule-editor textarea:focus { outline: none; border-color: #58a6ff; }
.rule-edit-actions { display: flex; gap: 8px; margin-top: 8px; align-items: center; flex-wrap: wrap; }
.edit-btn { padding: 5px 14px; border-radius: 5px; border: 1px solid #30363d; background: #21262d; color: #c9d1d9; cursor: pointer; font-size: 0.88em; font-family: "Segoe UI", system-ui, sans-serif; transition: all 0.15s; }
.edit-btn:hover { border-color: #58a6ff; color: #58a6ff; background: #1a2332; }
.edit-btn.save { background: #238636; border-color: #2ea043; color: #fff; }
.edit-btn.save:hover { background: #2ea043; border-color: #3fb950; }
.edit-btn.backup { background: #1a1508; border-color: #9e6a03; color: #d29922; }
.edit-btn.backup:hover { background: #2a1f08; border-color: #d29922; }
.edit-btn.cancel { background: #21262d; color: #8b949e; }
.edit-btn.cancel:hover { background: #30363d; color: #c9d1d9; }
.edit-btn.git-init { background: #0d1926; border-color: #1f6feb; color: #58a6ff; }
.edit-btn.git-init:hover { background: #1a2332; border-color: #58a6ff; }
.edit-status { font-size: 0.85em; margin-left: 8px; }
.edit-status.ok { color: #3fb950; }
.edit-status.err { color: #f85149; }
.edit-status.warn { color: #d29922; }
.git-banner { background: #1a1508; border: 1px solid #9e6a03; border-radius: 6px; padding: 8px 14px; margin-top: 8px; display: flex; align-items: center; gap: 10px; font-size: 0.88em; color: #d29922; }
.git-banner.ok { background: #0d1a12; border-color: #238636; color: #3fb950; }

/* Legend */
.legend { max-width: 1100px; margin: 32px auto 24px; background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 18px 22px; }
.legend h3 { font-size: 1em; color: #8b949e; margin-bottom: 12px; }
.legend-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 10px; }
.legend-item { display: flex; align-items: center; gap: 10px; font-size: 0.95em; }

/* Security */
.flag-row { border-bottom: 1px solid #21262d; padding: 8px 22px; display: flex; align-items: center; gap: 10px; font-size: 0.9em; }
.flag-row:last-child { border-bottom: none; }
.flag-type { min-width: 140px; font-family: "Consolas", monospace; color: #ffa657; }
.flag-file { min-width: 250px; color: #d2a8ff; font-family: "Consolas", monospace; font-size: 0.85em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.flag-msg { flex: 1; color: #8b949e; }
/* Share to ZIP */
.share-bar { max-width: 1100px; margin: 0 auto 18px; text-align: center; }
.share-btn { background: #238636; border: 1px solid #2ea043; color: #fff; padding: 8px 18px; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 0.95em; font-family: "Segoe UI", system-ui, sans-serif; transition: all 0.15s; }
.share-btn:hover { background: #2ea043; border-color: #3fb950; }
.modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); z-index: 1000; justify-content: center; align-items: center; }
.modal-overlay.open { display: flex; }
.modal { background: #161b22; border: 2px solid #30363d; border-radius: 12px; padding: 28px; max-width: 480px; width: 90%; }
.modal h2 { color: #58a6ff; margin-bottom: 6px; font-size: 1.3em; }
.modal .modal-sub { color: #8b949e; font-size: 0.9em; margin-bottom: 20px; }
.modal-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 18px; }
.modal-stat { background: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 8px 12px; font-size: 0.88em; }
.modal-stat .ms-num { color: #58a6ff; font-weight: 600; }
.modal-stat .ms-label { color: #8b949e; }
.modal label { display: block; color: #c9d1d9; font-size: 0.95em; margin-bottom: 6px; }
.modal input[type=password] { width: 100%; padding: 10px 14px; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; color: #e6edf3; font-size: 1em; margin-bottom: 12px; font-family: "Segoe UI", system-ui; box-sizing: border-box; }
.modal input[type=password]:focus { outline: none; border-color: #58a6ff; }
.modal .check-row { display: flex; align-items: center; gap: 8px; margin-bottom: 18px; color: #8b949e; font-size: 0.9em; cursor: pointer; }
.modal .check-row input[type=checkbox] { accent-color: #58a6ff; width: 16px; height: 16px; }
.modal .btn-row { display: flex; gap: 10px; }
.modal .btn-row button { flex: 1; padding: 10px; border-radius: 6px; font-size: 1em; font-weight: 600; cursor: pointer; font-family: "Segoe UI", system-ui; border: none; }
.modal .btn-export { background: #238636; color: #fff; }
.modal .btn-export:hover { background: #2ea043; }
.modal .btn-export:disabled { background: #21262d; color: #8b949e; cursor: not-allowed; }
.modal .btn-cancel { background: #21262d; color: #8b949e; border: 1px solid #30363d; }
.modal .btn-cancel:hover { background: #30363d; color: #c9d1d9; }
.modal .modal-error { color: #f85149; font-size: 0.9em; margin-top: 8px; display: none; }
.modal .modal-info { color: #6e7681; font-size: 0.82em; margin-top: 12px; }
.export-cats { max-height: 340px; overflow-y: auto; margin: 10px 0; border: 1px solid #30363d; border-radius: 8px; padding: 8px; }
.export-cat { margin-bottom: 6px; }
.cat-header { display: flex; align-items: center; gap: 8px; font-weight: 600; color: #58a6ff; cursor: pointer; padding: 4px 0; }
.cat-header input { margin: 0; }
.cat-items { padding-left: 24px; max-height: 0; overflow: hidden; transition: max-height 0.2s; }
.cat-header:has(input:checked) + .cat-items { max-height: 2000px; }
.item-check { display: flex; align-items: center; gap: 6px; padding: 2px 0; font-size: 0.85em; color: #c9d1d9; cursor: pointer; }
.item-check input { margin: 0; }
.item-name { font-family: monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.item-size { color: #6e7681; font-size: 0.85em; white-space: nowrap; }
.pw-toggle { margin-top: 6px; }
.pw-fields { transition: opacity 0.2s; margin-bottom: 4px; }
.pw-fields input { margin-bottom: 6px; }
"""

    JS = r"""
function toggle(id) {
    var h = document.getElementById('h-' + id);
    var b = document.getElementById('b-' + id);
    if (h && b) { h.classList.toggle('open'); b.classList.toggle('open'); }
}
function toggleHook(id) {
    var h = document.getElementById('hh-' + id);
    var d = document.getElementById('hd-' + id);
    if (h && d) { h.classList.toggle('open'); d.classList.toggle('open'); }
}
function toggleRule(id) {
    var h = document.getElementById('rh-' + id);
    var d = document.getElementById('rd-' + id);
    if (h && d) { h.classList.toggle('open'); d.classList.toggle('open'); }
}
function expandIn(pid, hc, bc) {
    var p = document.getElementById(pid); if (!p) return;
    var h = p.querySelectorAll('.' + hc + ':not(.open)');
    var b = p.querySelectorAll('.' + bc + ':not(.open)');
    for (var i = 0; i < h.length; i++) h[i].classList.add('open');
    for (var i = 0; i < b.length; i++) b[i].classList.add('open');
}
function collapseIn(pid, hc, bc) {
    var p = document.getElementById(pid); if (!p) return;
    var h = p.querySelectorAll('.' + hc + '.open');
    var b = p.querySelectorAll('.' + bc + '.open');
    for (var i = 0; i < h.length; i++) h[i].classList.remove('open');
    for (var i = 0; i < b.length; i++) b[i].classList.remove('open');
}
function expandAll(id) {
    expandIn(id, 'event-header', 'event-body');
    expandIn(id, 'hook-header', 'hook-detail');
    expandIn(id, 'rule-header', 'rule-detail');
}
function collapseAll(id) {
    collapseIn(id, 'rule-header', 'rule-detail');
    collapseIn(id, 'hook-header', 'hook-detail');
    collapseIn(id, 'event-header', 'event-body');
}
function copyPath(btn, path) {
    navigator.clipboard.writeText(path).then(function() {
        btn.textContent = 'Copied!';
        btn.classList.add('copied');
        setTimeout(function() { btn.textContent = 'Copy Path'; btn.classList.remove('copied'); }, 1500);
    });
}
var EDITOR_PORT = 0;
function editorApi(method, path, body) {
    if (!EDITOR_PORT) return Promise.reject('Editor server not running');
    var url = 'http://127.0.0.1:' + EDITOR_PORT + path;
    var opts = { method: method, headers: {'Content-Type': 'application/json'} };
    if (body) opts.body = JSON.stringify(body);
    return fetch(url, opts).then(function(r) { return r.json(); });
}
function editRule(rid, filePath) {
    var contentDiv = document.getElementById('content-' + rid);
    if (!contentDiv) return;
    // Toggle: if already editing, do nothing (use Cancel button)
    if (contentDiv.dataset.editing === 'true') return;
    // Save original content for cancel
    var originalHtml = contentDiv.innerHTML;
    contentDiv.dataset.editing = 'true';
    // Fetch full file content from server
    editorApi('GET', '/api/read?path=' + encodeURIComponent(filePath)).then(function(data) {
        if (data.error) { alert('Read error: ' + data.error); contentDiv.dataset.editing = ''; return; }
        // Replace content div with textarea + controls
        var fpEsc = filePath.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
        contentDiv.innerHTML = '<textarea id="ta-' + rid + '" spellcheck="false" style="width:100%;min-height:300px;background:#0d1117;color:#c9d1d9;border:1px solid #30363d;border-radius:6px;padding:12px;font-family:Consolas,Courier New,monospace;font-size:0.9em;line-height:1.5;resize:vertical;"></textarea>'
            + '<div id="git-' + rid + '" class="git-banner" style="margin-top:8px">Checking git status...</div>'
            + '<div class="rule-edit-actions" style="margin-top:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">'
            + '<button class="edit-btn save" onclick="saveRule(\'' + rid + '\',\'' + fpEsc + '\')">Save</button>'
            + '<button class="edit-btn backup" onclick="backupRule(\'' + rid + '\',\'' + fpEsc + '\')">Backup</button>'
            + '<button class="edit-btn cancel" onclick="cancelEdit(\'' + rid + '\')">Cancel</button>'
            + '<span id="status-' + rid + '" class="edit-status"></span>'
            + '</div>';
        document.getElementById('ta-' + rid).value = data.content;
        // Stash original HTML on the element for cancel
        contentDiv.dataset.originalHtml = originalHtml;
        checkGitForRule(rid, filePath);
    }).catch(function(e) {
        contentDiv.dataset.editing = '';
        alert('Editor server not reachable. Run the report with: python main.py (not --no-open)');
    });
}
function cancelEdit(rid) {
    var contentDiv = document.getElementById('content-' + rid);
    if (!contentDiv) return;
    contentDiv.innerHTML = contentDiv.dataset.originalHtml || '';
    contentDiv.dataset.editing = '';
    contentDiv.dataset.originalHtml = '';
}
function checkGitForRule(rid, filePath) {
    var dirPath = filePath.replace(/\\/g, '/').replace(/\/[^/]+$/, '');
    editorApi('GET', '/api/git-status?dir=' + encodeURIComponent(dirPath)).then(function(data) {
        var el = document.getElementById('git-' + rid);
        if (!el) return;
        if (data.error) {
            el.className = 'git-banner';
            el.innerHTML = '!! Git check failed: ' + data.error;
            return;
        }
        if (!data.is_repo) {
            el.className = 'git-banner';
            el.innerHTML = '!! WARNING: No git repo tracking this folder. Changes cannot be restored. '
                + '<button class="edit-btn git-init" onclick="initGitRepo(\'' + rid + '\',\'' + dirPath.replace(/'/g, "\\'") + '\')">Initialize Git Repo</button>';
        } else if (!data.tracked) {
            el.className = 'git-banner';
            el.innerHTML = '!! WARNING: Git repo exists but files not tracked. Run: git add . && git commit -m "track rules" '
                + '<button class="edit-btn git-init" onclick="initGitRepo(\'' + rid + '\',\'' + dirPath.replace(/'/g, "\\'") + '\')">Track Files</button>';
        } else {
            el.className = 'git-banner ok';
            el.innerHTML = 'Git: tracked' + (data.dirty ? ' (uncommitted changes)' : ' (clean)');
        }
    });
}
function initGitRepo(rid, dirPath) {
    editorApi('POST', '/api/git-init', {dir: dirPath}).then(function(data) {
        if (data.error) { alert('Git init failed: ' + data.error); return; }
        var el = document.getElementById('git-' + rid);
        if (el) { el.className = 'git-banner ok'; el.innerHTML = 'Git: initialized and committed'; }
    });
}
function saveRule(rid, filePath) {
    var ta = document.getElementById('ta-' + rid);
    if (!ta) return;
    var status = document.getElementById('status-' + rid);
    editorApi('POST', '/api/save', {path: filePath, content: ta.value}).then(function(data) {
        if (data.error) {
            if (status) { status.className = 'edit-status err'; status.textContent = 'Save failed: ' + data.error; }
            return;
        }
        if (status) { status.className = 'edit-status ok'; status.textContent = 'Saved!'; }
        // Auto-commit
        editorApi('POST', '/api/git-commit', {path: filePath, message: 'Edit rule via claude-report'}).then(function(r) {
            if (r.ok && status) status.textContent = 'Saved + committed';
        });
        // After 2s, switch back to read-only view with updated content
        setTimeout(function() {
            var contentDiv = document.getElementById('content-' + rid);
            if (contentDiv && contentDiv.dataset.editing === 'true') {
                var body = content;
                var idx1 = content.indexOf('---');
                if (idx1 === 0) { var idx2 = content.indexOf('---', 3); if (idx2 > 0) body = content.substring(idx2 + 3).trim(); }
                var tmp = document.createElement('div'); tmp.textContent = body;
                contentDiv.innerHTML = tmp.innerHTML;
                contentDiv.dataset.editing = '';
            }
        }, 2000);
    }).catch(function(e) {
        if (status) { status.className = 'edit-status err'; status.textContent = 'Server error'; }
    });
}
function backupRule(rid, filePath) {
    var status = document.getElementById('status-' + rid);
    editorApi('POST', '/api/backup', {path: filePath}).then(function(data) {
        if (data.error) {
            if (status) { status.className = 'edit-status err'; status.textContent = 'Backup failed: ' + data.error; }
            return;
        }
        if (status) { status.className = 'edit-status ok'; status.textContent = 'Backed up to ' + data.backup_path.split(/[/\\]/).pop(); }
        setTimeout(function() { if (status) status.textContent = ''; }, 5000);
    }).catch(function(e) {
        if (status) { status.className = 'edit-status err'; status.textContent = 'Server error'; }
    });
}

function openShareModal() {
    document.getElementById('share-modal').classList.add('open');
    document.getElementById('share-pw1').value = '';
    document.getElementById('share-pw2').value = '';
    document.getElementById('share-encrypt').checked = false;
    togglePwFields();
    document.getElementById('share-error').style.display = 'none';
}
function toggleCat(el) {
    var cat = el.getAttribute('data-cat');
    var checks = document.querySelectorAll('#cat-' + cat + ' input[type=checkbox]');
    for (var i = 0; i < checks.length; i++) checks[i].checked = el.checked;
}
function togglePwFields() {
    var on = document.getElementById('share-encrypt').checked;
    var fields = document.getElementById('pw-fields');
    fields.style.opacity = on ? '1' : '0.4';
    fields.style.pointerEvents = on ? 'auto' : 'none';
    document.getElementById('share-pw1').disabled = !on;
    document.getElementById('share-pw2').disabled = !on;
    var btn = document.getElementById('share-export-btn');
    btn.textContent = on ? 'Export Encrypted ZIP' : 'Export ZIP Bundle';
}
function closeShareModal() {
    document.getElementById('share-modal').classList.remove('open');
    document.getElementById('share-pw1').value = '';
    document.getElementById('share-pw2').value = '';
}
function filterSecFlags() {
    var checks = document.querySelectorAll('.sev-filter');
    var allowed = {};
    for (var i = 0; i < checks.length; i++) {
        if (checks[i].checked) allowed[checks[i].getAttribute('data-sev')] = true;
    }
    var rows = document.querySelectorAll('.flag-row');
    for (var i = 0; i < rows.length; i++) {
        rows[i].style.display = allowed[rows[i].getAttribute('data-severity')] ? '' : 'none';
    }
}
function resolveWithClaude() {
    // Collect visible security flags into markdown instructions
    var rows = document.querySelectorAll('.flag-row');
    var items = [];
    for (var i = 0; i < rows.length; i++) {
        if (rows[i].style.display === 'none') continue;
        var sev = rows[i].getAttribute('data-severity');
        var type = rows[i].querySelector('.flag-type');
        var file = rows[i].querySelector('.flag-file');
        var msg = rows[i].querySelector('.flag-msg');
        items.push('- **[' + sev + ']** `' + (type ? type.textContent : '') + '` in `' + (file ? file.textContent : '') + '`: ' + (msg ? msg.textContent : ''));
    }
    if (items.length === 0) { alert('No flags selected.'); return; }
    var md = '# Security Flag Resolution\\n\\n';
    md += 'The following security flags were detected by claude-report. Review each one and resolve it.\\n';
    md += 'For each flag, explain what was found, whether it is a real issue, and fix it if needed.\\n';
    md += 'Do NOT modify this file -- make changes to the actual source files referenced below.\\n\\n';
    md += '## Flags (' + items.length + ')\\n\\n';
    md += items.join('\\n');
    md += '\\n\\n## Instructions\\n\\n';
    md += '1. Read each flag and the referenced file\\n';
    md += '2. Determine if it is a real security concern or false positive\\n';
    md += '3. If real: fix the issue in the source file\\n';
    md += '4. If false positive: add a brief comment explaining why\\n';
    md += '5. After resolving all flags, run `python ~/.claude/skills/claude-report/main.py --quick` to verify\\n';
    // Save as .md file
    var blob = new Blob([md.replace(/\\\\n/g, '\\n')], {type: 'text/markdown'});
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'resolve-security-flags.md';
    a.click();
    URL.revokeObjectURL(url);
    // Also generate a .bat file that runs claude with the md file
    var bat = '@echo off\\r\\necho Running Claude to resolve security flags...\\r\\n';
    bat += 'cd /d "%USERPROFILE%"\\r\\n';
    bat += 'claude -p "Read the file resolve-security-flags.md in my Downloads folder and follow its instructions to resolve all security flags listed." < nul\\r\\n';
    bat += 'pause\\r\\n';
    var batBlob = new Blob([bat.replace(/\\\\r\\\\n/g, '\\r\\n')], {type: 'application/bat'});
    var batUrl = URL.createObjectURL(batBlob);
    var b = document.createElement('a');
    b.href = batUrl;
    b.download = 'run-claude-resolve.bat';
    b.click();
    URL.revokeObjectURL(batUrl);
    alert('Downloaded resolve-security-flags.md and run-claude-resolve.bat.\\nMove both to your Downloads folder, then double-click the .bat file to launch Claude.');
}
function uint8ToBase64(u8) {
    var c = [], s = 8192;
    for (var i = 0; i < u8.length; i += s) c.push(String.fromCharCode.apply(null, u8.subarray(i, i + s)));
    return btoa(c.join(''));
}


function stripSecrets(bundle) {
    // Mandatory secret scanning -- runs on every export, not optional.
    // Patterns from detect-secrets, gitleaks, and trufflehog.
    var patterns = [
        { re: /AKIA[0-9A-Z]{16}/g, label: 'AWS Access Key' },
        { re: /(?<![A-Za-z0-9])[A-Za-z0-9\/+=]{40}(?![A-Za-z0-9\/+=])/g, label: 'AWS Secret Key (40-char base64)', contextRe: /(?:aws|secret|key)/i },
        { re: /gh[ps]_[A-Za-z0-9_]{36,}/g, label: 'GitHub Token' },
        { re: /gho_[A-Za-z0-9_]{36,}/g, label: 'GitHub OAuth Token' },
        { re: /github_pat_[A-Za-z0-9_]{22,}/g, label: 'GitHub PAT' },
        { re: /sk-[A-Za-z0-9]{20,}/g, label: 'API Secret Key' },
        { re: /sk-proj-[A-Za-z0-9\-_]{20,}/g, label: 'OpenAI Project Key' },
        { re: /xox[bpoas]-[A-Za-z0-9\-]{10,}/g, label: 'Slack Token' },
        { re: /-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----/g, label: 'Private Key' },
        { re: /eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}/g, label: 'JWT Token' },
        { re: /Bearer [A-Za-z0-9\-._~+\/]{20,}=*/g, label: 'Bearer Token' },
        { re: /(?:api[_-]?key|api[_-]?token|api[_-]?secret|access[_-]?token|auth[_-]?token|secret[_-]?key|private[_-]?key|client[_-]?secret)\s*[=:]\s*["']?([A-Za-z0-9\-._~+\/=]{12,})["']?/gi, label: 'Generic API Key/Token' },
        { re: /(?:password|passwd|pwd)\s*[=:]\s*["']?([^\s"']{8,})["']?/gi, label: 'Password' },
        { re: /(?:https?:\/\/)[^:]+:([^@\s]{8,})@/g, label: 'URL with credentials' },
    ];
    var redactCount = 0;
    var redactTypes = {};
    for (var cat in bundle) {
        if (!Array.isArray(bundle[cat])) continue;
        for (var i = 0; i < bundle[cat].length; i++) {
            var c = bundle[cat][i].content;
            for (var p = 0; p < patterns.length; p++) {
                var pat = patterns[p];
                pat.re.lastIndex = 0;
                var matches = c.match(pat.re);
                if (matches) {
                    // Skip context-dependent patterns unless context matches
                    if (pat.contextRe) {
                        var hasContext = false;
                        for (var m = 0; m < matches.length; m++) {
                            var idx = c.indexOf(matches[m]);
                            var ctx = c.substring(Math.max(0, idx - 80), idx + matches[m].length + 20);
                            if (pat.contextRe.test(ctx)) { hasContext = true; break; }
                        }
                        if (!hasContext) continue;
                    }
                    for (var m = 0; m < matches.length; m++) {
                        // Don't redact credential: references (these are keyring pointers, not secrets)
                        if (matches[m].indexOf('credential:') === 0) continue;
                        c = c.split(matches[m]).join('[REDACTED:' + pat.label + ']');
                        redactCount++;
                        redactTypes[pat.label] = (redactTypes[pat.label] || 0) + 1;
                    }
                }
            }
            bundle[cat][i].content = c;
            bundle[cat][i].size = c.length;
        }
    }
    return { bundle: bundle, count: redactCount, types: redactTypes };
}

function anonymizeBundle(bundle) {
    // Extract username from known path patterns
    var userRe = /[\/\\](?:Users|home)[\/\\]([^\/\\]+)/;
    var username = null;
    for (var cat in bundle) {
        if (!Array.isArray(bundle[cat])) continue;
        for (var i = 0; i < bundle[cat].length; i++) {
            var m = bundle[cat][i].content.match(userRe);
            if (m && m[1] !== 'Administrator' && m[1] !== 'root') { username = m[1]; break; }
        }
        if (username) break;
    }
    // Collect all IPs
    var ipRe = /\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b/g;
    var ipMap = {};
    var ipCounter = 0;
    for (var cat in bundle) {
        if (!Array.isArray(bundle[cat])) continue;
        for (var i = 0; i < bundle[cat].length; i++) {
            var matches = bundle[cat][i].content.match(ipRe);
            if (matches) {
                for (var j = 0; j < matches.length; j++) {
                    var ip = matches[j];
                    // Skip localhost and common non-routable
                    if (ip === '127.0.0.1' || ip === '0.0.0.0' || ip.startsWith('255.')) continue;
                    if (!(ip in ipMap)) { ipCounter++; ipMap[ip] = ipCounter; }
                }
            }
        }
    }
    // Apply redactions
    for (var cat in bundle) {
        if (!Array.isArray(bundle[cat])) continue;
        for (var i = 0; i < bundle[cat].length; i++) {
            var c = bundle[cat][i].content;
            // Redact username
            if (username) {
                c = c.split(username).join('[user]');
                bundle[cat][i].path = bundle[cat][i].path.split(username).join('[user]');
            }
            // Redact IPs with consistent numbering
            for (var ip in ipMap) {
                c = c.split(ip).join('[ip-' + ipMap[ip] + ']');
            }
            bundle[cat][i].content = c;
            bundle[cat][i].size = c.length;
        }
    }
    return bundle;
}
async function loadJSZip() {
    if (window.JSZip) return;
    return new Promise(function(resolve, reject) {
        var s = document.createElement('script');
        s.src = 'https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js';
        s.onload = resolve;
        s.onerror = function() { reject(new Error('Failed to load JSZip. Check your internet connection.')); };
        document.head.appendChild(s);
    });
}
function generateExportHtml(bundle, ts) {
    var h = [];
    h.push('<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">');
    h.push('<meta name="viewport" content="width=device-width, initial-scale=1.0">');
    h.push('<title>Claude Config Export</title>');
    h.push('<style>');
    h.push('*{margin:0;padding:0;box-sizing:border-box;}');
    h.push('body{background:#0d1117;color:#e6edf3;font-family:"Segoe UI",system-ui,-apple-system,sans-serif;padding:24px;min-height:100vh;font-size:16px;}');
    h.push('h1{text-align:center;color:#58a6ff;font-size:2em;margin-bottom:8px;}');
    h.push('.subtitle{text-align:center;color:#8b949e;margin-bottom:32px;font-size:1.1em;}');
    h.push('.stats{max-width:1100px;margin:0 auto 24px;display:flex;gap:14px;flex-wrap:wrap;justify-content:center;}');
    h.push('.stat{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:10px 18px;text-align:center;}');
    h.push('.stat-num{font-size:1.7em;font-weight:700;color:#58a6ff;}');
    h.push('.stat-label{font-size:0.85em;color:#8b949e;}');
    h.push('.note{max-width:1100px;margin:0 auto 18px;text-align:center;color:#6e7681;font-size:0.85em;}');
    h.push('.section{max-width:1100px;margin:0 auto 24px;}');
    h.push('.sec-hdr{color:#58a6ff;font-size:1.3em;font-weight:700;cursor:pointer;padding:16px 22px;background:#161b22;border:2px solid #30363d;border-radius:10px;display:flex;align-items:center;gap:14px;user-select:none;transition:all 0.2s;}');
    h.push('.sec-hdr:hover{border-color:#58a6ff;background:#1a2332;}');
    h.push('.sec-hdr .arrow{font-family:monospace;min-width:14px;transition:transform 0.2s;}');
    h.push('.sec-hdr.open .arrow{transform:rotate(90deg);}');
    h.push('.sec-body{display:none;border:1px solid #30363d;border-top:0;border-radius:0 0 10px 10px;background:#161b22;}');
    h.push('.sec-body.open{display:block;}');
    h.push('.file-card{border-bottom:1px solid #21262d;padding:16px 22px;}');
    h.push('.file-card:last-child{border-bottom:none;}');
    h.push('.file-name{color:#d2a8ff;font-family:"Consolas",monospace;font-size:0.95em;margin-bottom:4px;display:flex;align-items:center;gap:10px;}');
    h.push('.file-size{color:#6e7681;font-size:0.82em;}');
    h.push('.file-content{background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:12px 16px;font-family:"Consolas","Courier New",monospace;font-size:0.85em;line-height:1.5;color:#c9d1d9;white-space:pre-wrap;word-break:break-word;max-height:400px;overflow-y:auto;margin-top:6px;}');
    h.push('.legend{max-width:1100px;margin:32px auto;background:#161b22;border:1px solid #30363d;border-radius:10px;padding:18px 22px;text-align:center;color:#6e7681;font-size:0.85em;}');
    h.push('</style></head><body>');
    h.push('<h1>[=] Claude Config Export</h1>');
    var catNames = {configs:"Configs", hooks:"Hook Scripts", rules:"Rules", skills:"Skills", mcp_servers:"MCP Servers"};
    var catOrder = ["configs","hooks","rules","skills","mcp_servers"];
    var totalFiles = 0;
    for (var ci = 0; ci < catOrder.length; ci++) { totalFiles += bundle[catOrder[ci]] ? bundle[catOrder[ci]].length : 0; }
    h.push('<div class="subtitle">Exported: ' + ts + ' | ' + totalFiles + ' files</div>');
    h.push('<div class="stats">');
    for (var ci = 0; ci < catOrder.length; ci++) {
        var cat = catOrder[ci];
        var n = bundle[cat] ? bundle[cat].length : 0;
        if (n > 0) h.push('<div class="stat"><div class="stat-num">' + n + '</div><div class="stat-label">' + catNames[cat] + '</div></div>');
    }
    h.push('</div>');
    h.push('<div class="note">Secrets redacted. Source files also included as raw files in this ZIP.</div>');
    h.push('<script>function togSec(el){el.classList.toggle("open");el.nextElementSibling.classList.toggle("open");}<\/script>');
    for (var ci = 0; ci < catOrder.length; ci++) {
        var cat = catOrder[ci];
        if (!bundle[cat] || bundle[cat].length === 0) continue;
        h.push('<div class="section">');
        h.push('<div class="sec-hdr" onclick="togSec(this)"><span class="arrow">&gt;</span>' + catNames[cat] + ' (' + bundle[cat].length + ')</div>');
        h.push('<div class="sec-body">');
        for (var i = 0; i < bundle[cat].length; i++) {
            var f = bundle[cat][i];
            var sz = f.size < 1024 ? f.size + 'b' : Math.round(f.size/1024) + 'kb';
            var esc = f.content.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
            var truncated = esc.length > 8000;
            var shown = truncated ? esc.substring(0, 8000) + '\n\n... truncated (' + f.size + ' bytes total, see full file in ZIP) ...' : esc;
            h.push('<div class="file-card">');
            h.push('<div class="file-name">' + f.path + ' <span class="file-size">' + sz + '</span></div>');
            h.push('<pre class="file-content">' + shown + '</pre>');
            h.push('</div>');
        }
        h.push('</div></div>');
    }
    h.push('<div class="legend">Exported from Claude Code Inventory Report. Secrets (API keys, tokens, passwords, private keys) automatically redacted.</div>');
    h.push('</body></html>');
    return h.join('\n');
}
async function exportBundle() {
    var doEncrypt = document.getElementById('share-encrypt').checked;
    var pw1 = document.getElementById('share-pw1').value;
    var pw2 = document.getElementById('share-pw2').value;
    var err = document.getElementById('share-error');
    if (doEncrypt) {
        if (!pw1 || pw1.length < 4) { err.textContent = 'Password must be at least 4 characters.'; err.style.display = 'block'; return; }
        if (pw1 !== pw2) { err.textContent = 'Passwords do not match.'; err.style.display = 'block'; return; }
    }
    err.style.display = 'none';
    var btn = document.getElementById('share-export-btn');
    btn.disabled = true; btn.textContent = 'Loading JSZip...';
    try {
        await loadJSZip();
        btn.textContent = 'Building ZIP...';
        var fullBundle = JSON.parse(document.getElementById('bundle-data').textContent);
        // Build filtered bundle from checked items
        var bundle = {};
        var cats = ['configs', 'hooks', 'rules', 'skills', 'mcp_servers'];
        for (var ci = 0; ci < cats.length; ci++) {
            var cat = cats[ci];
            if (!fullBundle[cat]) continue;
            var checks = document.querySelectorAll('#cat-' + cat + ' input[type=checkbox]');
            var items = [];
            for (var i = 0; i < checks.length; i++) {
                if (checks[i].checked) items.push(fullBundle[cat][i]);
            }
            if (items.length > 0) bundle[cat] = items;
        }
        // Anonymize if checked
        var doAnon = document.getElementById('share-anon').checked;
        if (doAnon) bundle = anonymizeBundle(bundle);
        // Always strip secrets (mandatory)
        var secResult = stripSecrets(bundle);
        bundle = secResult.bundle;
        if (secResult.count > 0) {
            var summary = 'Redacted ' + secResult.count + ' secret(s): ';
            var parts = [];
            for (var t in secResult.types) parts.push(secResult.types[t] + 'x ' + t);
            summary += parts.join(', ');
            console.log('[share] ' + summary);
        }
        var ts = new Date().toISOString().slice(0,19).replace('T',' ');
        // Generate export HTML from filtered data
        var reportHtml = generateExportHtml(bundle, ts);
        // Build ZIP: report.html + raw source files in folders
        var zip = new JSZip();
        zip.file('report.html', reportHtml);
        var folderMap = {configs:'configs', hooks:'hooks', rules:'rules', skills:'skills', mcp_servers:'mcp'};
        for (var ci = 0; ci < cats.length; ci++) {
            var cat = cats[ci];
            if (!bundle[cat]) continue;
            var folder = zip.folder(folderMap[cat]);
            for (var i = 0; i < bundle[cat].length; i++) {
                var f = bundle[cat][i];
                folder.file(f.path.replace(/\\/g, '/'), f.content);
            }
        }
        btn.textContent = 'Compressing...';
        var zipBlob = await zip.generateAsync({type: 'blob'});
        if (doEncrypt) {
            btn.textContent = 'Encrypting...';
            var zipBytes = new Uint8Array(await zipBlob.arrayBuffer());
            var enc = new TextEncoder();
            var salt = crypto.getRandomValues(new Uint8Array(16));
            var iv = crypto.getRandomValues(new Uint8Array(12));
            var km = await crypto.subtle.importKey('raw', enc.encode(pw1), 'PBKDF2', false, ['deriveKey']);
            var key = await crypto.subtle.deriveKey({name:'PBKDF2',salt:salt,iterations:100000,hash:'SHA-256'}, km, {name:'AES-GCM',length:256}, false, ['encrypt']);
            var ct = new Uint8Array(await crypto.subtle.encrypt({name:'AES-GCM',iv:iv}, key, zipBytes));
            var combined = new Uint8Array(28 + ct.length);
            combined.set(salt, 0); combined.set(iv, 16); combined.set(ct, 28);
            var b64 = uint8ToBase64(combined);
            var fc = 0;
            for (var cat in bundle) { if (Array.isArray(bundle[cat])) fc += bundle[cat].length; }
            var szKb = Math.round(zipBytes.length / 1024);
            var tpl = atob(document.getElementById('decrypt-tpl-b64').textContent.trim());
            tpl = tpl.replace('__ENCRYPTED_DATA__', b64).replace('__FILES_COUNT__', String(fc)).replace('__SIZE_KB__', String(szKb)).replace('__GENERATED_TS__', ts);
            var blob = new Blob([tpl], {type:'text/html;charset=utf-8'});
            var a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'claude-config-bundle.html';
            a.click();
            URL.revokeObjectURL(a.href);
        } else {
            var a = document.createElement('a');
            a.href = URL.createObjectURL(zipBlob);
            a.download = 'claude-config-bundle.zip';
            a.click();
            URL.revokeObjectURL(a.href);
        }
        closeShareModal();
    } catch(e) {
        err.textContent = 'Export failed: ' + e.message; err.style.display = 'block';
    }
    document.getElementById('share-pw1').value = '';
    document.getElementById('share-pw2').value = '';
    btn.disabled = false; btn.textContent = doEncrypt ? 'Export Encrypted ZIP' : 'Export ZIP Bundle';
}
"""

    # Canonical event order for the timeline
    EVENT_ORDER = ['SessionStart', 'UserPromptSubmit', 'PreToolUse', 'PostToolUse', 'Stop', 'SessionEnd']

    # Event type -> badge
    EVENT_BADGES = {
        'SessionStart': ('INJECT', 'badge-inject'),
        'UserPromptSubmit': ('INJECT', 'badge-inject'),
        'PreToolUse': ('GATE', 'badge-gate'),
        'PostToolUse': ('CHECK', 'badge-check'),
        'Stop': ('BLOCK', 'badge-block'),
        'SessionEnd': ('ASYNC', 'badge-async'),
    }
    DECRYPT_TEMPLATE = r"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude Config Bundle</title>
<style>
*{margin:0;padding:0;box-sizing:border-box;}
body{background:#0d1117;color:#e6edf3;font-family:"Segoe UI",system-ui;display:flex;justify-content:center;align-items:center;min-height:100vh;}
.box{background:#161b22;border:2px solid #30363d;border-radius:12px;padding:32px;max-width:440px;width:90%;text-align:center;}
h1{color:#58a6ff;font-size:1.5em;margin-bottom:8px;}
.sub{color:#8b949e;margin-bottom:24px;font-size:0.9em;}
input{width:100%;padding:10px 14px;background:#0d1117;border:1px solid #30363d;border-radius:6px;color:#e6edf3;font-size:1em;margin-bottom:16px;font-family:"Segoe UI",system-ui;box-sizing:border-box;}
input:focus{outline:none;border-color:#58a6ff;}
button{width:100%;padding:10px;background:#238636;border:none;border-radius:6px;color:#fff;font-size:1em;font-weight:600;cursor:pointer;font-family:"Segoe UI",system-ui;}
button:hover{background:#2ea043;}button:disabled{background:#21262d;color:#8b949e;cursor:not-allowed;}
.err{color:#f85149;font-size:0.9em;margin-top:12px;display:none;}
.ok{color:#3fb950;font-size:0.9em;margin-top:12px;display:none;}
.info{color:#6e7681;font-size:0.82em;margin-top:16px;}
</style></head><body>
<div class="box">
<h1>[=] Claude Config Bundle</h1>
<div class="sub">__GENERATED_TS__ -- __FILES_COUNT__ files (__SIZE_KB__ KB)</div>
<input type="password" id="pw" placeholder="Enter password to decrypt" autofocus>
<button id="dbtn" onclick="decrypt()">Decrypt and Download ZIP</button>
<div class="err" id="err">Wrong password or corrupted data.</div>
<div class="ok" id="ok">Decrypted! ZIP downloading...</div>
<div class="info">AES-256-GCM encrypted. Contains report.html + source files.</div>
</div>
<script id="enc-data" type="text/plain">__ENCRYPTED_DATA__<\/script>
<script>
function b64u8(b){var r=atob(b),u=new Uint8Array(r.length);for(var i=0;i<r.length;i++)u[i]=r.charCodeAt(i);return u;}
async function decrypt(){
var pw=document.getElementById('pw').value;if(!pw)return;
document.getElementById('err').style.display='none';document.getElementById('ok').style.display='none';
var btn=document.getElementById('dbtn');btn.disabled=true;btn.textContent='Decrypting...';
try{
var raw=b64u8(document.getElementById('enc-data').textContent.trim());
var salt=raw.slice(0,16),iv=raw.slice(16,28),ct=raw.slice(28);
var enc=new TextEncoder();
var km=await crypto.subtle.importKey('raw',enc.encode(pw),'PBKDF2',false,['deriveKey']);
var key=await crypto.subtle.deriveKey({name:'PBKDF2',salt:salt,iterations:100000,hash:'SHA-256'},km,{name:'AES-GCM',length:256},false,['decrypt']);
var dec=await crypto.subtle.decrypt({name:'AES-GCM',iv:iv},key,ct);
var blob=new Blob([dec],{type:'application/zip'});
var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='claude-config-bundle.zip';a.click();
URL.revokeObjectURL(a.href);document.getElementById('ok').style.display='block';document.getElementById('pw').value='';
}catch(e){document.getElementById('err').style.display='block';}
btn.disabled=false;btn.textContent='Decrypt and Download ZIP';
}
document.getElementById('pw').addEventListener('keypress',function(e){if(e.key==='Enter')decrypt();});
<\/script></body></html>"""


    def generate(self, mcp_data: Dict, skill_data: Dict, hook_data: Dict, output_path: Path = None, rule_data: Dict = None, editor_port: int = 0) -> str:
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        servers = mcp_data.get("servers", {})
        mcp_total = sum(len(v) for v in servers.values())
        skills = skill_data.get("skills", {})
        skill_total = sum(len(v) for v in skills.values())
        hooks = hook_data.get("hooks", {})
        active_hooks = hooks.get("active", {})
        active_count = sum(len(v) for v in active_hooks.values())
        all_flags = (mcp_data.get("security_flags", []) +
                     skill_data.get("security_flags", []) +
                     hook_data.get("security_flags", []))
        warn_count = len([f for f in all_flags if f.get("severity") == "warning"])

        # Use RuleScanner data if provided, otherwise fall back to old loader
        if rule_data:
            rules = rule_data.get('rules_by_event', {})
            self._firing_stats = rule_data.get('firing_stats', {})
            self._mcp_rules = rule_data.get('mcp_rules', {})
            self._misplaced_rules = rule_data.get('misplaced_rules', [])
        else:
            rules = self._load_rules()
            self._firing_stats = {}
            self._mcp_rules = {}
            self._misplaced_rules = []
        self._editor_port = editor_port
        rule_count = sum(len(v) for v in rules.values())
        mcp_rule_count = sum(len(v) for v in self._mcp_rules.values())

        parts = []
        parts.append('<!DOCTYPE html>\n<html lang="en">\n<head>')
        parts.append('<meta charset="UTF-8">')
        parts.append('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
        parts.append('<title>Claude Code Inventory Report</title>')
        parts.append(f'<style>{self.CSS}</style>')
        parts.append('</head>\n<body>')
        parts.append(f'<script>{self.JS}</script>')
        if self._editor_port:
            parts.append(f'<script>EDITOR_PORT = {self._editor_port};</script>')
        parts.append('<h1>Claude Code Inventory Report</h1>')
        parts.append(f'<div class="subtitle">MCP Servers / Skills / Hooks + Rules / Security</div>')
        parts.append(f'<div class="generated">Generated: {ts}</div>')

        # Stats bar
        parts.append('<div class="stats">')
        parts.append(f'<div class="stat"><div class="stat-num">{mcp_total}</div><div class="stat-label">MCP Servers</div></div>')
        parts.append(f'<div class="stat"><div class="stat-num green">{skill_total}</div><div class="stat-label">Skills</div></div>')
        parts.append(f'<div class="stat"><div class="stat-num purple">{active_count}</div><div class="stat-label">Hooks</div></div>')
        parts.append(f'<div class="stat"><div class="stat-num amber">{rule_count + mcp_rule_count}</div><div class="stat-label">Rules</div></div>')
        parts.append(f'<div class="stat"><div class="stat-num{"" if warn_count == 0 else " red"}">{warn_count}</div><div class="stat-label">Warnings</div></div>')
        parts.append('</div>')

        # Collect bundle files for share feature
        bundle = self._collect_bundle_files(mcp_data, skill_data, hook_data, rules)
        bundle_json = json_mod.dumps(bundle, ensure_ascii=False)
        # Count files for modal stats
        b_configs = len(bundle.get('configs', []))
        b_hooks = len(bundle.get('hooks', []))
        b_rules = len(bundle.get('rules', []))
        b_skills = len(bundle.get('skills', []))
        b_mcp = len(bundle.get('mcp_servers', []))
        b_total_size = sum(f.get('size', 0) for cat in bundle.values() for f in cat)

        # Share button
        parts.append('<div class="share-bar">')
        parts.append('<button class="share-btn" onclick="openShareModal()">Share / Export</button>')
        parts.append('</div>')

        # MCP section
        parts.append(self._section_mcp(servers, mcp_total))

        # Skills section
        parts.append(self._section_skills(skills, skill_total))

        # Hooks section (wraps the event flow timeline)
        parts.append(self._section_hooks(active_hooks, active_count, rules, rule_count))

        # Security flags
        parts.append(self._section_security(all_flags))

        # Legend
        parts.append(self._section_legend())

        # Hidden data for share feature
        parts.append(f'<script id="bundle-data" type="application/json">{bundle_json}</script>')
        tpl_b64 = base64.b64encode(self.DECRYPT_TEMPLATE.replace('<\\/script>', '</script>').encode('utf-8')).decode('ascii')
        parts.append(f'<script id="decrypt-tpl-b64" type="text/plain">{tpl_b64}</script>')

        # Share modal
        # Build per-item checkbox lists from bundle data
        def _item_checks(cat, items):
            rows = []
            for idx, f in enumerate(items):
                name = f.get('path', f'item-{idx}')
                sz = f.get('size', 0)
                sz_str = f'{sz}b' if sz < 1024 else f'{sz//1024}kb' if sz < 1048576 else f'{sz//1048576}mb'
                warn = ' <span style="color:#d29922;font-weight:bold" title="Large file (>2MB)">[LARGE]</span>' if sz > 2097152 else ''
                rows.append(f'<label class="item-check"><input type="checkbox" checked data-cat="{cat}" data-idx="{idx}"> <span class="item-name">{name}</span> <span class="item-size">{sz_str}{warn}</span></label>')
            return '\n'.join(rows)

        configs_checks = _item_checks('configs', bundle.get('configs', []))
        hooks_checks = _item_checks('hooks', bundle.get('hooks', []))
        rules_checks = _item_checks('rules', bundle.get('rules', []))
        skills_checks = _item_checks('skills', bundle.get('skills', []))
        mcp_checks = _item_checks('mcp_servers', bundle.get('mcp_servers', []))

        parts.append(f'''<div class="modal-overlay" id="share-modal" onclick="if(event.target===this)closeShareModal()">
<div class="modal">
<h2>Share Config Bundle</h2>
<div class="modal-sub">Select items to export. Secrets are ALWAYS redacted.</div>
<div class="export-cats">
<div class="export-cat">
<label class="cat-header"><input type="checkbox" checked class="cat-toggle" data-cat="configs" onchange="toggleCat(this)"> Configs ({b_configs})</label>
<div class="cat-items" id="cat-configs">{configs_checks}</div>
</div>
<div class="export-cat">
<label class="cat-header"><input type="checkbox" checked class="cat-toggle" data-cat="hooks" onchange="toggleCat(this)"> Hook Scripts ({b_hooks})</label>
<div class="cat-items" id="cat-hooks">{hooks_checks}</div>
</div>
<div class="export-cat">
<label class="cat-header"><input type="checkbox" checked class="cat-toggle" data-cat="rules" onchange="toggleCat(this)"> Rules ({b_rules})</label>
<div class="cat-items" id="cat-rules">{rules_checks}</div>
</div>
<div class="export-cat">
<label class="cat-header"><input type="checkbox" checked class="cat-toggle" data-cat="skills" onchange="toggleCat(this)"> Skills ({b_skills})</label>
<div class="cat-items" id="cat-skills">{skills_checks}</div>
</div>
<div class="export-cat">
<label class="cat-header"><input type="checkbox" class="cat-toggle" data-cat="mcp_servers" onchange="toggleCat(this)"> MCP Servers ({b_mcp})</label>
<div class="cat-items" id="cat-mcp_servers">{mcp_checks}</div>
</div>
</div>
<label class="check-row" title="Replace usernames and IP addresses with placeholders"><input type="checkbox" id="share-anon"> Anonymize (redact usernames and IP addresses)</label>
<label class="check-row pw-toggle"><input type="checkbox" id="share-encrypt" onchange="togglePwFields()"> Encrypt with password</label>
<div class="pw-fields" id="pw-fields" style="opacity:0.4;pointer-events:none">
<input type="password" id="share-pw1" placeholder="Enter password" autocomplete="off" disabled>
<input type="password" id="share-pw2" placeholder="Confirm password" autocomplete="off" disabled>
</div>
<div class="btn-row">
<button class="btn-cancel" onclick="closeShareModal()">Cancel</button>
<button class="btn-export" id="share-export-btn" onclick="exportBundle()">Export ZIP Bundle</button>
</div>
<div class="modal-error" id="share-error"></div>
<div class="modal-info">Secrets (API keys, tokens, passwords, private keys) are ALWAYS redacted before export.</div>
</div></div>''')

        parts.append('</body>\n</html>')
        content = '\n'.join(parts)

        if output_path:
            output_path.write_text(content, encoding='utf-8')
        return content

    def _e(self, text: str) -> str:
        return html.escape(str(text) if text else '-')

    def _hook_name(self, h: Dict) -> str:
        """Extract readable hook name from command path."""
        cmd = h.get('command', '') or ''
        name = cmd.split('/')[-1].split('\\')[-1]
        name = name.strip('"').strip("'")
        if name.endswith('.js'):
            name = name[:-3]
        elif name.endswith('.sh'):
            name = name[:-3]
        return name or cmd[:40]

    def _load_rules(self) -> Dict[str, List[Dict]]:
        """Load rules from ~/.claude/rule-book/ only. rules/ is wrong location."""
        home = Path.home()
        rule_book_dir = home / '.claude' / 'rule-book'
        result = {}
        for event_dir in ['UserPromptSubmit', 'Stop', 'PreToolUse', 'PostToolUse']:
            rules_list = []
            edir = rule_book_dir / event_dir
            if not edir.is_dir():
                continue
            for f in sorted(edir.iterdir()):
                if f.suffix != '.md':
                    continue
                try:
                    content = f.read_text(encoding='utf-8')
                    meta = self._parse_frontmatter(content)
                    if meta:
                        meta['_file'] = f.name
                        meta['_path'] = str(f)
                        meta['_event'] = event_dir
                        meta['_source'] = 'rule-book'
                        if 'id' not in meta:
                            meta['id'] = f.stem
                        rules_list.append(meta)
                except Exception:
                    pass
            if rules_list:
                rules_list.sort(key=lambda r: int(r.get('priority', '10') or '10'))
                result[event_dir] = rules_list
        return result

    def _parse_frontmatter(self, content: str) -> dict:
        """Parse YAML frontmatter from markdown."""
        if not content.startswith('---'):
            return {}
        end = content.find('---', 3)
        if end == -1:
            return {}
        yaml_str = content[3:end].strip()
        meta = {}
        current_list_key = None
        for line in yaml_str.split('\n'):
            trimmed = line.strip()
            # Handle multi-line YAML list items
            if trimmed.startswith('- ') and current_list_key:
                if not isinstance(meta.get(current_list_key), list):
                    meta[current_list_key] = []
                meta[current_list_key].append(trimmed[2:].strip())
                continue
            current_list_key = None
            col = line.find(':')
            if col == -1:
                continue
            key = line[:col].strip()
            val = line[col+1:].strip()
            if val.startswith('[') and val.endswith(']'):
                meta[key] = [s.strip() for s in val[1:-1].split(',')]
            elif val == '':
                current_list_key = key
            else:
                meta[key] = val
        meta['body'] = content[end+3:].strip()
        return meta

    def _section_mcp(self, servers: Dict, total: int) -> str:
        lines = []
        lines.append('<div class="section">')
        lines.append(f'<div class="section-header" id="h-mcp" onclick="toggle(\'mcp\')">'
                     f'<span class="arrow">></span><span class="section-title">MCP Servers</span>'
                     f'<span class="section-count">{total}</span></div>')
        lines.append(f'<div class="section-body" id="b-mcp">')
        # Group ALL servers by routed field (set by scanner from .mcp.json servers list)
        managed = []
        standalone = []
        for status_key in ['running', 'stopped', 'disabled', 'unregistered']:
            for s in servers.get(status_key, []):
                actual_status = status_key
                if s.get('routed'):
                    managed.append((actual_status, s))
                else:
                    standalone.append((actual_status, s))
        # Managed servers (routed through mcp-manager)
        if managed:
            lines.append(f'<div class="group-label" style="margin-bottom:4px">MANAGED (routed via mcp-manager) ({len(managed)})</div>')
            for status, s in managed:
                lines.append(self._mcp_item_row(status, s))
        # Standalone servers (direct config, not routed)
        if standalone:
            lines.append(f'<div class="group-label" style="margin-top:12px;margin-bottom:4px">STANDALONE / DIRECT ({len(standalone)})</div>')
            for status, s in standalone:
                lines.append(self._mcp_item_row(status, s))
        if not managed and not standalone:
            lines.append('<div class="item-row" style="color:#6e7681">No MCP servers detected</div>')
        lines.append('</div></div>')
        return '\n'.join(lines)

    def _mcp_item_row(self, status: str, s: Dict) -> str:
        """Render a single MCP server row with status badge, description, source, and file link."""
        name = self._e(s.get('name', '?'))
        desc = self._e((s.get('description', '') or '')[:80])
        source = self._e(s.get('source', ''))
        badge_class = f'badge-{status}'
        sp = s.get('script_path', '') or s.get('path', '')
        file_link = ''
        if sp:
            sp_resolved = str(sp).replace('~', str(Path.home()))
            file_url = 'file:///' + sp_resolved.replace('\\', '/')
            sp_win = sp_resolved.replace('/', '\\')
            file_link = (f'<a class="file-btn" href="{self._e(file_url)}" target="_blank" '
                        f'style="margin-left:auto;white-space:nowrap">Open</a>'
                        f'<button class="file-btn" onclick="copyPath(this, \'{self._e(sp_win)}\')" '
                        f'style="white-space:nowrap">Copy Path</button>')
        return (f'<div class="item-row"><span class="badge {badge_class}">{status}</span>'
                f'<span class="item-name">{name}</span><span class="item-desc">{desc}</span>'
                f'<span class="item-source">{source}</span>{file_link}</div>')

    def _section_skills(self, skills: Dict, total: int) -> str:
        lines = []
        lines.append('<div class="section">')
        lines.append(f'<div class="section-header" id="h-skills" onclick="toggle(\'skills\')">'
                     f'<span class="arrow">></span><span class="section-title">Skills</span>'
                     f'<span class="section-count">{total}</span></div>')
        lines.append(f'<div class="section-body" id="b-skills">')
        source_labels = {'user': ('USER-LEVEL', 'badge-user'), 'project': ('PROJECT-LEVEL', 'badge-project'),
                         'marketplace': ('MARKETPLACE', 'badge-marketplace'), 'unregistered': ('UNREGISTERED', 'badge-unregistered')}
        for source in ['user', 'project', 'marketplace', 'unregistered']:
            items = skills.get(source, [])
            if not items:
                continue
            label, badge = source_labels.get(source, (source.upper(), 'badge-disabled'))
            if source == 'marketplace':
                # Sub-group by marketplace name
                by_mp = {}
                for s in items:
                    mp = s.get('marketplace', 'unknown')
                    by_mp.setdefault(mp, []).append(s)
                for mp_name, mp_items in sorted(by_mp.items()):
                    lines.append(f'<div class="group-label">MARKETPLACE: {self._e(mp_name)} ({len(mp_items)})</div>')
                    for s in mp_items:
                        lines.append(self._skill_item_row(s, badge, source))
            else:
                lines.append(f'<div class="group-label">{label} ({len(items)})</div>')
                for s in items:
                    lines.append(self._skill_item_row(s, badge, source))
        lines.append('</div></div>')
        return '\n'.join(lines)

    def _skill_item_row(self, s: Dict, badge: str, source: str) -> str:
        """Render a single skill row with name, title, registry status, and file link."""
        name = self._e(s.get('name', '?'))
        title = self._e((s.get('title', '') or '')[:50])
        # Registry badge with clear labels
        if s.get('registered'):
            reg_html = '<span class="badge badge-registered" title="In skill-registry.json">registered</span>'
        else:
            reg_html = '<span class="badge" title="Not in skill-registry.json" style="color:#6e7681;font-size:0.75em">unregistered</span>'
        # Version badge for marketplace skills
        version_html = ''
        if s.get('version'):
            version_html = f'<span style="color:#6e7681;font-size:0.8em;font-family:monospace">v{self._e(s["version"])}</span>'
        # File link
        sp = s.get('path', '')
        file_link = ''
        if sp:
            sp_resolved = str(sp).replace('~', str(Path.home()))
            file_url = 'file:///' + sp_resolved.replace('\\', '/')
            sp_win = sp_resolved.replace('/', '\\')
            file_link = (f'<a class="file-btn" href="{self._e(file_url)}" target="_blank" '
                        f'style="margin-left:auto;white-space:nowrap">Open</a>'
                        f'<button class="file-btn" onclick="copyPath(this, \'{self._e(sp_win)}\')" '
                        f'style="white-space:nowrap">Copy Path</button>')
        return (f'<div class="item-row"><span class="badge {badge}">{source[:4]}</span>'
                f'<span class="item-name">{name}</span><span class="item-desc">{title}</span>'
                f'{version_html} {reg_html}{file_link}</div>')

    def _section_hooks(self, active_hooks: Dict, hook_count: int, rules: Dict, rule_count: int) -> str:
        """Hooks section -- hierarchical expand/collapse. Controls appear inside each expanded level."""
        lines = []
        lines.append('<div class="section">')
        lines.append(f'<div class="section-header" id="h-hooks" onclick="toggle(\'hooks\')">'
                     f'<span class="arrow">></span><span class="section-title">Hooks + Rules</span>'
                     f'<span class="section-count">{hook_count} hooks + {rule_count} rules</span></div>')
        lines.append(f'<div class="section-body" id="b-hooks">')

        # Section-level: Expand All / Collapse All (opens everything)
        lines.append('<div class="level-controls">')
        lines.append('<button class="expand-btn" onclick="event.stopPropagation(); expandAll(\'b-hooks\')">Expand All</button>')
        lines.append('<button class="expand-btn" onclick="event.stopPropagation(); collapseAll(\'b-hooks\')">Collapse All</button>')
        lines.append('</div>')

        lines.append('<div class="flow">')
        hook_id = 0

        for idx, evt in enumerate(self.EVENT_ORDER):
            hooks_list = active_hooks.get(evt, [])
            event_rules = rules.get(evt, [])
            total_items = len(hooks_list) + len(event_rules)
            if total_items == 0:
                continue

            badge_text, badge_class = self.EVENT_BADGES.get(evt, ('', ''))
            eid = f'ev{idx}'

            # Find sm-* hook index (rules nest under it)
            sm_hook_idx = None
            if event_rules:
                for hi, h in enumerate(hooks_list):
                    if self._hook_name(h).startswith('sm-'):
                        sm_hook_idx = hi
                        break

            lines.append('<div class="event-node">')
            lines.append(f'<div class="event-header" id="h-{eid}" onclick="toggle(\'{eid}\')">')
            lines.append(f'<span class="arrow">></span>')
            lines.append(f'<span class="event-number">{idx+1}</span>')
            lines.append(f'<span class="event-name">{self._e(evt)}</span>')
            if badge_text:
                lines.append(f'<span class="event-badge {badge_class}">{badge_text}</span>')
            lines.append(f'<span class="event-count">{len(hooks_list)} hook{"s" if len(hooks_list) != 1 else ""}'
                         f'{f" + {len(event_rules)} rules" if event_rules else ""}</span>')
            lines.append('</div>')

            lines.append(f'<div class="event-body" id="b-{eid}">')

            # Per-event expand/collapse -- visible when event is expanded
            if len(hooks_list) > 1 or event_rules:
                lines.append(f'<div class="level-controls">')
                lines.append(f'<button class="expand-btn" onclick="event.stopPropagation(); '
                             f'expandIn(\'b-{eid}\',\'hook-header\',\'hook-detail\')">Expand All</button>')
                lines.append(f'<button class="expand-btn" onclick="event.stopPropagation(); '
                             f'collapseIn(\'b-{eid}\',\'hook-header\',\'hook-detail\')">Collapse All</button>')
                lines.append('</div>')

            # Hooks
            for hi, h in enumerate(hooks_list):
                hid = f'h{hook_id}'
                hook_id += 1
                name = self._e(self._hook_name(h))
                matcher = self._e(h.get('matcher', '*'))
                is_async = h.get('async', False)
                exit_class = 'exit-2' if evt == 'PreToolUse' else 'exit-0'
                exit_text = 'exit 2=BLOCK' if evt == 'PreToolUse' else 'exit 0'
                has_rules = (hi == sm_hook_idx and bool(event_rules))

                lines.append('<div class="hook-row">')
                lines.append(f'<div class="hook-header" id="hh-{hid}" onclick="toggleHook(\'{hid}\')">')
                lines.append(f'<span class="arrow">></span>')
                lines.append(f'<span class="hook-name">{name}</span>')
                if matcher != '*':
                    lines.append(f'<span class="hook-matcher">{matcher}</span>')
                if has_rules:
                    lines.append(f'<span class="event-count" style="font-size:0.85em">{len(event_rules)} rules</span>')
                if is_async:
                    lines.append(f'<span class="event-badge badge-async">ASYNC</span>')
                lines.append(f'<span class="exit-code {exit_class}">{exit_text}</span>')
                lines.append('</div>')

                # Detail panel
                lines.append(f'<div class="hook-detail" id="hd-{hid}">')
                lines.append(f'<div class="detail-section"><div class="detail-label">Command</div>'
                             f'<div class="detail-value"><code>{self._e(h.get("command", ""))}</code></div></div>')
                sp = h.get('script_path', '')
                if sp:
                    sp_resolved = sp.replace('~', str(Path.home()))
                    sp_win = sp_resolved.replace('/', '\\')
                    file_url = 'file:///' + sp_resolved.replace('\\', '/')
                    lines.append(f'<div class="detail-section"><div class="detail-label">Script</div>'
                                 f'<div class="detail-value" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">'
                                 f'<span class="filepath">{self._e(sp)}</span>'
                                 f'<a class="file-btn" href="{self._e(file_url)}" target="_blank">Open File</a>'
                                 f'<button class="file-btn" onclick="copyPath(this, \'{self._e(sp_win)}\')">'
                                 f'Copy Path</button></div></div>')

                # Nest rules under the sm-* hook
                if has_rules:
                    lines.append(f'<div class="detail-section">')
                    lines.append(f'<div class="detail-label" style="display:flex;align-items:center;gap:10px">'
                                 f'RULES ({len(event_rules)})'
                                 f' <button class="expand-btn" onclick="event.stopPropagation(); '
                                 f'expandIn(\'hd-{hid}\',\'rule-header\',\'rule-detail\')">Expand All</button>'
                                 f' <button class="expand-btn" onclick="event.stopPropagation(); '
                                 f'collapseIn(\'hd-{hid}\',\'rule-header\',\'rule-detail\')">Collapse All</button>'
                                 f'</div>')
                    for ri, rule in enumerate(event_rules):
                        rid = f'r{idx}_{ri}'
                        lines.append(self._render_rule(rid, rule, evt))
                    lines.append('</div>')  # detail-section for rules

                lines.append('</div>')  # hook-detail
                lines.append('</div>')  # hook-row

            lines.append('</div>')  # event-body
            lines.append('</div>')  # event-node

            # Connector arrow between events
            if idx < len(self.EVENT_ORDER) - 1:
                lines.append('<div class="connector"><span class="line">|</span></div>')

        lines.append('</div>')  # flow

        # MCP-collocated rules section
        if self._mcp_rules:
            lines.append('<div class="mcp-rules-section">')
            mcp_rule_total = sum(len(v) for v in self._mcp_rules.values())
            lines.append(f'<div class="mcp-rules-header">MCP-Collocated Rules ({mcp_rule_total})</div>')
            for server_name, server_rules in self._mcp_rules.items():
                lines.append(f'<div style="margin-bottom:8px">')
                lines.append(f'<div style="color:#3fb950;font-size:0.9em;margin-bottom:4px;font-family:Consolas,monospace">'
                             f'{self._e(server_name)}/ ({len(server_rules)} rules)</div>')
                for ri, rule in enumerate(server_rules):
                    rid = f'mcp_{server_name}_{ri}'
                    lines.append(self._render_rule(rid, rule, rule.get('_event', 'UserPromptSubmit')))
                lines.append('</div>')
            lines.append('</div>')

        # MISPLACED RULES WARNING -- .md files found in rules/ instead of rule-book/
        if self._misplaced_rules:
            lines.append('<div style="border-top:2px solid #f85149;margin-top:16px;padding-top:12px">')
            lines.append(f'<div style="color:#f85149;font-size:1em;font-weight:700;margin-bottom:8px">'
                         f'!! MISPLACED RULES ({len(self._misplaced_rules)}) -- found in rules/ instead of rule-book/</div>')
            lines.append('<div style="color:#f85149;font-size:0.85em;margin-bottom:12px;background:#1c0c0c;'
                         'padding:10px 14px;border-radius:6px;border:1px solid #f85149">'
                         'These .md files are in ~/.claude/rules/ which is WRONG. '
                         'Claude Code natively loads ALL .md from rules/ on every prompt (~50KB context waste). '
                         'Move them to ~/.claude/rule-book/&lt;event&gt;/ where the keyword-matching hook manages them.</div>')
            for ri, rule in enumerate(self._misplaced_rules):
                rid = f'misplaced_{ri}'
                evt = rule.get('_event', 'unknown')
                lines.append(f'<div style="display:flex;align-items:center;gap:10px;padding:8px 22px;'
                             f'border-bottom:1px solid #21262d;background:#1c0808">')
                lines.append(f'<span class="badge badge-warning">MOVE</span>')
                lines.append(f'<span style="color:#c9d1d9;font-family:Consolas,monospace;font-size:0.9em">'
                             f'{self._e(rule.get("_file", "?"))}</span>')
                lines.append(f'<span style="color:#8b949e;font-size:0.82em">event: {self._e(evt)}</span>')
                target = f'rule-book/{evt}/' if evt != 'unknown' else 'rule-book/&lt;event&gt;/'
                lines.append(f'<span style="color:#ffa657;font-size:0.82em">--> {target}</span>')
                if rule.get('_path'):
                    lines.append(f'<span style="color:#6e7681;font-size:0.8em;margin-left:auto">'
                                 f'{self._e(rule["_path"])}</span>')
                lines.append('</div>')
            lines.append('</div>')

        # RULE ANALYSIS -- self-analyze rules for issues
        all_rules = []
        for evt, rlist in rules.items():
            for r in rlist:
                all_rules.append({**r, '_event': evt})
        for r in self._misplaced_rules:
            all_rules.append(r)
        for srv, rlist in self._mcp_rules.items():
            for r in rlist:
                all_rules.append({**r, '_source': f'mcp:{srv}'})
        findings = self._analyze_rules(all_rules)
        if findings:
            lines.append('<div style="border-top:2px solid #58a6ff;margin-top:16px;padding-top:12px">')
            lines.append(f'<div style="color:#58a6ff;font-size:1em;font-weight:700;margin-bottom:8px">'
                         f'RULE ANALYSIS ({len(findings)} findings)</div>')
            sev_colors = {'error': '#f85149', 'warning': '#d29922', 'info': '#58a6ff'}
            sev_icons = {'error': '!!', 'warning': '!', 'info': '*'}
            for f in findings:
                sc = sev_colors.get(f['severity'], '#8b949e')
                si = sev_icons.get(f['severity'], '*')
                lines.append(f'<div style="display:flex;align-items:flex-start;gap:10px;padding:6px 14px;'
                             f'margin-bottom:4px;background:#0d1117;border-left:3px solid {sc};border-radius:0 4px 4px 0">')
                lines.append(f'<span style="color:{sc};font-weight:700;font-family:Consolas,monospace;min-width:20px">{si}</span>')
                lines.append(f'<span style="color:#c9d1d9;font-size:0.9em">{f["message"]}</span>')
                lines.append('</div>')
            lines.append('</div>')

        lines.append('</div></div>')  # section-body, section
        return '\n'.join(lines)

    def _analyze_rules(self, all_rules: list) -> list:
        """Self-analyze rules for misplacement, missing fields, keyword issues."""
        import re
        findings = []

        # Check 1: UserPromptSubmit rules that should be PreToolUse
        # (contain tool-blocking language like "NEVER use X tool", "block", "gate")
        blocking_patterns = [
            (re.compile(r'NEVER\s+use\s+(the\s+)?(Read|Write|Edit|Task|Bash|Agent)\s+tool', re.I),
             'contains tool-blocking language -- should be PreToolUse (blocks before tool runs)'),
            (re.compile(r'Do\s+NOT\s+use\s+(the\s+)?(Read|Write|Edit|Task|Bash|Agent)\s+tool', re.I),
             'contains tool-blocking language -- should be PreToolUse'),
            (re.compile(r'NEVER\s+read\s+\.env', re.I),
             'blocks reading .env files -- should be PreToolUse gate on Read tool'),
        ]
        for r in all_rules:
            if r.get('_event') != 'UserPromptSubmit':
                continue
            body = r.get('body', '')
            name = r.get('id', r.get('_file', '?'))
            for pat, msg in blocking_patterns:
                if pat.search(body):
                    findings.append({
                        'severity': 'warning',
                        'message': f'<b>{self._e(name)}</b> (UserPromptSubmit): {msg}'
                    })
                    break

        # Check 2: Rules without WHY section
        for r in all_rules:
            body = r.get('body', '')
            name = r.get('id', r.get('_file', '?'))
            if body and '## WHY' not in body and '# WHY' not in body and not r.get('description', ''):
                findings.append({
                    'severity': 'info',
                    'message': f'<b>{self._e(name)}</b>: no WHY section or description -- rules without WHY become cargo cult'
                })

        # Check 3: Keyword overlap detection (same keyword pair in 2+ rules)
        from collections import defaultdict
        kw_pairs = defaultdict(list)
        for r in all_rules:
            kws = r.get('keywords', [])
            if isinstance(kws, str):
                kws = [k.strip() for k in kws.split(',')]
            name = r.get('id', r.get('_file', '?'))
            if len(kws) >= 2:
                seen_pairs = set()
                for i in range(len(kws)):
                    for j in range(i+1, len(kws)):
                        pair = tuple(sorted([kws[i].lower(), kws[j].lower()]))
                        if pair not in seen_pairs:
                            seen_pairs.add(pair)
                            kw_pairs[pair].append(name)
        for pair, rules_with in kw_pairs.items():
            if len(rules_with) > 1:
                findings.append({
                    'severity': 'info',
                    'message': f'Keyword overlap [{pair[0]}, {pair[1]}]: shared by {", ".join("<b>" + self._e(n) + "</b>" for n in rules_with)} -- both fire on same prompts'
                })

        # Check 4: Stop rules using keywords instead of pattern
        for r in all_rules:
            if r.get('_event') != 'Stop':
                continue
            name = r.get('id', r.get('_file', '?'))
            if r.get('keywords') and not r.get('pattern'):
                findings.append({
                    'severity': 'warning',
                    'message': f'<b>{self._e(name)}</b> (Stop): uses keywords instead of pattern regex -- keywords false-positive on code/tables'
                })

        # Check 5: Rules with very few keywords (< 3) and min_matches > 1
        for r in all_rules:
            kws = r.get('keywords', [])
            if isinstance(kws, str):
                kws = [k.strip() for k in kws.split(',')]
            name = r.get('id', r.get('_file', '?'))
            mm = int(r.get('min_matches', 2) or 2)
            if 0 < len(kws) < 3 and mm >= 2:
                findings.append({
                    'severity': 'info',
                    'message': f'<b>{self._e(name)}</b>: only {len(kws)} keywords with min_matches={mm} -- narrow trigger, may rarely fire'
                })

        return findings

    def _render_rule(self, rid: str, rule: Dict, event: str) -> str:
        """Render a single rule row with full details: WHY, keywords, min_matches, firing stats."""
        lines = []
        rname = self._e(rule.get('id', rule.get('name', rule.get('_file', '?'))))
        raction = self._e((rule.get('action', '') or '')[:60])
        enabled = rule.get('enabled', 'true') != 'false'
        disabled_cls = '' if enabled else ' rule-disabled'
        source = rule.get('_source', 'rules')

        # Keyword count for header
        kws = rule.get('keywords', [])
        if isinstance(kws, str):
            kws = [kws]
        kw_count = len(kws)
        min_matches = rule.get('min_matches', '2')

        # Firing stats lookup
        rule_id = rule.get('id', rule.get('_file', '').replace('.md', ''))
        stats = self._firing_stats.get(rule_id, {})
        total_fires = stats.get('total', 0)

        lines.append(f'<div class="rule-row{disabled_cls}">')
        lines.append(f'<div class="rule-header" id="rh-{rid}" onclick="toggleRule(\'{rid}\')">')
        lines.append(f'<span class="arrow">></span>')
        lines.append(f'<span class="rule-icon">*</span>')
        lines.append(f'<span class="rule-name">{rname}</span>')

        # Source badge
        src_cls = 'src-rulebook' if source == 'rule-book' else ('src-mcp' if source.startswith('mcp:') else 'src-rules')
        lines.append(f'<span class="rule-source-badge {src_cls}">{self._e(source)}</span>')

        # Enabled badge
        en_cls = 'on' if enabled else 'off'
        en_text = 'ON' if enabled else 'OFF'
        lines.append(f'<span class="rule-enabled-badge {en_cls}">{en_text}</span>')

        # Total fires badge
        if total_fires > 0:
            fire_cls = 'hot' if total_fires > 50 else ''
            lines.append(f'<span style="color:#ffa657;font-size:0.82em;margin-left:6px">{total_fires} fires</span>')

        if raction:
            lines.append(f'<span class="rule-action">{raction}</span>')
        lines.append('</div>')

        # Detail panel
        lines.append(f'<div class="rule-detail" id="rd-{rid}">')

        # WHY / Description
        desc = rule.get('description', '')
        if desc:
            lines.append(f'<div class="rule-field"><div class="rule-field-label">WHY</div>'
                         f'<div class="rule-why">{self._e(desc)}</div></div>')

        # Event type
        lines.append(f'<div class="rule-field"><div class="rule-field-label">Hook Event</div>'
                     f'<div class="rule-field-value">{self._e(event)}</div></div>')

        # Pattern (Stop rules)
        if rule.get('pattern'):
            lines.append(f'<div class="rule-field"><div class="rule-field-label">Pattern (regex)</div>'
                         f'<div class="rule-field-value pattern">{self._e(rule["pattern"])}</div></div>')

        # Keywords with count and min_matches
        if kws:
            kw_spans = ''.join(f'<span>{self._e(k)}</span>' for k in kws)
            lines.append(f'<div class="rule-field"><div class="rule-field-label">'
                         f'Keywords ({kw_count})'
                         f'<span class="rule-min-matches">min_matches: {self._e(str(min_matches))}</span>'
                         f'</div>'
                         f'<div class="rule-field-value keywords">{kw_spans}</div></div>')

        # Priority
        if rule.get('priority'):
            lines.append(f'<div class="rule-field"><div class="rule-field-label">Priority</div>'
                         f'<div class="rule-field-value">{self._e(rule["priority"])}</div></div>')

        # Firing stats
        if stats:
            lines.append(f'<div class="rule-field"><div class="rule-field-label">Firing Stats</div>')
            lines.append(f'<div class="rule-stats">')
            for window, label in [('hour', '1h'), ('day', '1d'), ('week', '1w'), ('month', '1m'), ('year', '1y'), ('total', 'all')]:
                val = stats.get(window, 0)
                val_cls = 'zero' if val == 0 else ('very-hot' if val > 100 else ('hot' if val > 10 else ''))
                lines.append(f'<div class="stat-cell"><span class="stat-val {val_cls}">{val}</span>'
                             f'<span class="stat-win">{label}</span></div>')
            lines.append('</div>')
            last_fired = stats.get('last_fired')
            if last_fired:
                ts_str = last_fired.strftime('%Y-%m-%d %H:%M') if hasattr(last_fired, 'strftime') else str(last_fired)
                lines.append(f'<div style="font-size:0.82em;color:#6e7681;margin-top:4px">Last fired: {self._e(ts_str)} UTC</div>')
            lines.append('</div>')

        # File path with edit/backup buttons
        if rule.get('_path'):
            sp = rule['_path']
            sp_win = sp.replace('/', '\\')
            sp_escaped = sp_win.replace('\\', '\\\\').replace("'", "\\'")
            file_url = 'file:///' + sp.replace('\\', '/')
            lines.append(f'<div class="rule-field"><div class="rule-field-label">File</div>'
                         f'<div class="rule-field-value" style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">'
                         f'<span class="filepath" style="font-size:0.85em;color:#8b949e">{self._e(sp)}</span>'
                         f'<a class="file-btn" href="{self._e(file_url)}" target="_blank">Open</a>'
                         f'<button class="file-btn" onclick="copyPath(this, \'{self._e(sp_win)}\')">Copy Path</button>'
                         f'<button class="edit-btn" onclick="editRule(\'{rid}\', \'{sp_escaped}\')">Edit</button>'
                         f'<button class="edit-btn backup" onclick="backupRule(\'{rid}\', \'{sp_escaped}\')">Backup</button>'
                         f'<span id="status-{rid}" class="edit-status"></span>'
                         f'</div></div>')

        # Body (rule content)
        if rule.get('body'):
            lines.append(f'<div class="rule-field" id="content-field-{rid}"><div class="rule-field-label">Rule Content</div>'
                         f'<div class="rule-full-text" id="content-{rid}">{self._e(rule["body"][:2000])}</div></div>')

        lines.append('</div>')  # rule-detail
        lines.append('</div>')  # rule-row
        return '\n'.join(lines)

    def _section_security(self, flags: List[Dict]) -> str:
        lines = []
        lines.append('<div class="section">')
        count = len(flags)
        lines.append(f'<div class="section-header" id="h-sec" onclick="toggle(\'sec\')">'
                     f'<span class="arrow">></span><span class="section-title">Security Flags</span>'
                     f'<span class="section-count">{count}</span></div>')
        lines.append(f'<div class="section-body" id="b-sec">')
        if not flags:
            lines.append('<div class="item-row"><span class="item-desc">No security concerns found.</span></div>')
        else:
            # Severity filter checkboxes + resolve button
            lines.append('<div style="display:flex;gap:16px;align-items:center;margin-bottom:12px;flex-wrap:wrap">')
            lines.append('<span style="color:#8b949e;font-size:13px">Include:</span>')
            lines.append('<label style="color:#f85149;cursor:pointer"><input type="checkbox" checked class="sev-filter" data-sev="warning" onchange="filterSecFlags()"> warning</label>')
            lines.append('<label style="color:#58a6ff;cursor:pointer"><input type="checkbox" checked class="sev-filter" data-sev="info" onchange="filterSecFlags()"> info</label>')
            lines.append('<button class="expand-btn" onclick="resolveWithClaude()" style="margin-left:auto">Resolve with Claude</button>')
            lines.append('</div>')
            shown = flags[:100]
            for f in shown:
                ftype = self._e(f.get("type", "unknown"))
                ffile = self._e((f.get("file", "") or "")[-45:])
                msg = self._e((f.get("message", "") or "")[:60])
                sev = f.get("severity", "info")
                badge_class = 'badge-warning' if sev == 'warning' else 'badge-info'
                lines.append(f'<div class="flag-row" data-severity="{self._e(sev)}"><span class="badge {badge_class}">{self._e(sev)}</span>'
                             f'<span class="flag-type">{ftype}</span><span class="flag-file">{ffile}</span>'
                             f'<span class="flag-msg">{msg}</span></div>')
            if count > 100:
                lines.append(f'<div class="item-row"><span class="item-desc">... and {count - 100} more flags</span></div>')
        lines.append('</div></div>')
        return '\n'.join(lines)

    def _section_legend(self) -> str:
        return """<div class="legend">
  <h3>EXIT CODE REFERENCE</h3>
  <div class="legend-grid">
    <div class="legend-item"><span class="exit-code exit-0">exit 0</span> Allow / inject stdout as context</div>
    <div class="legend-item"><span class="exit-code exit-2">exit 2</span> BLOCK (PreToolUse only)</div>
    <div class="legend-item"><span class="event-badge badge-inject">INJECT</span> Adds context to Claude's prompt</div>
    <div class="legend-item"><span class="event-badge badge-gate">GATE</span> Can block tool execution</div>
    <div class="legend-item"><span class="event-badge badge-check">CHECK</span> Validates after tool runs</div>
    <div class="legend-item"><span class="event-badge badge-block">BLOCK</span> Can block Claude's response</div>
    <div class="legend-item"><span class="event-badge badge-async">ASYNC</span> Runs in background</div>
  </div>
</div>"""

    def _collect_bundle_files(self, mcp_data: Dict, skill_data: Dict, hook_data: Dict, rules: Dict) -> Dict[str, List[Dict]]:
        """Collect all config/source files for the share bundle."""
        home = Path.home()
        claude_dir = home / '.claude'
        bundle = {"configs": [], "hooks": [], "rules": [], "skills": []}

        def _read(p: Path) -> str:
            try:
                return p.read_text(encoding='utf-8', errors='replace')
            except Exception:
                return ''

        def _add(cat: str, path: Path, display_name: str = ''):
            if path.exists() and path.is_file():
                content = _read(path)
                if content:
                    bundle[cat].append({"path": display_name or path.name, "content": content, "size": len(content)})

        # Core configs
        _add("configs", claude_dir / 'settings.json')
        _add("configs", claude_dir / 'CLAUDE.md', 'global-CLAUDE.md')
        _add("configs", Path.cwd() / '.mcp.json')
        _add("configs", Path.cwd() / 'CLAUDE.md', 'project-CLAUDE.md')

        # Hook scripts from settings.json
        # Schema: hooks[event] = [{matcher, hooks: [{type, command}]}]
        settings_path = claude_dir / 'settings.json'
        if settings_path.exists():
            try:
                settings = json_mod.loads(settings_path.read_text())
                seen_hooks = set()
                for event, hook_groups in settings.get('hooks', {}).items():
                    for group in hook_groups:
                        for hook in group.get('hooks', []):
                            cmd_str = hook.get('command', '') or ''
                            # Extract script path from command string
                            # Formats: node "path.js", python path.py, bash "$HOME/path.sh"
                            raw = None
                            for ext in ('.js', '.py', '.sh'):
                                idx = cmd_str.find(ext)
                                if idx < 0:
                                    continue
                                # Walk backwards from extension to find path start
                                end = idx + len(ext)
                                start = end - 1
                                while start > 0 and cmd_str[start-1] not in (' ', '"', "'"):
                                    start -= 1
                                candidate = cmd_str[start:end]
                                if candidate:
                                    raw = candidate.strip('"').strip("'").replace('$HOME', str(Path.home()))
                                    break
                            if raw:
                                script_path = Path(raw)
                                if script_path.exists() and str(script_path) not in seen_hooks:
                                    seen_hooks.add(str(script_path))
                                    rel = f'{event}/{script_path.name}'
                                    _add("hooks", script_path, rel)
            except Exception:
                pass

        # Rules from all event dirs
        rules_dir = claude_dir / 'rules'
        if rules_dir.exists():
            for md in sorted(rules_dir.rglob('*.md')):
                if 'backups' in str(md) or 'archive' in str(md):
                    continue
                try:
                    rel = str(md.relative_to(rules_dir))
                except ValueError:
                    rel = md.name
                content = _read(md)
                if content:
                    bundle["rules"].append({"path": rel, "content": content, "size": len(content)})

        # Skill SKILL.md files
        skills_dir = claude_dir / 'skills'
        if skills_dir.exists():
            for skill_md in sorted(skills_dir.rglob('SKILL.md')):
                try:
                    rel = str(skill_md.relative_to(skills_dir))
                except ValueError:
                    rel = skill_md.name
                content = _read(skill_md)
                if content:
                    bundle["skills"].append({"path": rel, "content": content, "size": len(content)})

        # MCP server files (includes mcp-manager source + all server sources)
        mcp_files = []
        # Find MCP base directory
        mcp_base = None
        for candidate in [Path.cwd().parent / 'MCP', home / 'mcp']:
            if candidate.exists():
                mcp_base = candidate
                break
        if mcp_base:
            # mcp-manager source files
            mgr_dir = mcp_base / 'mcp-manager'
            if mgr_dir.exists():
                for rel in ['build/index.js', 'servers.yaml', 'package.json']:
                    p = mgr_dir / rel
                    if p.exists():
                        content = _read(p)
                        if content and len(content) < 500000:
                            mcp_files.append({"path": f"mcp-manager/{rel}", "content": content, "size": len(content)})
        # Individual server source files from scanner data
        seen_mcp = set()
        for status in ['running', 'stopped', 'disabled']:
            for srv in mcp_data.get("servers", {}).get(status, []):
                name = srv.get('name', '') or ''
                sp = srv.get('script_path', '')
                if not sp:
                    continue
                sp_resolved = Path(sp.replace('~', str(home)))
                if sp_resolved.exists() and str(sp_resolved) not in seen_mcp:
                    seen_mcp.add(str(sp_resolved))
                    content = _read(sp_resolved)
                    if content and len(content) < 500000:
                        display = f"{name}/{sp_resolved.name}" if name else sp_resolved.name
                        mcp_files.append({"path": display, "content": content, "size": len(content)})
        if mcp_files:
            bundle["mcp_servers"] = mcp_files

        return bundle
