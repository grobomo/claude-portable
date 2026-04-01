#!/usr/bin/env node
/**
 * central-server.js -- Monitoring dashboard server for CCC fleet.
 *
 * Serves a /fleet-tune endpoint that shows current vs desired node counts
 * with color coding: green = matched, yellow = drift, red = critical.
 *
 * Usage:
 *   node central-server.js
 *
 * Environment:
 *   DASHBOARD_PORT            Port to listen on (default: 8082)
 *   DISPATCHER_HEALTH_URL     Dispatcher /health URL (default: http://localhost:8080/health)
 *   TUNE_CONFIG_PATH          Path to tune-config.json (default: ../scripts/fleet/tune-config.json)
 */

const http = require("http");
const fs = require("fs");
const path = require("path");

const PORT = parseInt(process.env.DASHBOARD_PORT || "8082", 10);
const DISPATCHER_URL = process.env.DISPATCHER_HEALTH_URL || "http://localhost:8080/health";
const TUNE_CONFIG_PATH = process.env.TUNE_CONFIG_PATH ||
  path.join(__dirname, "..", "scripts", "fleet", "tune-config.json");

// ── Helpers ───────────────────────────────────────────────────────────────────

function loadTuneConfig() {
  try {
    return JSON.parse(fs.readFileSync(TUNE_CONFIG_PATH, "utf8"));
  } catch (err) {
    return {
      worker_ratio: 2,
      worker_minimum: 10,
      monitor_ratio: 20,
      monitor_minimum: 1,
      dispatcher_count: 1,
      drift_threshold_percent: 20,
      critical_threshold_percent: 50,
    };
  }
}

function fetchJSON(url) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, { timeout: 5000 }, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => {
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          reject(new Error("Invalid JSON from dispatcher"));
        }
      });
    });
    req.on("error", reject);
    req.on("timeout", () => { req.destroy(); reject(new Error("Timeout")); });
  });
}

function computeTuning(health, config) {
  const pendingTasks = health.pending_tasks || 0;
  const roster = health.fleet_roster || {};

  const actualWorkers = Object.keys(roster).filter((k) => k.startsWith("worker")).length;
  const actualMonitors = Object.keys(roster).filter((k) => k.startsWith("monitor")).length;
  const actualDispatchers = 1;

  const desiredWorkers = Math.max(pendingTasks * config.worker_ratio, config.worker_minimum);
  const desiredMonitors = Math.max(Math.floor(desiredWorkers / config.monitor_ratio), config.monitor_minimum);
  const desiredDispatchers = config.dispatcher_count;

  function statusFor(actual, desired) {
    if (actual === desired) return "matched";
    if (desired === 0) return "critical";
    const pct = Math.abs(actual - desired) / desired * 100;
    if (pct >= config.critical_threshold_percent) return "critical";
    if (pct >= config.drift_threshold_percent) return "drift";
    return "drift";
  }

  return {
    pending_tasks: pendingTasks,
    active_workers: health.active_workers || 0,
    nodes: [
      {
        type: "Workers",
        actual: actualWorkers,
        desired: desiredWorkers,
        delta: desiredWorkers - actualWorkers,
        status: statusFor(actualWorkers, desiredWorkers),
      },
      {
        type: "Monitors",
        actual: actualMonitors,
        desired: desiredMonitors,
        delta: desiredMonitors - actualMonitors,
        status: statusFor(actualMonitors, desiredMonitors),
      },
      {
        type: "Dispatchers",
        actual: actualDispatchers,
        desired: desiredDispatchers,
        delta: desiredDispatchers - actualDispatchers,
        status: statusFor(actualDispatchers, desiredDispatchers),
      },
    ],
  };
}

function recommendation(node) {
  if (node.delta > 0) return `Add ${node.delta} ${node.type.toLowerCase()}`;
  if (node.delta < 0) return `Remove ${Math.abs(node.delta)} ${node.type.toLowerCase()}`;
  return `${node.type} OK`;
}

// ── HTML Template ─────────────────────────────────────────────────────────────

