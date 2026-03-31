"""
dashboard_auth.py -- Session-based authentication for CCC fleet dashboard.

Provides:
- User management with bcrypt-hashed passwords stored in a local JSON file
- Session management with secure httpOnly cookies
- Auth middleware for HealthHandler
- Login/logout/change-password/admin endpoints
"""

import hashlib
import json
import logging
import os
import secrets
import threading
import time

import bcrypt

log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────

USERS_FILE = os.environ.get(
    "DASHBOARD_USERS_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_users.json"),
)
SESSION_TTL = int(os.environ.get("DASHBOARD_SESSION_TTL", "86400"))  # 24 hours

# ── User store ─────────────────────────────────────────────────────────────────
# Format: {"users": {"username": {"password_hash": "...", "role": "admin|user",
#           "force_password_change": true/false, "created_at": "..."}}}

_users_lock = threading.Lock()
_users = {}  # loaded at init


def _load_users():
    """Load users from JSON file. Creates default admin if file missing."""
    global _users
    try:
        with open(USERS_FILE, "r") as f:
            data = json.load(f)
            _users = data.get("users", {})
            log.info("Loaded %d users from %s", len(_users), USERS_FILE)
    except FileNotFoundError:
        log.info("Users file not found, creating default admin user")
        _users = {}
        _create_default_admin()
    except (json.JSONDecodeError, Exception) as e:
        log.warning("Failed to load users file: %s -- creating default admin", e)
        _users = {}
        _create_default_admin()


def _save_users():
    """Persist users to JSON file."""
    try:
        with open(USERS_FILE, "w") as f:
            json.dump({"users": _users}, f, indent=2)
    except Exception as e:
        log.error("Failed to save users file: %s", e)


def _create_default_admin():
    """Create the default admin/admin user with force_password_change=True."""
    pw_hash = bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode("utf-8")
    _users["admin"] = {
        "password_hash": pw_hash,
        "role": "admin",
        "force_password_change": True,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _save_users()
    log.info("Created default admin user (password: admin, must change on first login)")


def verify_password(username, password):
    """Check password against stored hash. Returns True if valid."""
    user = _users.get(username)
    if not user:
        return False
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            user["password_hash"].encode("utf-8"),
        )
    except Exception:
        return False


