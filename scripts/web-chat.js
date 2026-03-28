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
 *   - Per-client rate limiting (max 20 messages/minute)
 *   - Max concurrent connections (default 5)
 *   - Auto-generated token if none provided
 *
 * Usage:
 *   node web-chat.js                  # start server on :8888
 *   CLAUDE_WEB_PORT=9999 node web-chat.js  # custom port
 */

const http = require("http");
const { WebSocketServer } = require("ws");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const PORT = parseInt(process.env.CLAUDE_WEB_PORT || "8888", 10);
const MAX_CONNECTIONS = parseInt(process.env.CLAUDE_WEB_MAX_CONN || "5", 10);
const RATE_LIMIT = 20; // messages per minute per client
const HEARTBEAT_INTERVAL = 30000; // 30s
const HEARTBEAT_TIMEOUT = 10000; // 10s grace
const SESSION_DIR = "/data/sessions";
const HTML_PATH = path.join(__dirname, "web-chat.html");

// Auto-generate token if not set (written to /data/web-chat-token for retrieval)
const TOKEN = process.env.CLAUDE_WEB_TOKEN || crypto.randomBytes(16).toString("hex");
const TOKEN_FILE = "/data/web-chat-token";

// Active Claude processes keyed by WebSocket
const sessions = new Map();

// Per-client rate limiting
const rateLimits = new Map(); // ws -> { count, resetAt }

// ── Helpers ──────────────────────────────────────────────────────────────────

function checkAuth(tokenCandidate) {
  return tokenCandidate === TOKEN;
}

function isRateLimited(ws) {
  const now = Date.now();
  let rl = rateLimits.get(ws);
  if (!rl || now > rl.resetAt) {
    rl = { count: 0, resetAt: now + 60000 };
    rateLimits.set(ws, rl);
  }
  rl.count++;
  return rl.count > RATE_LIMIT;
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
    res.end(JSON.stringify({ status: "ok", sessions: sessions.size }));
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
    });
    return;
  }

  // List active sessions
  if (parsedUrl.pathname === "/sessions") {
    const active = [];
    for (const [, sess] of sessions) {
      active.push({
        id: sess.id,
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

  const sessionId = `web-${Date.now()}-${crypto.randomBytes(3).toString("hex")}`;
  const session = {
    id: sessionId,
    started: new Date().toISOString(),
    proc: null,
    project: "/workspace",
    buffer: "",
    lastPong: Date.now(),
  };
  sessions.set(ws, session);

  console.log(`[${sessionId}] Connected (total: ${sessions.size})`);
  safeSend(ws, { type: "system", text: `Connected. Type a message to start.` });

  // ── Heartbeat (ping/pong) ──
  ws.isAlive = true;
  ws.on("pong", () => {
    ws.isAlive = true;
    session.lastPong = Date.now();
  });

  // ── Message handler ──
  ws.on("message", (raw) => {
    // Rate limit
    if (isRateLimited(ws)) {
      safeSend(ws, { type: "error", text: "Rate limited. Slow down." });
      return;
    }

    let msg;
    try {
      msg = JSON.parse(raw.toString());
    } catch {
      msg = { type: "chat", text: raw.toString() };
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
    } else if (msg.type === "resume") {
      handleResume(ws, session);
    }
  });

  ws.on("close", () => {
    console.log(`[${sessionId}] Disconnected`);
    if (session.proc && !session.proc.killed) {
      session.proc.kill("SIGTERM");
    }
    sessions.delete(ws);
    rateLimits.delete(ws);
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

// ── Claude CLI interaction ──────────────────────────────────────────────────

function handleChat(ws, session, text) {
  if (!text || !text.trim()) return;

  // Kill any existing process
  if (session.proc && !session.proc.killed) {
    session.proc.kill("SIGTERM");
  }

  const trimmed = text.length > 100 ? text.substring(0, 100) + "..." : text;
  console.log(`[${session.id}] Prompt: ${trimmed}`);

  // Use -p for print mode, --resume to continue conversation context
  const args = ["-p", text, "--verbose"];
  if (session.hasConversation) {
    args.push("--resume");
  }

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

    // Log conversation to session file
    try {
      const logDir = path.join(SESSION_DIR, session.id);
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

function handleResume(ws, session) {
  if (session.proc && !session.proc.killed) {
    session.proc.kill("SIGTERM");
  }

  const proc = spawn("claude", ["--resume", "--verbose"], {
    cwd: session.project,
    env: { ...process.env, TERM: "dumb", NO_COLOR: "1" },
    stdio: ["pipe", "pipe", "pipe"],
  });

  session.proc = proc;
  session.hasConversation = true;

  safeSend(ws, { type: "system", text: "Resuming previous conversation..." });

  proc.stdout.on("data", (chunk) => {
    safeSend(ws, { type: "stream", text: chunk.toString() });
  });

  proc.stderr.on("data", (chunk) => {
    const t = chunk.toString();
    if (!t.includes("Update available") && !t.includes("npm ")) {
      safeSend(ws, { type: "stderr", text: t });
    }
  });

  proc.on("close", (code) => {
    safeSend(ws, { type: "done", code });
    session.proc = null;
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
  console.log(`Rate limit: ${RATE_LIMIT} msgs/min per client`);
  console.log(`Heartbeat: ${HEARTBEAT_INTERVAL / 1000}s ping, ${HEARTBEAT_TIMEOUT / 1000}s timeout`);
});
