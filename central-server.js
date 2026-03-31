#!/usr/bin/env node
/**
 * central-server.js -- Fleet dashboard server for claude-portable.
 *
 * Serves the dashboard HTML at GET / and proxies API calls to the dispatcher.
 *
 * Environment variables:
 *   DASHBOARD_PORT        Port to listen on (default: 3000)
 *   DISPATCHER_URL        Dispatcher base URL (default: http://localhost:8080)
 *   DISPATCH_API_TOKEN    Bearer token for task submission (optional)
 */

var http = require("http");
var url = require("url");

var PORT = parseInt(process.env.DASHBOARD_PORT || "3000", 10);
var DISPATCHER_URL = (process.env.DISPATCHER_URL || "http://localhost:8080").replace(/\/$/, "");
var API_TOKEN = process.env.DISPATCH_API_TOKEN || "";

// ── Proxy helper ──────────────────────────────────────────────────────────────

function proxyToDispatcher(req, res, targetPath, options) {
  var parsed = url.parse(DISPATCHER_URL);
  var opts = {
    hostname: parsed.hostname,
    port: parsed.port || 80,
    path: targetPath,
    method: options && options.method || req.method,
    headers: { "Content-Type": "application/json" },
    timeout: 8000,
  };
  if (API_TOKEN) {
    opts.headers["Authorization"] = "Bearer " + API_TOKEN;
  }

  var proxyReq = http.request(opts, function(proxyRes) {
    res.writeHead(proxyRes.statusCode, {
      "Content-Type": proxyRes.headers["content-type"] || "application/json",
      "Access-Control-Allow-Origin": "*",
    });
    proxyRes.pipe(res);
  });

  proxyReq.on("error", function(err) {
    res.writeHead(502, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "Dispatcher unreachable", detail: err.message }));
  });

  proxyReq.on("timeout", function() {
    proxyReq.destroy();
    res.writeHead(504, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "Dispatcher timeout" }));
  });

  if (options && options.body) {
    proxyReq.write(options.body);
    proxyReq.end();
  } else if (req.method === "POST" || req.method === "PUT") {
    req.pipe(proxyReq);
  } else {
    proxyReq.end();
  }
}

// ── HTTP Server ───────────────────────────────────────────────────────────────

var server = http.createServer(function(req, res) {
  var parsed = url.parse(req.url, true);
  var pathname = parsed.pathname;

  // CORS preflight
  if (req.method === "OPTIONS") {
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization",
    });
    res.end();
    return;
  }

  // Serve dashboard HTML
  if (pathname === "/" && req.method === "GET") {
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    res.end(DASHBOARD_HTML);
    return;
  }

  // Proxy API endpoints to dispatcher (includes /api/*, /dashboard/api/*, /health, /board)
  if (pathname.startsWith("/api/") || pathname.startsWith("/dashboard/api/") || pathname === "/health" || pathname === "/board") {
    proxyToDispatcher(req, res, pathname);
    return;
  }

  // POST /task -- submit new task (proxied to dispatcher)
  if (pathname === "/task" && req.method === "POST") {
    proxyToDispatcher(req, res, "/task", { method: "POST" });
    return;
  }

  // 404
  res.writeHead(404, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ error: "Not found" }));
});

server.listen(PORT, function() {
  console.log("[central-server] Listening on port " + PORT);
  console.log("[central-server] Dispatcher: " + DISPATCHER_URL);
});

// ── Dashboard HTML ────────────────────────────────────────────────────────────

var DASHBOARD_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CCC Fleet Dashboard</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  background: #0d1117;
  color: #e6edf3;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: 18px;
  line-height: 1.6;
}

/* ── Header ─────────────────────────────────────────────────── */
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 28px;
  background: #161b22;
  border-bottom: 1px solid #30363d;
}
.header h1 { font-size: 26px; font-weight: 700; letter-spacing: -0.5px; }
.refresh-info { font-size: 14px; color: #8b949e; display: flex; align-items: center; gap: 8px; }
.refresh-dot {
  width: 10px; height: 10px;
  border-radius: 50%;
  background: #3fb950;
  animation: pulse 2s infinite;
}
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }

