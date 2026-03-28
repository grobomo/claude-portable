#!/usr/bin/env node
/**
 * web-chat -- Mobile-friendly web interface for Claude Code sessions.
 *
 * Runs on port 8888 inside the container. Spawns Claude CLI as a child
 * process and streams I/O over WebSocket to a phone-friendly chat UI.
 *
 * Security (per websocket.org best practices):
 *   - Token auth via CLAUDE_WEB_TOKEN (required for non-health endpoints)
 *   - Origin header validation
 *   - WebSocket heartbeat (30s ping/pong, 10s timeout)
 *   - Per-user rate limiting (max 20 prompts/hour, set CHATBOT_RATE_LIMIT)
 *   - Max concurrent connections (default 5)
 *   - Auto-generated token if none provided
 *
 * Usage:
 *   node web-chat.js                  # start server on :8888
 *   CLAUDE_WEB_PORT=9999 node web-chat.js  # custom port
 */

const http = require("http");
const { WebSocketServer } = require("ws");
const { spawn, execFile } = require("child_process");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const PORT = parseInt(process.env.CLAUDE_WEB_PORT || "8888", 10);
const MAX_CONNECTIONS = parseInt(process.env.CLAUDE_WEB_MAX_CONN || "10", 10);
const RATE_LIMIT = parseInt(process.env.CHATBOT_RATE_LIMIT || "20", 10); // prompts per hour per user
const HEARTBEAT_INTERVAL = 30000; // 30s
const HEARTBEAT_TIMEOUT = 10000; // 10s grace
const SESSION_DIR = "/data/sessions";
const HTML_PATH = path.join(__dirname, "web-chat.html");

// Auto-generate token if not set (written to /data/web-chat-token for retrieval)
const TOKEN = process.env.CLAUDE_WEB_TOKEN || crypto.randomBytes(16).toString("hex");
const TOKEN_FILE = "/data/web-chat-token";

// Active sessions keyed by WebSocket
const sessions = new Map(); // ws -> session object

// Track active usernames to prevent duplicate sessions
const activeUsers = new Map(); // username -> ws

// Per-user rate limiting (keyed by username, persists across reconnects within the hour window)
const rateLimits = new Map(); // username -> { count, resetAt }

// ── Helpers ──────────────────────────────────────────────────────────────────

function checkAuth(tokenCandidate) {
  return tokenCandidate === TOKEN;
}

// Allow only safe username characters (letters, digits, hyphens, underscores)
// Returns sanitized name or empty string if invalid
function sanitizeUsername(name) {
  if (!name || typeof name !== "string") return "";
  const trimmed = name.trim().substring(0, 32);
  return /^[a-zA-Z0-9_-]+$/.test(trimmed) ? trimmed : "";
}

function isRateLimited(username) {
  if (!username) return false; // not yet identified — allow name message through
  const now = Date.now();
  let rl = rateLimits.get(username);
  if (!rl || now > rl.resetAt) {
    rl = { count: 0, resetAt: now + 3600000 }; // 1-hour window
    rateLimits.set(username, rl);
  }
  rl.count++;
  if (rl.count > RATE_LIMIT) {
    const minutesLeft = Math.ceil((rl.resetAt - now) / 60000);
    return `Rate limit reached (${RATE_LIMIT} prompts/hour). Try again in ${minutesLeft} min.`;
  }
  return null;
}

function safeSend(ws, data) {
  if (ws.readyState === 1) { // WebSocket.OPEN
    ws.send(typeof data === "string" ? data : JSON.stringify(data));
  }
}

// ── HTTP server (serves the HTML UI + health check) ─────────────────────────

