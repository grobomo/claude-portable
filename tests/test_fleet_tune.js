#!/usr/bin/env node
/**
 * Tests for fleet-tune system:
 *   - monitoring-dashboard/central-server.js /fleet-tune endpoint
 *   - scripts/fleet/fleet-tune.sh calculations
 *
 * Spins up a mock dispatcher, validates tuning logic and HTML rendering.
 * Zero external dependencies -- uses only Node.js built-ins.
 * Exit code 0 = all pass, 1 = failure.
 */

var http = require("http");
var child_process = require("child_process");
var path = require("path");

var DASHBOARD_PORT = 14370;
var MOCK_DISPATCHER_PORT = 14371;
var CENTRAL_JS = path.join(__dirname, "..", "monitoring-dashboard", "central-server.js");
var FLEET_TUNE_SH = path.join(__dirname, "..", "scripts", "fleet", "fleet-tune.sh");

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

var mockHealth = {
  status: "running",
  pending_tasks: 15,
  active_workers: 3,
  fleet_roster: {
    "worker-abc1": { status: "busy" },
    "worker-def2": { status: "busy" },
    "worker-ghi3": { status: "idle" },
    "monitor-xyz1": { status: "healthy" },
  },
};

var mockDispatcher = http.createServer(function(req, res) {
  if (req.url === "/health" && req.method === "GET") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify(mockHealth));
  } else {
    res.writeHead(404);
    res.end("not found");
  }
});

// ── HTTP helper ───────────────────────────────────────────────────────────────

function httpGet(port, urlPath) {
  return new Promise(function(resolve, reject) {
    http.get("http://127.0.0.1:" + port + urlPath, function(res) {
      var body = "";
      res.on("data", function(d) { body += d; });
      res.on("end", function() {
        resolve({ status: res.statusCode, headers: res.headers, body: body });
      });
    }).on("error", reject);
  });
}

// ── Tests: /fleet-tune/api ────────────────────────────────────────────────────

test("GET /fleet-tune/api returns valid JSON with correct schema", function() {
  return httpGet(DASHBOARD_PORT, "/fleet-tune/api").then(function(res) {
    assert(res.status === 200, "expected 200 got " + res.status);
    var data = JSON.parse(res.body);
    assert(data.pending_tasks === 15, "expected 15 pending_tasks got " + data.pending_tasks);
    assert(data.active_workers === 3, "expected 3 active_workers");
    assert(Array.isArray(data.nodes), "expected nodes array");
    assert(data.nodes.length === 3, "expected 3 node types");
    assert(data.timestamp, "missing timestamp");
  });
});

test("API calculates workers = max(pending*2, 10) = 30", function() {
  return httpGet(DASHBOARD_PORT, "/fleet-tune/api").then(function(res) {
    var data = JSON.parse(res.body);
    var workers = data.nodes.find(function(n) { return n.type === "Workers"; });
    assert(workers.desired === 30, "expected desired 30 got " + workers.desired);
    assert(workers.actual === 3, "expected actual 3 got " + workers.actual);
    assert(workers.delta === 27, "expected delta 27 got " + workers.delta);
  });
});

test("API calculates monitors = max(30/20, 1) = 1", function() {
  return httpGet(DASHBOARD_PORT, "/fleet-tune/api").then(function(res) {
    var data = JSON.parse(res.body);
    var monitors = data.nodes.find(function(n) { return n.type === "Monitors"; });
    assert(monitors.desired === 1, "expected desired 1 got " + monitors.desired);
    assert(monitors.actual === 1, "expected actual 1 got " + monitors.actual);
    assert(monitors.delta === 0, "expected delta 0 got " + monitors.delta);
    assert(monitors.status === "matched", "expected matched got " + monitors.status);
  });
});

test("API sets dispatchers desired = 1, status matched", function() {
  return httpGet(DASHBOARD_PORT, "/fleet-tune/api").then(function(res) {
    var data = JSON.parse(res.body);
    var dispatchers = data.nodes.find(function(n) { return n.type === "Dispatchers"; });
    assert(dispatchers.desired === 1, "expected desired 1");
    assert(dispatchers.actual === 1, "expected actual 1");
    assert(dispatchers.status === "matched", "expected matched");
  });
});

test("API marks workers as critical when delta > 50%", function() {
  return httpGet(DASHBOARD_PORT, "/fleet-tune/api").then(function(res) {
    var data = JSON.parse(res.body);
    var workers = data.nodes.find(function(n) { return n.type === "Workers"; });
    assert(workers.status === "critical", "expected critical got " + workers.status);
  });
});

test("API includes recommendation strings", function() {
  return httpGet(DASHBOARD_PORT, "/fleet-tune/api").then(function(res) {
    var data = JSON.parse(res.body);
    var workers = data.nodes.find(function(n) { return n.type === "Workers"; });
    assert(workers.recommendation === "Add 27 workers", "expected 'Add 27 workers' got '" + workers.recommendation + "'");
    var monitors = data.nodes.find(function(n) { return n.type === "Monitors"; });
    assert(monitors.recommendation === "Monitors OK", "expected 'Monitors OK'");
  });
});

// ── Tests: /fleet-tune HTML ───────────────────────────────────────────────────

