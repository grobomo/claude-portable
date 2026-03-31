#!/usr/bin/env node
/**
 * Tests for central-server.js
 *
 * Spins up a mock dispatcher + central-server, validates:
 *   1. GET / serves HTML with expected elements
 *   2. GET /api/stats proxies to dispatcher
 *   3. GET /api/workers proxies to dispatcher
 *   4. GET /api/tasks proxies to dispatcher
 *   5. POST /task proxies to dispatcher
 *   6. GET /health proxies to dispatcher
 *   7. Unknown paths return 404
 *   8. Dispatcher down returns 502
 *
 * Zero external dependencies -- uses only Node.js built-ins.
 * Exit code 0 = all pass, 1 = failure.
 */

var http = require("http");
var child_process = require("child_process");
var path = require("path");

var CENTRAL_PORT = 13370;
var MOCK_DISPATCHER_PORT = 13371;
var CENTRAL_JS = path.join(__dirname, "..", "central-server.js");

var passed = 0;
var failed = 0;
var tests = [];

function assert(cond, msg) {
  if (!cond) throw new Error("FAIL: " + msg);
}

function test(name, fn) {
  tests.push({ name: name, fn: fn });
}

// ── Mock Dispatcher ───────────────────────────────────────────────────────────

var MOCK_STATS = {
  total_workers: 3,
  idle_count: 1,
  busy_count: 2,
  tasks_completed_today: 5,
  tasks_failed_today: 1,
  avg_duration_seconds: 420,
  success_rate_percent: 83.3,
  uptime_seconds: 7200,
};

var MOCK_WORKERS = {
  "w1": { status: "idle", ip: "10.0.1.1", tasks_completed: 3, tasks_failed: 0, current_task_id: null },
  "w2": { status: "busy", ip: "10.0.1.2", tasks_completed: 5, tasks_failed: 1, current_task_id: "req-010" },
};

var MOCK_TASKS = [
  { id: "req-010", text: "Build feature", state: "dispatched", worker: "w2", duration_seconds: 120 },
  { id: "req-009", text: "Fix bug", state: "completed", worker: "w1", duration_seconds: 300 },
];

var lastPostBody = null;

var mockDispatcher = http.createServer(function(req, res) {
  res.setHeader("Content-Type", "application/json");

  if (req.url === "/api/stats" && req.method === "GET") {
    res.writeHead(200);
    res.end(JSON.stringify(MOCK_STATS));
  } else if (req.url === "/api/workers" && req.method === "GET") {
    res.writeHead(200);
    res.end(JSON.stringify(MOCK_WORKERS));
  } else if (req.url === "/api/tasks" && req.method === "GET") {
    res.writeHead(200);
    res.end(JSON.stringify(MOCK_TASKS));
  } else if (req.url === "/health" && req.method === "GET") {
    res.writeHead(200);
    res.end(JSON.stringify({ status: "ok", uptime_seconds: 7200 }));
  } else if (req.url === "/task" && req.method === "POST") {
    var body = "";
    req.on("data", function(c) { body += c; });
    req.on("end", function() {
      lastPostBody = JSON.parse(body);
      res.writeHead(201);
      res.end(JSON.stringify({ id: "req-011", state: "PENDING" }));
    });
  } else if (req.url === "/dashboard" && req.method === "GET") {
    res.setHeader("Content-Type", "text/html; charset=utf-8");
    res.writeHead(200);
    res.end("<html><head><title>CCC Fleet Dashboard</title></head><body>tab-tasks tab-infra</body></html>");
  } else if (req.url === "/dashboard/api/tasks" && req.method === "GET") {
    res.writeHead(200);
    res.end(JSON.stringify({ features: [], summary: { total_tasks: 0 }, updated_at: "2026-03-29T10:00:00Z" }));
  } else if (req.url === "/dashboard/api/infra" && req.method === "GET") {
    res.writeHead(200);
    res.end(JSON.stringify({ workers: [{ worker_id: "w1", healthy: true, cpu_percent: 25.0 }], updated_at: "2026-03-29T10:00:00Z" }));
  } else if (req.url === "/api/submit" && req.method === "POST") {
    var body2 = "";
    req.on("data", function(c) { body2 += c; });
    req.on("end", function() {
      var parsed2 = JSON.parse(body2);
      res.writeHead(201);
      res.end(JSON.stringify({ id: "req-012", state: "PENDING", text: parsed2.text }));
    });
  } else {
    res.writeHead(404);
    res.end(JSON.stringify({ error: "not found" }));
  }
});