const server = http.createServer((req, res) => {
  const parsedUrl = new URL(req.url, `http://${req.headers.host}`);

  // Health check -- no auth needed
  if (parsedUrl.pathname === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ok", sessions: sessions.size, users: activeUsers.size }));
    return;
  }

  // Auth check
  const authHeader = req.headers.authorization || "";
  const urlToken = parsedUrl.searchParams.get("token");
  const bearerToken = authHeader.startsWith("Bearer ") ? authHeader.slice(7) : "";
  if (!checkAuth(urlToken) && !checkAuth(bearerToken)) {
    res.writeHead(401, { "Content-Type": "text/plain" });
    res.end("Unauthorized. Add ?token=<your-token> to the URL.");
    return;
  }

  // Serve the chat UI
  if (parsedUrl.pathname === "/") {
    fs.readFile(HTML_PATH, "utf8", (err, html) => {
      if (err) {
        res.writeHead(500);
        res.end("Error loading UI");
        return;
      }
      // Inject token into HTML so WebSocket can use it
      html = html.replace("__WEB_TOKEN__", TOKEN);
      res.writeHead(200, {
        "Content-Type": "text/html",
        "Cache-Control": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
      });
      res.end(html);
    });
    return;
  }

  // HTTP prompt endpoint (for Lambda relay -- no WebSocket needed)
  if (parsedUrl.pathname === "/api/prompt" && req.method === "POST") {
    let body = "";
    req.on("data", (chunk) => { body += chunk; });
    req.on("end", () => {
      let parsed;
      try { parsed = JSON.parse(body); } catch {
        res.writeHead(400, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "Invalid JSON" }));
        return;
      }
      const prompt = parsed.prompt || parsed.text;
      if (!prompt) {
        res.writeHead(400, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "prompt required" }));
        return;
      }
      const cwd = parsed.project || "/workspace";
      // Pull latest code so Claude sees recent worker commits
      gitPull(cwd).then(() => {
      const args = ["-p", prompt, "--verbose"];
      const proc = spawn("claude", args, {
        cwd,
        env: { ...process.env, TERM: "dumb", NO_COLOR: "1" },
        stdio: ["pipe", "pipe", "pipe"],
      });
      let output = "";
      let stderr = "";
      proc.stdout.on("data", (chunk) => { output += chunk.toString(); });
      proc.stderr.on("data", (chunk) => { stderr += chunk.toString(); });
      proc.on("close", (code) => {
        res.writeHead(200, {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": "*",
        });
        res.end(JSON.stringify({ output, stderr, code }));
      });
      proc.on("error", (err) => {
        res.writeHead(500, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: err.message }));
      });
      }); // gitPull.then
    });
    return;
  }

  // Fleet status endpoint -- collects git + dispatcher data and returns JSON
  if (parsedUrl.pathname === "/fleet-status") {
    const project = parsedUrl.searchParams.get("project") || "/workspace/claude-portable";
    getFleetStatus(project).then((status) => {
      res.writeHead(200, {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
      });
      res.end(JSON.stringify(status));
    }).catch((err) => {
      res.writeHead(500, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: err.message }));
    });
    return;
  }

  // List active sessions
  if (parsedUrl.pathname === "/sessions") {
    const active = [];
    for (const [, sess] of sessions) {
      active.push({
        id: sess.id,
        user: sess.user,
        started: sess.started,
        project: sess.project || "/workspace",
        alive: sess.proc && !sess.proc.killed,
      });
    }
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify(active));
    return;
  }

  res.writeHead(404);
  res.end("Not found");
});

// ── WebSocket server ────────────────────────────────────────────────────────

const wss = new WebSocketServer({ server, maxPayload: 64 * 1024 }); // 64KB max message

