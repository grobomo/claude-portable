"""Tests for dashboard authentication (login, sessions, admin, password change)."""

import importlib.machinery
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from http.server import HTTPServer
from urllib.parse import urlencode

# Load git-dispatch.py as a module (same pattern as test_dashboard_api.py)
loader = importlib.machinery.SourceFileLoader(
    "git_dispatch",
    os.path.join(os.path.dirname(__file__), "..", "scripts", "git-dispatch.py"),
)
spec = importlib.util.spec_from_loader("git_dispatch", loader)
gd = importlib.util.module_from_spec(spec)
loader.exec_module(gd)

import dashboard_auth


def _http_request(server, method, path, body=None, headers=None, follow_redirects=False):
    """Make an HTTP request. Returns (status, response_headers_dict, body_bytes)."""
    import http.client
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    hdrs = headers or {}
    if body and "Content-Type" not in hdrs:
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    conn.request(method, path, body=body, headers=hdrs)
    resp = conn.getresponse()
    resp_body = resp.read()
    resp_headers = {k.lower(): v for k, v in resp.getheaders()}
    conn.close()
    return resp.status, resp_headers, resp_body


def _extract_session_cookie(resp_headers):
    """Extract ccc_session value from Set-Cookie header."""
    cookie = resp_headers.get("set-cookie", "")
    for part in cookie.split(";"):
        part = part.strip()
        if part.startswith("ccc_session="):
            return part[len("ccc_session="):]
    return None