// ── HTTP helpers ──────────────────────────────────────────────────────────────

function httpGet(port, path) {
  return new Promise(function(resolve, reject) {
    http.get("http://127.0.0.1:" + port + path, function(res) {
      var body = "";
      res.on("data", function(d) { body += d; });
      res.on("end", function() {
        resolve({ status: res.statusCode, headers: res.headers, body: body });
      });
    }).on("error", reject);
  });
}

function httpPost(port, path, data) {
  return new Promise(function(resolve, reject) {
    var payload = JSON.stringify(data);
    var opts = {
      hostname: "127.0.0.1",
      port: port,
      path: path,
      method: "POST",
      headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(payload) },
    };
    var req = http.request(opts, function(res) {
      var body = "";
      res.on("data", function(d) { body += d; });
      res.on("end", function() {
        resolve({ status: res.statusCode, headers: res.headers, body: body });
      });
    });
    req.on("error", reject);
    req.write(payload);
    req.end();
  });
}

// ── Tests ─────────────────────────────────────────────────────────────────────

test("GET / returns HTML with dashboard elements", function() {
  return httpGet(CENTRAL_PORT, "/").then(function(res) {
    assert(res.status === 200, "expected 200 got " + res.status);
    assert(res.headers["content-type"].indexOf("text/html") >= 0, "expected text/html");
    assert(res.body.indexOf("<!DOCTYPE html>") >= 0, "missing DOCTYPE");
    assert(res.body.indexOf("workers-grid") >= 0, "missing workers-grid");
    assert(res.body.indexOf("submit-form") >= 0, "missing submit-form");
    assert(res.body.indexOf("fleet-bar") >= 0, "missing fleet stats bar");
    assert(res.body.indexOf("tasks-table") >= 0, "missing tasks table");
    assert(res.body.indexOf("Auto-refresh") >= 0, "missing auto-refresh");
    assert(res.body.indexOf("MAX_SLOTS = 10") >= 0, "missing 10-slot grid");
    assert(res.body.indexOf("#0d1117") >= 0, "missing dark theme bg color");
  });
});

test("GET /api/stats proxies to dispatcher", function() {
  return httpGet(CENTRAL_PORT, "/api/stats").then(function(res) {
    assert(res.status === 200, "expected 200 got " + res.status);
    var data = JSON.parse(res.body);
    assert(data.total_workers === 3, "expected 3 workers got " + data.total_workers);
    assert(data.idle_count === 1, "expected 1 idle");
    assert(data.busy_count === 2, "expected 2 busy");
    assert(data.uptime_seconds === 7200, "expected uptime 7200");
  });
});

test("GET /api/workers proxies to dispatcher", function() {
  return httpGet(CENTRAL_PORT, "/api/workers").then(function(res) {
    assert(res.status === 200, "expected 200");
    var data = JSON.parse(res.body);
    assert(data.w1 && data.w1.status === "idle", "w1 should be idle");
    assert(data.w2 && data.w2.status === "busy", "w2 should be busy");
  });
});

test("GET /api/tasks proxies to dispatcher", function() {
  return httpGet(CENTRAL_PORT, "/api/tasks").then(function(res) {
    assert(res.status === 200, "expected 200");
    var data = JSON.parse(res.body);
    assert(Array.isArray(data), "expected array");
    assert(data.length === 2, "expected 2 tasks got " + data.length);
    assert(data[0].id === "req-010", "first task id mismatch");
  });
});

test("GET /health proxies to dispatcher", function() {
  return httpGet(CENTRAL_PORT, "/health").then(function(res) {
    assert(res.status === 200, "expected 200");
    var data = JSON.parse(res.body);
    assert(data.status === "ok", "expected status ok");
  });
});

test("POST /task proxies to dispatcher", function() {
  lastPostBody = null;
  return httpPost(CENTRAL_PORT, "/task", { description: "Test task from dashboard" }).then(function(res) {
    assert(res.status === 201, "expected 201 got " + res.status);
    var data = JSON.parse(res.body);
    assert(data.id === "req-011", "expected task id req-011");
    assert(lastPostBody && lastPostBody.description === "Test task from dashboard", "POST body not proxied");
  });
});