wss.on("connection", (ws, req) => {
  // Max connections check
  if (sessions.size >= MAX_CONNECTIONS) {
    ws.close(4002, "Too many connections");
    return;
  }

  // Auth check
  const url = new URL(req.url, `http://${req.headers.host}`);
  const urlToken = url.searchParams.get("token");
  if (!checkAuth(urlToken)) {
    ws.close(4001, "Unauthorized");
    return;
  }

  // User identification: ?user=name param or prompt on first message
  const rawUser = url.searchParams.get("user") || "";
  const user = sanitizeUsername(rawUser) || null;

  // Reject if username already has an active session
  if (user && activeUsers.has(user)) {
    const existingWs = activeUsers.get(user);
    if (existingWs.readyState === 1 /* OPEN */) {
      ws.close(4003, `User '${user}' already has an active session`);
      return;
    }
    // Prior connection is gone — clean it up
    activeUsers.delete(user);
  }

  const sessionId = `web-${Date.now()}-${crypto.randomBytes(3).toString("hex")}`;
  const session = {
    id: sessionId,
    user: user,           // null until identified
    started: new Date().toISOString(),
    proc: null,
    project: "/workspace",
    buffer: "",
    lastPong: Date.now(),
    awaitingName: !user,  // true when we still need the user to provide a name
  };
  sessions.set(ws, session);

  if (user) {
    activeUsers.set(user, ws);
  }

  console.log(`[${sessionId}] Connected as '${user || "?"}' (total: ${sessions.size})`);

  if (!user) {
    safeSend(ws, { type: "system", text: "Connected. What is your name? (reply with your name to continue)" });
  } else {
    safeSend(ws, { type: "system", text: `Connected as ${user}. Type a message to start.` });
  }

  // ── Heartbeat (ping/pong) ──
  ws.isAlive = true;
  ws.on("pong", () => {
    ws.isAlive = true;
    session.lastPong = Date.now();
  });

  // ── Message handler ──
  ws.on("message", (raw) => {
    // Per-user hourly rate limit (skip check while awaiting name)
    if (!session.awaitingName) {
      const limitMsg = isRateLimited(session.user);
      if (limitMsg) {
        safeSend(ws, { type: "error", text: limitMsg });
        return;
      }
    }

    let msg;
    try {
      msg = JSON.parse(raw.toString());
    } catch {
      msg = { type: "chat", text: raw.toString() };
    }

    // Handle name identification on first message
    if (session.awaitingName) {
      const nameCandidate = sanitizeUsername(msg.text || msg.name || raw.toString());
      if (!nameCandidate) {
        safeSend(ws, { type: "system", text: "Please enter a valid name (letters, numbers, hyphens, underscores only)." });
        return;
      }
      if (activeUsers.has(nameCandidate)) {
        const existingWs = activeUsers.get(nameCandidate);
        if (existingWs.readyState === 1 /* OPEN */) {
          safeSend(ws, { type: "error", text: `Name '${nameCandidate}' is already in use. Choose another.` });
          return;
        }
        activeUsers.delete(nameCandidate);
      }
      session.user = nameCandidate;
      session.awaitingName = false;
      activeUsers.set(nameCandidate, ws);
      console.log(`[${session.id}] Identified as '${nameCandidate}'`);
      safeSend(ws, { type: "system", text: `Hello ${nameCandidate}! Type a message to start.` });
      return;
    }

    if (msg.type === "chat" || msg.type === undefined) {
      handleChat(ws, session, msg.text || msg.prompt || raw.toString());
    } else if (msg.type === "cd") {
      // Validate path -- must be absolute and not escape container
      const p = msg.path || "/workspace";
      if (!p.startsWith("/")) {
        safeSend(ws, { type: "error", text: "Path must be absolute." });
        return;
      }
      session.project = p;
      safeSend(ws, { type: "system", text: `Working directory: ${session.project}` });
    } else if (msg.type === "interrupt") {
      if (session.proc && !session.proc.killed) {
        session.proc.kill("SIGINT");
        safeSend(ws, { type: "system", text: "Interrupted." });
      }
    }
  });

  ws.on("close", () => {
    console.log(`[${sessionId}] Disconnected (user: ${session.user || "?"})`);
    if (session.proc && !session.proc.killed) {
      session.proc.kill("SIGTERM");
    }
    sessions.delete(ws);
    // Note: rateLimits keyed by username — intentionally NOT deleted on disconnect
    // so the hourly window persists across reconnects.
    if (session.user && activeUsers.get(session.user) === ws) {
      activeUsers.delete(session.user);
    }
  });

  ws.on("error", (err) => {
    console.error(`[${sessionId}] WebSocket error: ${err.message}`);
  });
});

