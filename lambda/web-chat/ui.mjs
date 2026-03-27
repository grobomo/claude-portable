// Web Chat UI - mobile-first chat interface
// Talks to Lambda /api/prompt which relays to EC2 web-chat

export const WEB_UI = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Claude">
<title>Claude Portable</title>
<style>
  :root {
    --bg: #0a0a0a; --surface: #141414; --border: #2a2a2a;
    --text: #e0e0e0; --dim: #666; --accent: #c084fc; --accent-dim: #7c3aed;
    --user-bg: #1c1530; --error: #ff4a4a; --green: #4ae04a;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
    font-size: 14px; background: var(--bg); color: var(--text);
    height: 100dvh; display: flex; flex-direction: column; overflow: hidden;
    -webkit-font-smoothing: antialiased;
  }
  header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 16px; background: var(--surface); border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }
  header h1 { font-size: 16px; font-weight: 600; color: var(--accent); }
  .status { font-size: 11px; color: var(--dim); }
  .status-dot {
    display: inline-block; width: 8px; height: 8px; border-radius: 50%;
    background: var(--dim); margin-right: 4px; vertical-align: middle;
  }
  .status-dot.ok { background: var(--green); }
  .status-dot.busy { background: #d29922; animation: pulse 1s infinite; }
  .status-dot.err { background: var(--error); }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }

  #messages {
    flex: 1; overflow-y: auto; padding: 12px 16px;
    display: flex; flex-direction: column; gap: 10px;
    -webkit-overflow-scrolling: touch;
  }
  .msg {
    max-width: 90%; padding: 10px 14px; border-radius: 16px;
    font-size: 14px; line-height: 1.5; word-wrap: break-word; white-space: pre-wrap;
  }
  .msg.user {
    align-self: flex-end; background: var(--accent-dim); color: white;
    border-bottom-right-radius: 4px;
  }
  .msg.claude {
    align-self: flex-start; background: var(--surface); border: 1px solid var(--border);
    border-bottom-left-radius: 4px;
  }
  .msg.system {
    align-self: center; color: var(--dim); font-size: 12px; padding: 4px 12px;
  }
  .msg.error { align-self: center; color: var(--error); font-size: 12px; }
  .msg code, .msg pre {
    background: rgba(255,255,255,0.06); padding: 1px 5px; border-radius: 4px;
    font-family: 'SF Mono', 'Fira Code', monospace; font-size: 13px;
  }
  .msg pre { display: block; padding: 10px; margin: 8px 0; overflow-x: auto; white-space: pre; border: 1px solid var(--border); }

  .input-area {
    padding: 8px 12px; padding-bottom: max(8px, env(safe-area-inset-bottom));
    background: var(--surface); border-top: 1px solid var(--border); flex-shrink: 0;
  }
  .input-row { display: flex; gap: 8px; align-items: flex-end; }
  #input {
    flex: 1; background: var(--bg); border: 1px solid var(--border); color: var(--text);
    padding: 10px 14px; border-radius: 20px; font-size: 15px; font-family: inherit;
    resize: none; max-height: 120px; min-height: 40px; line-height: 1.4; outline: none;
  }
  #input:focus { border-color: var(--accent); }
  #input::placeholder { color: var(--dim); }
  #send-btn {
    width: 40px; height: 40px; border-radius: 50%; background: var(--accent-dim);
    border: none; color: white; font-size: 18px; cursor: pointer;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  }
  #send-btn:disabled { opacity: 0.4; }

  .login-screen {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    min-height: 100vh; padding: 20px;
  }
  .login-screen h1 { font-size: 20px; margin-bottom: 8px; color: var(--accent); }
  .login-screen p { color: var(--dim); margin-bottom: 20px; font-size: 12px; }
  .login-screen input { max-width: 300px; text-align: center; background: var(--bg); border: 1px solid var(--border); color: var(--text); padding: 10px; border-radius: 6px; font-family: inherit; font-size: 14px; }
  .login-screen button { max-width: 300px; width: 100%; }

  #messages::-webkit-scrollbar { width: 4px; }
  #messages::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
  @media (min-width: 768px) { #messages { padding: 20px 10%; } .msg { max-width: 75%; } }
</style>
</head>
<body>

<div id="login" class="login-screen">
  <h1>Claude Portable</h1>
  <p>Mobile chat interface</p>
  <input id="login-token" type="password" placeholder="API token">
  <div style="height:12px"></div>
  <button id="login-btn" class="action" style="background:var(--accent-dim);color:white;border:none;padding:10px 20px;border-radius:6px;font-family:inherit;font-size:14px;cursor:pointer" onclick="doLogin()">Connect</button>
</div>

<div id="app" style="display:none">
  <header>
    <div>
      <h1>Claude Portable</h1>
      <div class="status"><span class="status-dot" id="dot"></span><span id="status-text">Connecting...</span></div>
    </div>
  </header>
  <div id="messages"></div>
  <div class="input-area">
    <div class="input-row">
      <textarea id="input" rows="1" placeholder="Message Claude..." autofocus></textarea>
      <button id="send-btn" onclick="doSend()">&#9654;</button>
    </div>
  </div>
</div>

<script>
'use strict';
let TOKEN = '', API = '';
let busy = false;

function doLogin() {
  TOKEN = document.getElementById('login-token').value.trim();
  if (!TOKEN) return;
  localStorage.setItem('wchat_token', TOKEN);
  API = location.origin;
  showApp();
}

function showApp() {
  document.getElementById('login').style.display = 'none';
  document.getElementById('app').style.display = 'flex';
  discover();
}

async function discover() {
  setStatus('busy', 'Discovering instance...');
  try {
    const res = await fetch(API + '/api/discover', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + TOKEN },
      body: '{}'
    });
    const data = await res.json();
    if (data.online) {
      setStatus('ok', data.instance.name + ' (' + data.instance.ip + ')');
      addMsg('system', 'Connected to ' + data.instance.name);
    } else {
      setStatus('err', 'No running instance');
      addMsg('system', 'No running instance found. Start one with: cpp offload');
    }
  } catch(e) {
    setStatus('err', 'Connection failed');
    addMsg('error', e.message);
  }
}