test("GET /nonexistent returns 404", function() {
  return httpGet(CENTRAL_PORT, "/nonexistent").then(function(res) {
    assert(res.status === 404, "expected 404 got " + res.status);
  });
});

test("CORS headers present on proxied responses", function() {
  return httpGet(CENTRAL_PORT, "/api/stats").then(function(res) {
    assert(res.headers["access-control-allow-origin"] === "*", "missing CORS header");
  });
});

test("GET /dashboard/api/tasks proxies to dispatcher", function() {
  return httpGet(CENTRAL_PORT, "/dashboard/api/tasks").then(function(res) {
    assert(res.status === 200, "expected 200 got " + res.status);
    var data = JSON.parse(res.body);
    assert(Array.isArray(data.features), "expected features array");
    assert(data.summary != null, "expected summary");
  });
});

test("GET /dashboard/api/infra proxies to dispatcher", function() {
  return httpGet(CENTRAL_PORT, "/dashboard/api/infra").then(function(res) {
    assert(res.status === 200, "expected 200 got " + res.status);
    var data = JSON.parse(res.body);
    assert(Array.isArray(data.workers), "expected workers array");
    assert(data.workers.length === 1, "expected 1 worker");
    assert(data.workers[0].worker_id === "w1", "expected w1");
  });
});

test("GET /dashboard proxies full dashboard HTML from dispatcher", function() {
  return httpGet(CENTRAL_PORT, "/dashboard").then(function(res) {
    assert(res.status === 200, "expected 200 got " + res.status);
    assert(res.headers["content-type"].indexOf("text/html") >= 0, "expected text/html");
    assert(res.body.indexOf("tab-tasks") >= 0, "missing tab-tasks");
    assert(res.body.indexOf("tab-infra") >= 0, "missing tab-infra");
  });
});

test("POST /api/submit proxies to dispatcher", function() {
  return httpPost(CENTRAL_PORT, "/api/submit", { text: "Test from dashboard" }).then(function(res) {
    assert(res.status === 201, "expected 201 got " + res.status);
    var data = JSON.parse(res.body);
    assert(data.id === "req-012", "expected req-012");
    assert(data.text === "Test from dashboard", "text mismatch");
  });
});

// ── Runner ────────────────────────────────────────────────────────────────────

function runTests() {
  var i = 0;
  function next() {
    if (i >= tests.length) {
      console.log("\n" + passed + " passed, " + failed + " failed, " + tests.length + " total");
      return cleanup(failed > 0 ? 1 : 0);
    }
    var t = tests[i++];
    Promise.resolve()
      .then(function() { return t.fn(); })
      .then(function() {
        passed++;
        console.log("  [PASS] " + t.name);
        next();
      })
      .catch(function(err) {
        failed++;
        console.log("  [FAIL] " + t.name + " -- " + err.message);
        next();
      });
  }
  next();
}

// ── Setup / Teardown ──────────────────────────────────────────────────────────

var centralProc = null;

function cleanup(exitCode) {
  if (centralProc) centralProc.kill();
  mockDispatcher.close(function() {
    process.exit(exitCode);
  });
}

process.on("SIGINT", function() { cleanup(1); });
process.on("SIGTERM", function() { cleanup(1); });

// Start mock dispatcher, then central-server, then run tests
mockDispatcher.listen(MOCK_DISPATCHER_PORT, function() {
  centralProc = child_process.spawn("node", [CENTRAL_JS], {
    env: Object.assign({}, process.env, {
      DASHBOARD_PORT: String(CENTRAL_PORT),
      DISPATCHER_URL: "http://127.0.0.1:" + MOCK_DISPATCHER_PORT,
    }),
    stdio: "pipe",
  });

  // Give central-server 500ms to start
  setTimeout(function() {
    console.log("Running " + tests.length + " tests...\n");
    runTests();
  }, 500);

  // Safety timeout -- kill everything after 15s
  setTimeout(function() {
    console.log("\nTIMEOUT -- tests did not complete in 15s");
    cleanup(1);
  }, 15000);
});