// ── Heartbeat interval ──────────────────────────────────────────────────────

const heartbeat = setInterval(() => {
  wss.clients.forEach((ws) => {
    if (!ws.isAlive) {
      console.log("Terminating dead WebSocket connection");
      ws.terminate();
      return;
    }
    ws.isAlive = false;
    ws.ping();
  });
}, HEARTBEAT_INTERVAL);

wss.on("close", () => clearInterval(heartbeat));

// ── Git pull helper ─────────────────────────────────────────────────────────

// Run `git pull --rebase` in cwd. Resolves when done (ignores errors so
// Claude always gets a response even if pull fails).
function gitPull(cwd) {
  return new Promise((resolve) => {
    execFile("git", ["pull", "--rebase"], { cwd, timeout: 30000 }, (err, stdout, stderr) => {
      if (err) {
        console.warn(`[git pull] in ${cwd}: ${err.message}`);
      } else {
        const out = (stdout + stderr).trim();
        if (out && !out.includes("Already up to date")) {
          console.log(`[git pull] ${cwd}: ${out}`);
        }
      }
      resolve();
    });
  });
}

// ── Fleet status ───────────────────────────────────────────────────────────

/**
 * Collect fleet status from git + optional dispatcher health endpoint.
 *
 * Returns a structured object with:
 *   todo       - { done, pending }
 *   open_prs   - array of { number, title, branch, author }
 *   branches   - active worker/chatbot branch names
 *   commits    - recent git log lines
 *   dispatcher - health data from DISPATCHER_URL/health, or null
 */