async function doSend() {
  const text = document.getElementById('input').value.trim();
  if (!text || busy) return;
  addMsg('user', text);
  document.getElementById('input').value = '';
  document.getElementById('input').style.height = 'auto';
  busy = true;
  document.getElementById('send-btn').disabled = true;
  setStatus('busy', 'Thinking...');
  try {
    const res = await fetch(API + '/api/prompt', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + TOKEN },
      body: JSON.stringify({ prompt: text })
    });
    const data = await res.json();
    if (data.error) { addMsg('error', data.error); }
    else { addMsg('claude', data.output || '(no output)'); }
    setStatus('ok', 'Ready');
  } catch(e) {
    addMsg('error', 'Request failed: ' + e.message);
    setStatus('err', 'Error');
  }
  busy = false;
  document.getElementById('send-btn').disabled = false;
}

function addMsg(type, text) {
  const el = document.createElement('div');
  el.className = 'msg ' + type;
  el.textContent = text;
  document.getElementById('messages').appendChild(el);
  el.scrollIntoView({ behavior: 'smooth' });
  // Format code blocks
  if (type === 'claude') {
    let h = esc(text);
    h = h.replace(/\`\`\`(\\w*)\\n([\\s\\S]*?)\`\`\`/g, '<pre><code>$2</code></pre>');
    h = h.replace(/\`([^\`]+)\`/g, '<code>$1</code>');
    h = h.replace(/\\*\\*([^*]+)\\*\\*/g, '<strong>$1</strong>');
    if (h !== esc(text)) el.innerHTML = h;
  }
}

function esc(s) {
  return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function setStatus(state, text) {
  document.getElementById('dot').className = 'status-dot ' + state;
  document.getElementById('status-text').textContent = text;
}

document.getElementById('input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); doSend(); }
});
document.getElementById('input').addEventListener('input', function() {
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 120) + 'px';
});

// Auto-login
window.addEventListener('load', () => {
  const t = localStorage.getItem('wchat_token');
  if (t) { document.getElementById('login-token').value = t; doLogin(); }
});
</script>
</body>
</html>`;