function renderFleetTuneHTML(tuning) {
  const statusColor = { matched: "#3fb950", drift: "#d29922", critical: "#f85149" };
  const statusLabel = { matched: "MATCHED", drift: "DRIFT", critical: "CRITICAL" };

  const rows = tuning.nodes.map((n) => {
    const color = statusColor[n.status];
    const label = statusLabel[n.status];
    const deltaStr = n.delta > 0 ? `+${n.delta}` : `${n.delta}`;
    const rec = recommendation(n);
    return `
      <tr>
        <td>${n.type}</td>
        <td>${n.actual}</td>
        <td>${n.desired}</td>
        <td>${deltaStr}</td>
        <td style="color:${color};font-weight:bold">${label}</td>
        <td>${rec}</td>
      </tr>`;
  }).join("");

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fleet Tuning -- CCC Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #0d1117; color: #c9d1d9;
    font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
    font-size: 16px; padding: 24px;
  }
  h1 { color: #58a6ff; font-size: 24px; margin-bottom: 16px; }
  .meta { color: #8b949e; margin-bottom: 24px; font-size: 14px; }
  .summary {
    display: flex; gap: 24px; margin-bottom: 24px; flex-wrap: wrap;
  }
  .summary-card {
    background: #161b22; border: 1px solid #30363d; border-radius: 6px;
    padding: 16px 24px; min-width: 140px; text-align: center;
  }
  .summary-card .label { font-size: 12px; color: #8b949e; text-transform: uppercase; }
  .summary-card .value { font-size: 28px; font-weight: bold; margin-top: 4px; }
  table {
    width: 100%; border-collapse: collapse; background: #161b22;
    border: 1px solid #30363d; border-radius: 6px; overflow: hidden;
  }
  th, td { padding: 12px 16px; text-align: left; border-bottom: 1px solid #30363d; }
  th { background: #21262d; color: #8b949e; font-size: 12px; text-transform: uppercase; }
  td { font-size: 16px; }
  tr:last-child td { border-bottom: none; }
  .ok { color: #3fb950; }
  .warn { color: #d29922; }
  .err { color: #f85149; }
  .refresh-note { margin-top: 16px; color: #8b949e; font-size: 12px; }
  .error-banner {
    background: #f8514922; border: 1px solid #f85149; border-radius: 6px;
    padding: 12px 16px; margin-bottom: 16px; color: #f85149; display: none;
  }
</style>
</head>
<body>
  <h1>Fleet Node Tuning</h1>
  <div class="meta">Updated: ${new Date().toISOString()} | Auto-refresh: 15s</div>
  <div id="error-banner" class="error-banner">Dispatcher unreachable</div>

  <div class="summary">
    <div class="summary-card">
      <div class="label">Pending Tasks</div>
      <div class="value">${tuning.pending_tasks}</div>
    </div>
    <div class="summary-card">
      <div class="label">Active Workers</div>
      <div class="value">${tuning.active_workers}</div>
    </div>
  </div>

  <table>
    <thead>
      <tr>
        <th>Node Type</th>
        <th>Actual</th>
        <th>Desired</th>
        <th>Delta</th>
        <th>Status</th>
        <th>Recommendation</th>
      </tr>
    </thead>
    <tbody>${rows}
    </tbody>
  </table>

  <p class="refresh-note">Page auto-refreshes every 15 seconds.</p>

  <script>
    setTimeout(function() { location.reload(); }, 15000);
  </script>
</body>
</html>`;
}

function renderErrorHTML(message) {
  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Fleet Tuning -- Error</title>
<style>
  body { background:#0d1117; color:#f85149; font-family:monospace; padding:24px; font-size:18px; }
</style>
</head>
<body>
  <h1>Fleet Tuning</h1>
  <p style="margin-top:16px">Error: ${message}</p>
  <p style="color:#8b949e;margin-top:8px">Retrying in 15 seconds...</p>
  <script>setTimeout(function(){location.reload()},15000);</script>
</body>
</html>`;
}

// ── Server ────────────────────────────────────────────────────────────────────

const server = http.createServer(async (req, res) => {
  if (req.method === "GET" && req.url === "/fleet-tune") {
    const config = loadTuneConfig();
    const healthUrl = process.env.DISPATCHER_HEALTH_URL || config.dispatcher_health_url || DISPATCHER_URL;
    try {
      const health = await fetchJSON(healthUrl);
      const tuning = computeTuning(health, config);
      const html = renderFleetTuneHTML(tuning);
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      res.end(html);
    } catch (err) {
      const html = renderErrorHTML(err.message);
      res.writeHead(502, { "Content-Type": "text/html; charset=utf-8" });
      res.end(html);
    }
  } else if (req.method === "GET" && req.url === "/fleet-tune/api") {
    const config = loadTuneConfig();
    const healthUrl = process.env.DISPATCHER_HEALTH_URL || config.dispatcher_health_url || DISPATCHER_URL;
    try {
      const health = await fetchJSON(healthUrl);
      const tuning = computeTuning(health, config);
      tuning.timestamp = new Date().toISOString();
      tuning.nodes.forEach((n) => (n.recommendation = recommendation(n)));
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify(tuning, null, 2));
    } catch (err) {
      res.writeHead(502, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: err.message }));
    }
  } else if (req.method === "GET" && req.url === "/") {
    res.writeHead(302, { Location: "/fleet-tune" });
    res.end();
  } else {
    res.writeHead(404, { "Content-Type": "text/plain" });
    res.end("Not found");
  }
});

server.listen(PORT, () => {
  console.log(`Dashboard server listening on http://0.0.0.0:${PORT}`);
  console.log(`Fleet tuning:  http://localhost:${PORT}/fleet-tune`);
  console.log(`Fleet API:     http://localhost:${PORT}/fleet-tune/api`);
  console.log(`Dispatcher:    ${DISPATCHER_URL}`);
  console.log(`Tune config:   ${TUNE_CONFIG_PATH}`);
});