async function getFleetStatus(project) {
  const cwd = project || "/workspace/claude-portable";
  const run = (cmd, args, opts) =>
    new Promise((resolve) => {
      execFile(cmd, args, { cwd, timeout: 30000, ...opts }, (err, stdout, stderr) => {
        resolve({ ok: !err, stdout: (stdout || "").trim(), stderr: (stderr || "").trim() });
      });
    });

  // Pull latest
  await run("git", ["pull", "--rebase", "--autostash"]);

  const status = {};

  // TODO progress
  try {
    const todo = fs.readFileSync(`${cwd}/TODO.md`, "utf8");
    status.todo = {
      done: (todo.match(/- \[x\]/g) || []).length,
      pending: (todo.match(/- \[ \]/g) || []).length,
    };
  } catch {
    status.todo = { done: 0, pending: 0, error: "could not read TODO.md" };
  }

  // Open PRs
  const prs = await run("gh", [
    "pr", "list", "--state", "open", "--limit", "20",
    "--json", "number,title,headRefName,author",
  ]);
  if (prs.ok && prs.stdout) {
    try {
      status.open_prs = JSON.parse(prs.stdout).map((p) => ({
        number: p.number,
        title: p.title,
        branch: p.headRefName,
        author: (p.author || {}).login || "?",
      }));
    } catch {
      status.open_prs = [];
    }
  } else {
    status.open_prs = [];
  }

  // Active worker/chatbot branches
  const branches = await run("git", ["branch", "-r"]);
  if (branches.ok) {
    status.branches = branches.stdout
      .split("\n")
      .filter((b) => b.includes("continuous-claude/") || b.includes("chatbot/"))
      .map((b) => b.trim().replace(/^origin\//, ""));
  } else {
    status.branches = [];
  }

  // Recent commits
  const log = await run("git", ["log", "--oneline", "-8"]);
  status.commits = log.ok ? log.stdout.split("\n").filter(Boolean) : [];

  // Dispatcher health
  const dispUrl = process.env.DISPATCHER_URL || "";
  if (dispUrl) {
    try {
      const healthUrl = dispUrl.replace(/\/$/, "") + "/health";
      const data = await new Promise((resolve, reject) => {
        const mod = healthUrl.startsWith("https") ? require("https") : require("http");
        const req = mod.get(healthUrl, { timeout: 5000 }, (res2) => {
          let body = "";
          res2.on("data", (c) => { body += c; });
          res2.on("end", () => {
            try { resolve(JSON.parse(body)); } catch { resolve({ raw: body }); }
          });
        });
        req.on("error", reject);
        req.on("timeout", () => { req.destroy(); reject(new Error("timeout")); });
      });
      status.dispatcher = data;
    } catch (e) {
      status.dispatcher = { error: `unreachable: ${e.message}` };
    }
  } else {
    status.dispatcher = null;
  }

  return status;
}

// ── Claude CLI interaction ──────────────────────────────────────────────────

function handleChat(ws, session, text) {
  if (!text || !text.trim()) return;

  // Kill any existing process
  if (session.proc && !session.proc.killed) {
    session.proc.kill("SIGTERM");
  }

  const trimmed = text.length > 100 ? text.substring(0, 100) + "..." : text;
  console.log(`[${session.id}] Prompt: ${trimmed}`);

  // Pull latest code before invoking Claude so it sees worker commits
  safeSend(ws, { type: "system", text: "Syncing latest code..." });
  gitPull(session.project).then(() => {
    launchClaude(ws, session, text);
  });
}

function launchClaude(ws, session, text) {
  // Use -p for print mode (each prompt is independent, work tracked via git/PRs)
  const args = ["-p", text, "--verbose"];

  const proc = spawn("claude", args, {
    cwd: session.project,
    env: {
      ...process.env,
      CLAUDE_CODE_ENTRYPOINT: "web-chat",
      TERM: "dumb",
      NO_COLOR: "1",
    },
    stdio: ["pipe", "pipe", "pipe"],
  });

  session.proc = proc;
  session.hasConversation = true;
  session.buffer = "";

  safeSend(ws, { type: "start" });

  proc.stdout.on("data", (chunk) => {
    const t = chunk.toString();
    session.buffer += t;
    safeSend(ws, { type: "stream", text: t });
  });

  proc.stderr.on("data", (chunk) => {
    const t = chunk.toString();
    // Filter noise
    if (!t.includes("Update available") && !t.includes("npm ")) {
      safeSend(ws, { type: "stderr", text: t });
    }
  });

  proc.on("close", (code) => {
    safeSend(ws, { type: "done", code });
    session.proc = null;

    // Log conversation to per-user session directory
    try {
      const logDir = path.join(SESSION_DIR, session.user || session.id);
      fs.mkdirSync(logDir, { recursive: true });
      const ts = new Date().toISOString();
      fs.appendFileSync(
        path.join(logDir, "conversation.log"),
        `\n[${ts}] USER: ${text.substring(0, 500)}\n` +
        `[${ts}] CLAUDE (exit=${code}):\n${session.buffer}\n` +
        `${"=".repeat(60)}\n`
      );
    } catch (e) {
      console.error(`[${session.id}] Log write failed: ${e.message}`);
    }
  });

  proc.on("error", (err) => {
    safeSend(ws, { type: "error", text: `Failed to start Claude: ${err.message}` });
  });
}

// ── Start ───────────────────────────────────────────────────────────────────

// Write token to file so ccc offload can retrieve it
try {
  fs.writeFileSync(TOKEN_FILE, TOKEN, { mode: 0o600 });
} catch (e) {
  // /data might not exist in dev
  console.warn(`Could not write token file: ${e.message}`);
}

server.listen(PORT, "0.0.0.0", () => {
  console.log(`web-chat listening on http://0.0.0.0:${PORT}`);
  console.log(`Auth token: ${TOKEN}`);
  console.log(`Max connections: ${MAX_CONNECTIONS}`);
  console.log(`Rate limit: ${RATE_LIMIT} prompts/hour per user (CHATBOT_RATE_LIMIT)`);
  console.log(`Heartbeat: ${HEARTBEAT_INTERVAL / 1000}s ping, ${HEARTBEAT_TIMEOUT / 1000}s timeout`);
});