def change_password(username, new_password):
    """Change a user's password and clear force_password_change flag."""
    with _users_lock:
        user = _users.get(username)
        if not user:
            return False
        user["password_hash"] = bcrypt.hashpw(
            new_password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        user["force_password_change"] = False
        _save_users()
    return True


def add_user(username, password, role="user"):
    """Add a new user. Returns (success, error_message)."""
    with _users_lock:
        if username in _users:
            return False, "User already exists"
        if len(username) < 2:
            return False, "Username must be at least 2 characters"
        if len(password) < 4:
            return False, "Password must be at least 4 characters"
        pw_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        _users[username] = {
            "password_hash": pw_hash,
            "role": role,
            "force_password_change": False,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _save_users()
    return True, None


def delete_user(username):
    """Delete a user. Cannot delete the last admin."""
    with _users_lock:
        if username not in _users:
            return False, "User not found"
        admin_count = sum(1 for u in _users.values() if u["role"] == "admin")
        if _users[username]["role"] == "admin" and admin_count <= 1:
            return False, "Cannot delete the last admin user"
        del _users[username]
        _save_users()
    return True, None


def force_password_reset(username):
    """Set force_password_change flag for a user."""
    with _users_lock:
        user = _users.get(username)
        if not user:
            return False, "User not found"
        user["force_password_change"] = True
        _save_users()
    return True, None


def list_users():
    """Return user list (without password hashes)."""
    result = []
    for name, data in _users.items():
        result.append({
            "username": name,
            "role": data["role"],
            "force_password_change": data.get("force_password_change", False),
            "created_at": data.get("created_at", ""),
        })
    return result


# ── Session store ──────────────────────────────────────────────────────────────

_sessions_lock = threading.Lock()
_sessions = {}  # {session_id: {"username": str, "created_at": float, "expires_at": float}}


def create_session(username):
    """Create a new session. Returns session_id."""
    session_id = secrets.token_hex(32)
    now = time.time()
    with _sessions_lock:
        _sessions[session_id] = {
            "username": username,
            "created_at": now,
            "expires_at": now + SESSION_TTL,
        }
    return session_id


def validate_session(session_id):
    """Validate session. Returns username if valid, None otherwise."""
    if not session_id:
        return None
    with _sessions_lock:
        session = _sessions.get(session_id)
        if not session:
            return None
        if time.time() > session["expires_at"]:
            del _sessions[session_id]
            return None
        return session["username"]


def destroy_session(session_id):
    """Remove a session."""
    with _sessions_lock:
        _sessions.pop(session_id, None)


def get_session_cookie(handler):
    """Extract session_id from Cookie header."""
    cookie_header = handler.headers.get("Cookie", "")
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith("ccc_session="):
            return part[len("ccc_session="):]
    return None


def get_current_user(handler):
    """Get the authenticated username from the request, or None."""
    session_id = get_session_cookie(handler)
    return validate_session(session_id)


def user_must_change_password(username):
    """Check if user has force_password_change flag set."""
    user = _users.get(username)
    if not user:
        return False
    return user.get("force_password_change", False)


def is_admin(username):
    """Check if user has admin role."""
    user = _users.get(username)
    if not user:
        return False
    return user.get("role") == "admin"


# ── Initialization ─────────────────────────────────────────────────────────────

def init():
    """Load users from disk. Call once at startup."""
    with _users_lock:
        _load_users()


# ── HTML Pages ─────────────────────────────────────────────────────────────────

LOGIN_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CCC Fleet Dashboard - Login</title>
<style>
:root {
  --bg: #0d1117; --card-bg: #161b22; --border: #30363d;
  --text: #e6edf3; --text-muted: #8b949e; --green: #3fb950;
  --red: #f85149; --blue: #58a6ff;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  background: var(--bg); color: var(--text);
  font-family: 'SF Mono', 'Consolas', 'Monaco', 'Menlo', monospace;
  display: flex; align-items: center; justify-content: center;
  min-height: 100vh;
}
.login-box {
  background: var(--card-bg); border: 1px solid var(--border);
  border-radius: 8px; padding: 40px; width: 380px;
}
.login-box h1 { font-size: 20px; margin-bottom: 8px; text-align: center; }
.login-box .subtitle { color: var(--text-muted); font-size: 13px; text-align: center; margin-bottom: 24px; }
label { display: block; font-size: 13px; color: var(--text-muted); margin-bottom: 4px; margin-top: 16px; }
input[type="text"], input[type="password"] {
  width: 100%; padding: 10px 12px; background: var(--bg);
  border: 1px solid var(--border); border-radius: 4px; color: var(--text);
  font-family: inherit; font-size: 14px;
}
input:focus { outline: none; border-color: var(--blue); }
button {
  width: 100%; padding: 10px; margin-top: 24px;
  background: var(--blue); color: #fff; border: none; border-radius: 4px;
  font-family: inherit; font-size: 14px; font-weight: 600; cursor: pointer;
}
button:hover { opacity: 0.9; }
.error { color: var(--red); font-size: 13px; margin-top: 12px; text-align: center; }
</style>
</head>
<body>
<div class="login-box">
  <h1>CCC Fleet Dashboard</h1>
  <div class="subtitle">Authentication Required</div>
  <form method="POST" action="/auth/login">
    <label for="username">Username</label>
    <input type="text" id="username" name="username" autocomplete="username" required autofocus>
    <label for="password">Password</label>
    <input type="password" id="password" name="password" autocomplete="current-password" required>
    <button type="submit">Sign In</button>
    {{ERROR}}
  </form>
</div>
</body>
</html>"""

CHANGE_PASSWORD_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CCC Fleet Dashboard - Change Password</title>
<style>
:root {
  --bg: #0d1117; --card-bg: #161b22; --border: #30363d;
  --text: #e6edf3; --text-muted: #8b949e; --green: #3fb950;
  --red: #f85149; --blue: #58a6ff; --amber: #d29922;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  background: var(--bg); color: var(--text);
  font-family: 'SF Mono', 'Consolas', 'Monaco', 'Menlo', monospace;
  display: flex; align-items: center; justify-content: center;
  min-height: 100vh;
}
.box {
  background: var(--card-bg); border: 1px solid var(--border);
  border-radius: 8px; padding: 40px; width: 420px;
}
.box h1 { font-size: 20px; margin-bottom: 8px; text-align: center; }
.box .warning { color: var(--amber); font-size: 13px; text-align: center; margin-bottom: 24px; }
label { display: block; font-size: 13px; color: var(--text-muted); margin-bottom: 4px; margin-top: 16px; }
input[type="password"] {
  width: 100%; padding: 10px 12px; background: var(--bg);
  border: 1px solid var(--border); border-radius: 4px; color: var(--text);
  font-family: inherit; font-size: 14px;
}
input:focus { outline: none; border-color: var(--blue); }
button {
  width: 100%; padding: 10px; margin-top: 24px;
  background: var(--green); color: #fff; border: none; border-radius: 4px;
  font-family: inherit; font-size: 14px; font-weight: 600; cursor: pointer;
}
button:hover { opacity: 0.9; }
.error { color: var(--red); font-size: 13px; margin-top: 12px; text-align: center; }
</style>
</head>
<body>
<div class="box">
  <h1>Change Password</h1>
  <div class="warning">You must change your password before continuing.</div>
  <form method="POST" action="/auth/change-password">
    <label for="new_password">New Password</label>
    <input type="password" id="new_password" name="new_password" autocomplete="new-password" required autofocus>
    <label for="confirm_password">Confirm Password</label>
    <input type="password" id="confirm_password" name="confirm_password" autocomplete="new-password" required>
    <button type="submit">Change Password</button>
    {{ERROR}}
  </form>
</div>
</body>
</html>"""

ADMIN_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CCC Fleet Dashboard - Admin</title>
<style>
:root {
  --bg: #0d1117; --card-bg: #161b22; --border: #30363d;
  --text: #e6edf3; --text-muted: #8b949e; --green: #3fb950;
  --red: #f85149; --blue: #58a6ff; --amber: #d29922;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  background: var(--bg); color: var(--text);
  font-family: 'SF Mono', 'Consolas', 'Monaco', 'Menlo', monospace;
  font-size: 14px; line-height: 1.5;
}
.top-bar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 24px; background: var(--card-bg); border-bottom: 1px solid var(--border);
}
.top-bar h1 { font-size: 18px; }
.top-bar a { color: var(--blue); text-decoration: none; font-size: 13px; }
.top-bar a:hover { text-decoration: underline; }
.container { max-width: 800px; margin: 32px auto; padding: 0 24px; }
.section { margin-bottom: 32px; }
.section h2 { font-size: 16px; margin-bottom: 16px; color: var(--text-muted); }
table { width: 100%; border-collapse: collapse; background: var(--card-bg); border-radius: 6px; overflow: hidden; }
th, td { padding: 10px 16px; text-align: left; border-bottom: 1px solid var(--border); }
th { font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
td { font-size: 13px; }
.badge { padding: 2px 8px; border-radius: 3px; font-size: 11px; font-weight: 600; }
.badge-admin { background: rgba(163,113,247,0.15); color: #a371f7; }
.badge-user { background: rgba(88,166,255,0.15); color: var(--blue); }
.badge-warn { background: rgba(210,153,34,0.15); color: var(--amber); }
.btn { padding: 4px 12px; border: 1px solid var(--border); border-radius: 4px; background: var(--card-bg); color: var(--text); font-family: inherit; font-size: 12px; cursor: pointer; }
.btn:hover { border-color: var(--text-muted); }
.btn-danger { border-color: var(--red); color: var(--red); }
.btn-danger:hover { background: rgba(248,81,73,0.15); }
.add-form {
  background: var(--card-bg); border: 1px solid var(--border); border-radius: 6px;
  padding: 20px; display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap;
}
.add-form .field { display: flex; flex-direction: column; gap: 4px; }
.add-form label { font-size: 12px; color: var(--text-muted); }
.add-form input, .add-form select {
  padding: 8px 10px; background: var(--bg); border: 1px solid var(--border);
  border-radius: 4px; color: var(--text); font-family: inherit; font-size: 13px;
}
.add-form button {
  padding: 8px 16px; background: var(--green); color: #fff; border: none;
  border-radius: 4px; font-family: inherit; font-size: 13px; font-weight: 600; cursor: pointer;
}
.msg { padding: 10px 16px; border-radius: 4px; margin-bottom: 16px; font-size: 13px; }
.msg-ok { background: rgba(63,185,80,0.15); color: var(--green); border: 1px solid rgba(63,185,80,0.3); }
.msg-err { background: rgba(248,81,73,0.15); color: var(--red); border: 1px solid rgba(248,81,73,0.3); }
</style>
</head>
<body>
<div class="top-bar">
  <h1>Admin Panel</h1>
  <div>
    <a href="/">Dashboard</a> &nbsp;|&nbsp;
    <a href="/auth/logout">Sign Out</a>
  </div>
</div>
<div class="container">
  {{MESSAGE}}
  <div class="section">
    <h2>Add New User</h2>
    <form class="add-form" method="POST" action="/admin/add-user">
      <div class="field">
        <label for="new_username">Username</label>
        <input type="text" id="new_username" name="username" required>
      </div>
      <div class="field">
        <label for="new_pw">Password</label>
        <input type="password" id="new_pw" name="password" required>
      </div>
      <div class="field">
        <label for="role">Role</label>
        <select id="role" name="role">
          <option value="user">user</option>
          <option value="admin">admin</option>
        </select>
      </div>
      <button type="submit">Add User</button>
    </form>
  </div>
  <div class="section">
    <h2>Users</h2>
    <table>
      <thead><tr><th>Username</th><th>Role</th><th>Status</th><th>Created</th><th>Actions</th></tr></thead>
      <tbody>
        {{USER_ROWS}}
      </tbody>
    </table>
  </div>
</div>
</body>
</html>"""


def render_login_page(error=""):
    """Render login HTML with optional error message."""
    err_html = '<div class="error">%s</div>' % error if error else ""
    return LOGIN_PAGE.replace("{{ERROR}}", err_html)


def render_change_password_page(error=""):
    """Render change-password HTML with optional error message."""
    err_html = '<div class="error">%s</div>' % error if error else ""
    return CHANGE_PASSWORD_PAGE.replace("{{ERROR}}", err_html)


def render_admin_page(message="", is_error=False):
    """Render admin HTML with user table."""
    msg_html = ""
    if message:
        cls = "msg-err" if is_error else "msg-ok"
        msg_html = '<div class="msg %s">%s</div>' % (cls, message)

    rows = []
    for user in list_users():
        role_badge = '<span class="badge badge-admin">admin</span>' if user["role"] == "admin" else '<span class="badge badge-user">user</span>'
        status = '<span class="badge badge-warn">must change pw</span>' if user["force_password_change"] else "OK"
        created = user["created_at"][:10] if user["created_at"] else "-"
        actions = (
            '<form method="POST" action="/admin/force-reset" style="display:inline">'
            '<input type="hidden" name="username" value="%s">'
            '<button class="btn" type="submit">Force Reset</button>'
            '</form> '
            '<form method="POST" action="/admin/delete-user" style="display:inline">'
            '<input type="hidden" name="username" value="%s">'
            '<button class="btn btn-danger" type="submit" onclick="return confirm(\'Delete %s?\')">Delete</button>'
            '</form>' % (user["username"], user["username"], user["username"])
        )
        rows.append(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (user["username"], role_badge, status, created, actions)
        )

    return (
        ADMIN_PAGE.replace("{{MESSAGE}}", msg_html)
        .replace("{{USER_ROWS}}", "\n".join(rows))
    )