test("GET /fleet-tune returns HTML with color coding", function() {
  return httpGet(DASHBOARD_PORT, "/fleet-tune").then(function(res) {
    assert(res.status === 200, "expected 200 got " + res.status);
    assert(res.headers["content-type"].indexOf("text/html") >= 0, "expected text/html");
    var body = res.body;
    assert(body.indexOf("#3fb950") >= 0, "missing green color");
    assert(body.indexOf("#f85149") >= 0, "missing red color");
    assert(body.indexOf("#d29922") >= 0, "missing yellow color");
    assert(body.indexOf("<table") >= 0, "missing table");
    assert(body.indexOf("CRITICAL") >= 0 || body.indexOf("MATCHED") >= 0, "missing status labels");
    assert(body.indexOf("setTimeout") >= 0, "missing auto-refresh");
  });
});

test("GET /fleet-tune includes summary cards", function() {
  return httpGet(DASHBOARD_PORT, "/fleet-tune").then(function(res) {
    assert(res.body.indexOf("Pending Tasks") >= 0, "missing Pending Tasks card");
    assert(res.body.indexOf("Active Workers") >= 0, "missing Active Workers card");
    assert(res.body.indexOf("15") >= 0, "missing pending count 15");
  });
});

test("GET /fleet-tune has dark theme", function() {
  return httpGet(DASHBOARD_PORT, "/fleet-tune").then(function(res) {
    assert(res.body.indexOf("#0d1117") >= 0, "missing dark bg");
    assert(res.body.indexOf("#161b22") >= 0, "missing card bg");
  });
});

// ── Tests: edge cases ─────────────────────────────────────────────────────────

test("GET / redirects to /fleet-tune", function() {
  return new Promise(function(resolve, reject) {
    http.get({
      hostname: "127.0.0.1",
      port: DASHBOARD_PORT,
      path: "/",
      headers: {},
    }, function(res) {
      assert(res.statusCode === 302, "expected 302 got " + res.statusCode);
      assert(res.headers.location === "/fleet-tune", "expected redirect to /fleet-tune");
      resolve();
    }).on("error", reject);
  });
});

test("GET /nonexistent returns 404", function() {
  return httpGet(DASHBOARD_PORT, "/nonexistent").then(function(res) {
    assert(res.status === 404, "expected 404 got " + res.status);
  });
});

// ── Tests: zero-pending scenario ──────────────────────────────────────────────

test("With 0 pending tasks, desired workers = minimum (10)", function() {
  // Temporarily change mock data
  var origPending = mockHealth.pending_tasks;
  mockHealth.pending_tasks = 0;
  return httpGet(DASHBOARD_PORT, "/fleet-tune/api").then(function(res) {
    mockHealth.pending_tasks = origPending;
    var data = JSON.parse(res.body);
    var workers = data.nodes.find(function(n) { return n.type === "Workers"; });
    assert(workers.desired === 10, "expected minimum 10 got " + workers.desired);
  });
});

// ── Tests: fleet-tune.sh (shell script) ───────────────────────────────────────

test("fleet-tune.sh --json outputs valid JSON", function() {
  return new Promise(function(resolve, reject) {
    // Write temp config pointing at mock dispatcher
    var fs = require("fs");
    var os = require("os");
    var tmpConfig = path.join(os.tmpdir(), "test-tune-config-" + Date.now() + ".json");
    fs.writeFileSync(tmpConfig, JSON.stringify({
      worker_ratio: 2,
      worker_minimum: 10,
      monitor_ratio: 20,
      monitor_minimum: 1,
      dispatcher_count: 1,
      dispatcher_health_url: "http://127.0.0.1:" + MOCK_DISPATCHER_PORT + "/health",
      drift_threshold_percent: 20,
      critical_threshold_percent: 50,
    }));

    child_process.exec(
      "bash " + FLEET_TUNE_SH + " --json --config " + tmpConfig,
      { timeout: 10000 },
      function(err, stdout, stderr) {
        try {
          fs.unlinkSync(tmpConfig);
        } catch (e) {}
        if (err) return reject(new Error("script failed: " + stderr));
        try {
          var data = JSON.parse(stdout);
          assert(data.fleet_state.pending_tasks === 15, "expected 15 pending");
          assert(data.desired.workers === 30, "expected 30 desired workers");
          assert(data.actual.workers === 3, "expected 3 actual workers");
          assert(data.delta.workers === 27, "expected delta 27");
          assert(data.status.workers === "critical", "expected critical");
          assert(data.recommendations.length === 3, "expected 3 recommendations");
          resolve();
        } catch (e) {
          reject(e);
        }
      }
    );
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

mockDispatcher.listen(MOCK_DISPATCHER_PORT, function() {
  centralProc = child_process.spawn("node", [CENTRAL_JS], {
    env: Object.assign({}, process.env, {
      DASHBOARD_PORT: String(DASHBOARD_PORT),
      DISPATCHER_HEALTH_URL: "http://127.0.0.1:" + MOCK_DISPATCHER_PORT + "/health",
    }),
    stdio: "pipe",
  });

  setTimeout(function() {
    console.log("Running " + tests.length + " fleet-tune tests...\n");
    runTests();
  }, 500);

  setTimeout(function() {
    console.log("\nTIMEOUT -- tests did not complete in 15s");
    cleanup(1);
  }, 15000);
});