/* ── Fleet Stats Bar ────────────────────────────────────────── */
.fleet-bar {
  display: flex;
  gap: 32px;
  padding: 16px 28px;
  background: #161b22;
  border-bottom: 1px solid #30363d;
  flex-wrap: wrap;
}
.fleet-stat { text-align: center; min-width: 110px; }
.fleet-stat .val { font-size: 36px; font-weight: 800; color: #3fb950; }
.fleet-stat .lbl { font-size: 13px; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; }
.fleet-stat.warn .val { color: #d29922; }
.fleet-stat.danger .val { color: #f85149; }

/* ── Sections ───────────────────────────────────────────────── */
.section { padding: 24px 28px; }
.section-title {
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.section-title .count {
  background: #30363d;
  color: #8b949e;
  font-size: 13px;
  padding: 2px 10px;
  border-radius: 12px;
}

/* ── Worker Grid ────────────────────────────────────────────── */
.workers-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 14px;
}
@media (max-width: 1200px) { .workers-grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 768px) { .workers-grid { grid-template-columns: repeat(2, 1fr); } }

.worker-card {
  background: #161b22;
  border: 2px solid #30363d;
  border-radius: 10px;
  padding: 18px;
  transition: all 0.2s;
  cursor: default;
  min-height: 130px;
}
.worker-card:hover { border-color: #58a6ff; transform: translateY(-2px); }
.worker-card.idle { border-left: 5px solid #3fb950; }
.worker-card.busy { border-left: 5px solid #d29922; }
.worker-card.unreachable { border-left: 5px solid #f85149; }
.worker-card.empty { border-left: 5px solid #30363d; opacity: 0.4; }

.worker-name { font-size: 17px; font-weight: 700; margin-bottom: 6px; display: flex; align-items: center; gap: 8px; }
.status-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
.dot-idle { background: #3fb950; }
.dot-busy { background: #d29922; }
.dot-unreachable { background: #f85149; }
.dot-empty { background: #30363d; }

.worker-info { font-size: 14px; color: #8b949e; }
.worker-task { font-size: 14px; color: #c9d1d9; margin-top: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* ── Task List ──────────────────────────────────────────────── */
.tasks-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 16px;
}
.tasks-table th {
  text-align: left;
  padding: 12px 14px;
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: #8b949e;
  border-bottom: 2px solid #30363d;
  position: sticky;
  top: 0;
  background: #0d1117;
}
.tasks-table td {
  padding: 12px 14px;
  border-bottom: 1px solid #21262d;
  vertical-align: middle;
}
.tasks-table tr:hover { background: #161b22; }

.badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 14px;
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.badge-completed { background: #1b4332; color: #3fb950; }
.badge-dispatched { background: #3d2e00; color: #d29922; }
.badge-pending { background: #21262d; color: #8b949e; }
.badge-failed { background: #3d0000; color: #f85149; }

.desc-cell { max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mono { font-family: 'Consolas', 'Monaco', 'Courier New', monospace; font-size: 14px; }

/* ── Submit Form ────────────────────────────────────────────── */
.submit-section {
  padding: 20px 28px;
  background: #161b22;
  border-top: 1px solid #30363d;
  position: sticky;
  bottom: 0;
}
.submit-form {
  display: flex;
  gap: 12px;
  max-width: 800px;
}
.submit-input {
  flex: 1;
  padding: 14px 18px;
  font-size: 16px;
  background: #0d1117;
  border: 2px solid #30363d;
  border-radius: 8px;
  color: #e6edf3;
  outline: none;
  transition: border-color 0.2s;
}
.submit-input:focus { border-color: #58a6ff; }
.submit-input::placeholder { color: #484f58; }
.submit-btn {
  padding: 14px 28px;
  font-size: 16px;
  font-weight: 700;
  background: #238636;
  color: #fff;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.2s;
}
.submit-btn:hover { background: #2ea043; }
.submit-btn:disabled { background: #21262d; color: #484f58; cursor: not-allowed; }
.submit-status { font-size: 14px; color: #8b949e; margin-top: 8px; min-height: 20px; }

/* ── Misc ───────────────────────────────────────────────────── */
.status-msg { text-align: center; padding: 40px; color: #8b949e; font-size: 16px; }
.error-msg { color: #f85149; }
.uptime { font-size: 13px; color: #484f58; margin-left: 16px; }

::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: #0d1117; }
::-webkit-scrollbar-thumb { background: #30363d; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #58a6ff; }
</style>
</head>
<body>

<!-- Header -->
<div class="header">
  <h1>CCC Fleet Dashboard<span class="uptime" id="uptime"></span></h1>
  <div class="refresh-info">
    <span class="refresh-dot" id="refresh-dot"></span>
    Auto-refresh <span id="countdown">10</span>s
  </div>
</div>

<!-- Fleet Stats -->
<div class="fleet-bar" id="fleet-bar">
  <div class="fleet-stat"><span class="val" id="stat-total">--</span><span class="lbl">Workers</span></div>
  <div class="fleet-stat"><span class="val" id="stat-idle">--</span><span class="lbl">Idle</span></div>
  <div class="fleet-stat warn"><span class="val" id="stat-busy">--</span><span class="lbl">Busy</span></div>
  <div class="fleet-stat"><span class="val" id="stat-tasks">--</span><span class="lbl">Tasks Today</span></div>
  <div class="fleet-stat danger"><span class="val" id="stat-failed">--</span><span class="lbl">Failed</span></div>
  <div class="fleet-stat"><span class="val" id="stat-rate">--</span><span class="lbl">Success Rate</span></div>
  <div class="fleet-stat"><span class="val" id="stat-avg">--</span><span class="lbl">Avg Duration</span></div>
</div>

<!-- Workers Grid -->
<div class="section">
  <div class="section-title">Workers <span class="count" id="worker-count">0</span></div>
  <div class="workers-grid" id="workers-grid">
    <!-- Filled by JS -->
  </div>
</div>

<!-- Tasks -->
<div class="section">
  <div class="section-title">Tasks <span class="count" id="task-count">0</span></div>
  <div style="max-height: 500px; overflow-y: auto;">
    <table class="tasks-table">
      <thead>
        <tr>
          <th>Status</th>
          <th>ID</th>
          <th>Description</th>
          <th>Worker</th>
          <th>Duration</th>
        </tr>
      </thead>
      <tbody id="tasks-body">
        <tr><td colspan="5" class="status-msg">Loading...</td></tr>
      </tbody>
    </table>
  </div>
</div>

<!-- Submit Form -->
<div class="submit-section">
  <form class="submit-form" id="submit-form">
    <input type="text" class="submit-input" id="task-input" placeholder="Submit a new task..." autocomplete="off">
    <button type="submit" class="submit-btn" id="submit-btn">Submit</button>
  </form>
  <div class="submit-status" id="submit-status"></div>
</div>

<script>
(function() {
  var REFRESH_INTERVAL = 10;
  var countdown = REFRESH_INTERVAL;
  var countdownEl = document.getElementById('countdown');
  var refreshDot = document.getElementById('refresh-dot');

  // ── Helpers ──────────────────────────────────────────────────

  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
  }

  function fmtDuration(sec) {
    if (sec == null) return '--';
    var s = Math.floor(sec);
    if (s < 60) return s + 's';
    if (s < 3600) return Math.floor(s/60) + 'm ' + (s%60) + 's';
    return Math.floor(s/3600) + 'h ' + Math.floor((s%3600)/60) + 'm';
  }

  function fmtUptime(sec) {
    if (!sec) return '';
    var h = Math.floor(sec / 3600);
    var m = Math.floor((sec % 3600) / 60);
    return 'Uptime: ' + h + 'h ' + m + 'm';
  }

  function badgeCls(state) {
    var s = (state || '').toLowerCase();
    if (s === 'completed') return 'badge-completed';
    if (s === 'dispatched') return 'badge-dispatched';
    if (s === 'failed') return 'badge-failed';
    return 'badge-pending';
  }

  // ── Fetch ────────────────────────────────────────────────────

  function fetchJSON(path) {
    return fetch(path).then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  // ── Render Stats ─────────────────────────────────────────────

  function renderStats(stats) {
    document.getElementById('stat-total').textContent = stats.total_workers != null ? stats.total_workers : '--';
    document.getElementById('stat-idle').textContent = stats.idle_count != null ? stats.idle_count : '--';
    document.getElementById('stat-busy').textContent = stats.busy_count != null ? stats.busy_count : '--';
    document.getElementById('stat-tasks').textContent = stats.tasks_completed_today != null ? stats.tasks_completed_today : '--';
    document.getElementById('stat-failed').textContent = stats.tasks_failed_today != null ? stats.tasks_failed_today : '--';
    document.getElementById('stat-rate').textContent = stats.success_rate_percent != null ? stats.success_rate_percent + '%' : '--';
    document.getElementById('stat-avg').textContent = stats.avg_duration_seconds ? fmtDuration(stats.avg_duration_seconds) : '--';
    document.getElementById('uptime').textContent = stats.uptime_seconds ? fmtUptime(stats.uptime_seconds) : '';
  }

  // ── Render Workers ───────────────────────────────────────────

  var MAX_SLOTS = 10;

  function renderWorkers(workersObj) {
    var grid = document.getElementById('workers-grid');
    var workers = [];
    // workersObj is { id: {...}, ... }
    for (var k in workersObj) {
      if (workersObj.hasOwnProperty(k)) {
        var w = workersObj[k];
        w._id = k;
        workers.push(w);
      }
    }
    // Sort: busy first, then idle, then unreachable
    var ORDER = { busy: 0, idle: 1 };
    workers.sort(function(a, b) {
      var oa = ORDER[a.status] != null ? ORDER[a.status] : 2;
      var ob = ORDER[b.status] != null ? ORDER[b.status] : 2;
      return oa - ob;
    });

    document.getElementById('worker-count').textContent = workers.length;

    var html = '';
    for (var i = 0; i < MAX_SLOTS; i++) {
      if (i < workers.length) {
        var w = workers[i];
        var st = (w.status || 'unreachable').toLowerCase();
        var dotCls = st === 'idle' ? 'dot-idle' : st === 'busy' ? 'dot-busy' : 'dot-unreachable';
        var taskText = w.current_task_id ? w.current_task_id : 'No task';

        html += '<div class="worker-card ' + esc(st) + '">'
          + '<div class="worker-name"><span class="status-dot ' + dotCls + '"></span>' + esc(w._id) + '</div>'
          + '<div class="worker-info">'
          + (w.ip ? 'IP: ' + esc(w.ip) : '')
          + ' | Done: ' + (w.tasks_completed || 0)
          + ' | Failed: ' + (w.tasks_failed || 0)
          + '</div>'
          + '<div class="worker-task">' + esc(taskText) + '</div>'
          + '</div>';
      } else {
        html += '<div class="worker-card empty">'
          + '<div class="worker-name"><span class="status-dot dot-empty"></span>slot-' + (i + 1) + '</div>'
          + '<div class="worker-info">Available</div>'
          + '</div>';
      }
    }
    grid.innerHTML = html;
  }

  // ── Render Tasks ─────────────────────────────────────────────

  var STATE_ORDER = { dispatched: 0, pending: 1, completed: 2, failed: 3 };

  function renderTasks(tasks) {
    var tbody = document.getElementById('tasks-body');
    if (!tasks || !tasks.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="status-msg">No tasks</td></tr>';
      document.getElementById('task-count').textContent = '0';
      return;
    }
    tasks.sort(function(a, b) {
      var oa = STATE_ORDER[a.state] != null ? STATE_ORDER[a.state] : 4;
      var ob = STATE_ORDER[b.state] != null ? STATE_ORDER[b.state] : 4;
      return oa - ob;
    });
    document.getElementById('task-count').textContent = tasks.length;

    var html = '';
    for (var i = 0; i < tasks.length; i++) {
      var t = tasks[i];
      var desc = t.text || t.description || '--';
      if (desc.length > 80) desc = desc.substring(0, 80) + '...';
      html += '<tr>'
        + '<td><span class="badge ' + badgeCls(t.state || t.status) + '">' + esc(t.state || t.status) + '</span></td>'
        + '<td class="mono">' + esc(t.id || '--') + '</td>'
        + '<td class="desc-cell" title="' + esc(t.text || t.description || '') + '">' + esc(desc) + '</td>'
        + '<td>' + esc(t.worker || '--') + '</td>'
        + '<td class="mono">' + fmtDuration(t.duration_seconds) + '</td>'
        + '</tr>';
    }
    tbody.innerHTML = html;
  }

  // ── Refresh ──────────────────────────────────────────────────

  function refresh() {
    countdown = REFRESH_INTERVAL;
    refreshDot.style.background = '#58a6ff';
    setTimeout(function() { refreshDot.style.background = '#3fb950'; }, 300);

    fetchJSON('/api/stats')
      .then(renderStats)
      .catch(function() { renderStats({}); });

    fetchJSON('/api/workers')
      .then(renderWorkers)
      .catch(function() { renderWorkers({}); });

    fetchJSON('/api/tasks')
      .then(function(data) { renderTasks(Array.isArray(data) ? data : data.tasks || []); })
      .catch(function(err) {
        document.getElementById('tasks-body').innerHTML =
          '<tr><td colspan="5" class="status-msg error-msg">Failed: ' + esc(String(err)) + '</td></tr>';
      });
  }

  // ── Countdown ────────────────────────────────────────────────

  setInterval(function() {
    countdown--;
    if (countdown <= 0) { refresh(); }
    countdownEl.textContent = countdown;
  }, 1000);

  // ── Submit Form ──────────────────────────────────────────────

  var form = document.getElementById('submit-form');
  var input = document.getElementById('task-input');
  var btn = document.getElementById('submit-btn');
  var statusEl = document.getElementById('submit-status');

  form.addEventListener('submit', function(e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text) return;

    btn.disabled = true;
    statusEl.textContent = 'Submitting...';

    fetch('/task', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description: text })
    })
    .then(function(r) {
      if (!r.ok) return r.json().then(function(d) { throw new Error(d.error || 'HTTP ' + r.status); });
      return r.json();
    })
    .then(function(data) {
      statusEl.textContent = 'Submitted: ' + (data.id || data.task_id || 'OK');
      input.value = '';
      setTimeout(refresh, 1000);
    })
    .catch(function(err) {
      statusEl.textContent = 'Error: ' + err.message;
    })
    .finally(function() {
      btn.disabled = false;
      setTimeout(function() { statusEl.textContent = ''; }, 5000);
    });
  });

  // ── Init ─────────────────────────────────────────────────────

  refresh();
})();
</script>
</body>
</html>`;