class TestDashboardAuthModule(unittest.TestCase):
    """Unit tests for dashboard_auth.py functions."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.users_file = os.path.join(self.tmpdir, "users.json")
        self._orig_file = dashboard_auth.USERS_FILE
        dashboard_auth.USERS_FILE = self.users_file
        dashboard_auth._users.clear()
        dashboard_auth._sessions.clear()
        dashboard_auth.init()

    def tearDown(self):
        dashboard_auth.USERS_FILE = self._orig_file
        dashboard_auth._users.clear()
        dashboard_auth._sessions.clear()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_default_admin_created(self):
        users = dashboard_auth.list_users()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["username"], "admin")
        self.assertEqual(users[0]["role"], "admin")
        self.assertTrue(users[0]["force_password_change"])

    def test_verify_default_password(self):
        self.assertTrue(dashboard_auth.verify_password("admin", "admin"))

    def test_verify_wrong_password(self):
        self.assertFalse(dashboard_auth.verify_password("admin", "wrong"))

    def test_verify_nonexistent_user(self):
        self.assertFalse(dashboard_auth.verify_password("ghost", "admin"))

    def test_change_password(self):
        self.assertTrue(dashboard_auth.change_password("admin", "newpass"))
        self.assertTrue(dashboard_auth.verify_password("admin", "newpass"))
        self.assertFalse(dashboard_auth.verify_password("admin", "admin"))

    def test_change_password_clears_force_flag(self):
        self.assertTrue(dashboard_auth.user_must_change_password("admin"))
        dashboard_auth.change_password("admin", "newpass")
        self.assertFalse(dashboard_auth.user_must_change_password("admin"))

    def test_add_user(self):
        ok, err = dashboard_auth.add_user("alice", "pass1234", "user")
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertTrue(dashboard_auth.verify_password("alice", "pass1234"))

    def test_add_duplicate_user(self):
        ok, err = dashboard_auth.add_user("admin", "pass", "user")
        self.assertFalse(ok)
        self.assertIn("already exists", err)

    def test_add_user_short_username(self):
        ok, err = dashboard_auth.add_user("a", "pass1234", "user")
        self.assertFalse(ok)
        self.assertIn("2 characters", err)

    def test_add_user_short_password(self):
        ok, err = dashboard_auth.add_user("bob", "ab", "user")
        self.assertFalse(ok)
        self.assertIn("4 characters", err)

    def test_delete_user(self):
        dashboard_auth.add_user("bob", "pass1234", "user")
        ok, err = dashboard_auth.delete_user("bob")
        self.assertTrue(ok)
        self.assertFalse(dashboard_auth.verify_password("bob", "pass1234"))

    def test_cannot_delete_last_admin(self):
        ok, err = dashboard_auth.delete_user("admin")
        self.assertFalse(ok)
        self.assertIn("last admin", err)

    def test_can_delete_admin_if_another_exists(self):
        dashboard_auth.add_user("admin2", "pass1234", "admin")
        ok, err = dashboard_auth.delete_user("admin")
        self.assertTrue(ok)

    def test_force_password_reset(self):
        dashboard_auth.change_password("admin", "newpass")
        self.assertFalse(dashboard_auth.user_must_change_password("admin"))
        ok, err = dashboard_auth.force_password_reset("admin")
        self.assertTrue(ok)
        self.assertTrue(dashboard_auth.user_must_change_password("admin"))

    def test_session_lifecycle(self):
        sid = dashboard_auth.create_session("admin")
        self.assertEqual(dashboard_auth.validate_session(sid), "admin")
        dashboard_auth.destroy_session(sid)
        self.assertIsNone(dashboard_auth.validate_session(sid))

    def test_expired_session(self):
        sid = dashboard_auth.create_session("admin")
        # Manually expire it
        with dashboard_auth._sessions_lock:
            dashboard_auth._sessions[sid]["expires_at"] = time.time() - 1
        self.assertIsNone(dashboard_auth.validate_session(sid))

    def test_is_admin(self):
        self.assertTrue(dashboard_auth.is_admin("admin"))
        dashboard_auth.add_user("viewer", "pass1234", "user")
        self.assertFalse(dashboard_auth.is_admin("viewer"))
        self.assertFalse(dashboard_auth.is_admin("nonexistent"))

    def test_persistence(self):
        dashboard_auth.add_user("persist", "test1234", "user")
        # Reload from disk
        dashboard_auth._users.clear()
        dashboard_auth.init()
        self.assertTrue(dashboard_auth.verify_password("persist", "test1234"))

    def test_render_login_page(self):
        html = dashboard_auth.render_login_page()
        self.assertIn("Sign In", html)
        self.assertNotIn('<div class="error">', html)  # no error div when no error

    def test_render_login_page_with_error(self):
        html = dashboard_auth.render_login_page("Bad credentials")
        self.assertIn("Bad credentials", html)

    def test_render_change_password_page(self):
        html = dashboard_auth.render_change_password_page()
        self.assertIn("Change Password", html)

    def test_render_admin_page(self):
        html = dashboard_auth.render_admin_page()
        self.assertIn("Admin Panel", html)
        self.assertIn("admin", html)


class TestAuthHttpEndpoints(unittest.TestCase):
    """Integration tests: actual HTTP requests testing auth flow."""

    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), gd.HealthHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.users_file = os.path.join(self.tmpdir, "users.json")
        self._orig_file = dashboard_auth.USERS_FILE
        dashboard_auth.USERS_FILE = self.users_file
        dashboard_auth._users.clear()
        dashboard_auth._sessions.clear()
        dashboard_auth.init()

    def tearDown(self):
        dashboard_auth.USERS_FILE = self._orig_file
        dashboard_auth._users.clear()
        dashboard_auth._sessions.clear()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_root_redirects_to_login(self):
        status, headers, _ = _http_request(self.server, "GET", "/")
        self.assertEqual(status, 302)
        self.assertEqual(headers.get("location"), "/auth/login")

    def test_dashboard_redirects_to_login(self):
        status, headers, _ = _http_request(self.server, "GET", "/dashboard")
        self.assertEqual(status, 302)
        self.assertEqual(headers.get("location"), "/auth/login")

    def test_login_page_renders(self):
        status, _, body = _http_request(self.server, "GET", "/auth/login")
        self.assertEqual(status, 200)
        self.assertIn(b"Sign In", body)

    def test_login_success_redirects_to_change_password(self):
        form = urlencode({"username": "admin", "password": "admin"})
        status, headers, _ = _http_request(self.server, "POST", "/auth/login", body=form)
        self.assertEqual(status, 302)
        self.assertEqual(headers.get("location"), "/auth/change-password")
        cookie = _extract_session_cookie(headers)
        self.assertIsNotNone(cookie)
        self.assertTrue(len(cookie) > 16)

    def test_login_failure(self):
        form = urlencode({"username": "admin", "password": "wrong"})
        status, _, body = _http_request(self.server, "POST", "/auth/login", body=form)
        self.assertEqual(status, 200)
        self.assertIn(b"Invalid username or password", body)

    def test_login_empty_fields(self):
        form = urlencode({"username": "", "password": ""})
        status, _, body = _http_request(self.server, "POST", "/auth/login", body=form)
        self.assertEqual(status, 200)
        self.assertIn(b"required", body)

    def test_full_login_flow(self):
        # Login with default admin
        form = urlencode({"username": "admin", "password": "admin"})
        status, headers, _ = _http_request(self.server, "POST", "/auth/login", body=form)
        self.assertEqual(status, 302)
        cookie = _extract_session_cookie(headers)

        # Should redirect to change-password when accessing root
        status, headers, _ = _http_request(
            self.server, "GET", "/",
            headers={"Cookie": "ccc_session=" + cookie},
        )
        self.assertEqual(status, 302)
        self.assertEqual(headers.get("location"), "/auth/change-password")

        # Change password
        form = urlencode({"new_password": "secure123", "confirm_password": "secure123"})
        status, headers, _ = _http_request(
            self.server, "POST", "/auth/change-password",
            body=form,
            headers={"Cookie": "ccc_session=" + cookie},
        )
        self.assertEqual(status, 302)
        self.assertEqual(headers.get("location"), "/")

        # Now root should serve dashboard
        status, _, body = _http_request(
            self.server, "GET", "/",
            headers={"Cookie": "ccc_session=" + cookie},
        )
        self.assertEqual(status, 200)
        self.assertIn(b"CCC Fleet Dashboard", body)

    def test_change_password_mismatch(self):
        # Login first
        form = urlencode({"username": "admin", "password": "admin"})
        _, headers, _ = _http_request(self.server, "POST", "/auth/login", body=form)
        cookie = _extract_session_cookie(headers)

        form = urlencode({"new_password": "abc123", "confirm_password": "xyz789"})
        status, _, body = _http_request(
            self.server, "POST", "/auth/change-password",
            body=form,
            headers={"Cookie": "ccc_session=" + cookie},
        )
        self.assertEqual(status, 200)
        self.assertIn(b"do not match", body)

    def test_change_password_too_short(self):
        form = urlencode({"username": "admin", "password": "admin"})
        _, headers, _ = _http_request(self.server, "POST", "/auth/login", body=form)
        cookie = _extract_session_cookie(headers)

        form = urlencode({"new_password": "ab", "confirm_password": "ab"})
        status, _, body = _http_request(
            self.server, "POST", "/auth/change-password",
            body=form,
            headers={"Cookie": "ccc_session=" + cookie},
        )
        self.assertEqual(status, 200)
        self.assertIn(b"4 characters", body)

    def test_logout(self):
        # Login and change password
        form = urlencode({"username": "admin", "password": "admin"})
        _, headers, _ = _http_request(self.server, "POST", "/auth/login", body=form)
        cookie = _extract_session_cookie(headers)
        dashboard_auth.change_password("admin", "pass1234")

        # Logout
        status, headers, _ = _http_request(
            self.server, "GET", "/auth/logout",
            headers={"Cookie": "ccc_session=" + cookie},
        )
        self.assertEqual(status, 302)
        self.assertEqual(headers.get("location"), "/auth/login")

        # Session should be invalid now
        status, headers, _ = _http_request(
            self.server, "GET", "/",
            headers={"Cookie": "ccc_session=" + cookie},
        )
        self.assertEqual(status, 302)
        self.assertEqual(headers.get("location"), "/auth/login")

    def test_admin_panel_requires_admin_role(self):
        # Change admin password, add a regular user
        dashboard_auth.change_password("admin", "pass1234")
        dashboard_auth.add_user("viewer", "view1234", "user")

        # Login as viewer
        form = urlencode({"username": "viewer", "password": "view1234"})
        _, headers, _ = _http_request(self.server, "POST", "/auth/login", body=form)
        cookie = _extract_session_cookie(headers)

        # Admin panel should be forbidden
        status, _, _ = _http_request(
            self.server, "GET", "/admin",
            headers={"Cookie": "ccc_session=" + cookie},
        )
        self.assertEqual(status, 403)

    def test_admin_panel_accessible_for_admin(self):
        dashboard_auth.change_password("admin", "pass1234")
        form = urlencode({"username": "admin", "password": "pass1234"})
        _, headers, _ = _http_request(self.server, "POST", "/auth/login", body=form)
        cookie = _extract_session_cookie(headers)

        status, _, body = _http_request(
            self.server, "GET", "/admin",
            headers={"Cookie": "ccc_session=" + cookie},
        )
        self.assertEqual(status, 200)
        self.assertIn(b"Admin Panel", body)

    def test_admin_add_user(self):
        dashboard_auth.change_password("admin", "pass1234")
        form = urlencode({"username": "admin", "password": "pass1234"})
        _, headers, _ = _http_request(self.server, "POST", "/auth/login", body=form)
        cookie = _extract_session_cookie(headers)

        form = urlencode({"username": "newguy", "password": "test1234", "role": "user"})
        status, _, body = _http_request(
            self.server, "POST", "/admin/add-user",
            body=form,
            headers={"Cookie": "ccc_session=" + cookie},
        )
        self.assertEqual(status, 200)
        self.assertIn(b"newguy", body)
        self.assertTrue(dashboard_auth.verify_password("newguy", "test1234"))

    def test_admin_force_reset(self):
        dashboard_auth.change_password("admin", "pass1234")
        dashboard_auth.add_user("bob", "bobpass12", "user")

        form = urlencode({"username": "admin", "password": "pass1234"})
        _, headers, _ = _http_request(self.server, "POST", "/auth/login", body=form)
        cookie = _extract_session_cookie(headers)

        form = urlencode({"username": "bob"})
        status, _, body = _http_request(
            self.server, "POST", "/admin/force-reset",
            body=form,
            headers={"Cookie": "ccc_session=" + cookie},
        )
        self.assertEqual(status, 200)
        self.assertTrue(dashboard_auth.user_must_change_password("bob"))

    def test_admin_delete_user(self):
        dashboard_auth.change_password("admin", "pass1234")
        dashboard_auth.add_user("temp", "temppass1", "user")

        form = urlencode({"username": "admin", "password": "pass1234"})
        _, headers, _ = _http_request(self.server, "POST", "/auth/login", body=form)
        cookie = _extract_session_cookie(headers)

        form = urlencode({"username": "temp"})
        status, _, body = _http_request(
            self.server, "POST", "/admin/delete-user",
            body=form,
            headers={"Cookie": "ccc_session=" + cookie},
        )
        self.assertEqual(status, 200)
        self.assertFalse(dashboard_auth.verify_password("temp", "temppass1"))

    def test_health_endpoint_no_auth_required(self):
        status, _, body = _http_request(self.server, "GET", "/health")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("uptime_seconds", data)

    def test_api_endpoints_no_auth_required(self):
        status, _, _ = _http_request(self.server, "GET", "/api/tasks")
        self.assertEqual(status, 200)
        status, _, _ = _http_request(self.server, "GET", "/api/workers")
        self.assertEqual(status, 200)
        status, _, _ = _http_request(self.server, "GET", "/api/stats")
        self.assertEqual(status, 200)

    def test_cookie_is_httponly(self):
        form = urlencode({"username": "admin", "password": "admin"})
        _, headers, _ = _http_request(self.server, "POST", "/auth/login", body=form)
        cookie_header = headers.get("set-cookie", "")
        self.assertIn("HttpOnly", cookie_header)
        self.assertIn("SameSite=Strict", cookie_header)


if __name__ == "__main__":
    unittest.main()
