#!/usr/bin/env python3
"""Tests for config-bundle.py sanitization and bundling.

Validates:
- Secret patterns are replaced
- Windows paths are rewritten to container paths
- PII (usernames) is scrubbed
- Excluded files are skipped
- Bundle creates valid zip with MANIFEST.json
- Version hash is deterministic
"""

import importlib
import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

loader = importlib.machinery.SourceFileLoader(
    "config_bundle",
    os.path.join(os.path.dirname(__file__), "..", "scripts", "config-bundle.py"),
)
spec = importlib.util.spec_from_loader("config_bundle", loader)
cb = importlib.util.module_from_spec(spec)
loader.exec_module(cb)


class TestSanitizeContent(unittest.TestCase):
    def test_windows_forward_slash_path(self):
        content = 'path = "C:/Users/joelg/Documents/ProjectsCL1/myproject"'
        result = cb.sanitize_content(content)
        self.assertNotIn("C:/Users/", result)
        self.assertIn("/workspace/", result)

    def test_windows_backslash_path(self):
        content = r'path = "C:\\Users\\joelg\\Documents\\ProjectsCL1\\MCP\\server"'
        result = cb.sanitize_content(content)
        self.assertNotIn("C:\\\\Users", result)
        self.assertIn("/opt/mcp/", result)

    def test_claude_home_path(self):
        content = '"C:/Users/joelg/.claude/settings.json"'
        result = cb.sanitize_content(content)
        self.assertIn("/home/claude/.claude/", result)
        self.assertNotIn("C:/Users/", result)

    def test_pii_username_scrubbed(self):
        content = "User joelg connected to server"
        result = cb.sanitize_content(content)
        self.assertNotIn("joelg", result)
        self.assertIn("${USER_NAME}", result)

    def test_pii_full_name_scrubbed(self):
        content = "Author: joel.ginsberg"
        result = cb.sanitize_content(content)
        self.assertNotIn("joel.ginsberg", result)

    def test_tmemu_account_scrubbed(self):
        content = "repo: joel-ginsberg_tmemu/myrepo"
        result = cb.sanitize_content(content)
        self.assertNotIn("joel-ginsberg_tmemu", result)
        self.assertIn("${TMEMU_ACCOUNT}", result)

    def test_oauth_token_scrubbed(self):
        content = '{"access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.very_long_token_here"}'
        result = cb.sanitize_content(content)
        self.assertNotIn("eyJhbGci", result)
        self.assertIn("${OAUTH_ACCESS_TOKEN}", result)

    def test_dash_separated_paths(self):
        content = "C--Users-joelg-Documents-ProjectsCL1-myproject"
        result = cb.sanitize_content(content)
        self.assertNotIn("joelg", result)

    def test_clean_content_unchanged(self):
        content = "This is normal text with no secrets or paths."
        result = cb.sanitize_content(content)
        self.assertEqual(result, content)


class TestShouldExclude(unittest.TestCase):
    def test_credentials_excluded(self):
        self.assertTrue(cb.should_exclude(".credentials.json"))

    def test_history_excluded(self):
        self.assertTrue(cb.should_exclude("history.jsonl"))

    def test_cache_dir_excluded(self):
        self.assertTrue(cb.should_exclude("cache/something.json"))

    def test_git_dir_excluded(self):
        self.assertTrue(cb.should_exclude(".git/objects/abc"))

    def test_html_excluded(self):
        self.assertTrue(cb.should_exclude("report.html"))

    def test_settings_not_excluded(self):
        self.assertFalse(cb.should_exclude("settings.json"))

    def test_rule_md_not_excluded(self):
        self.assertFalse(cb.should_exclude("rules/my-rule.md"))

    def test_hook_js_not_excluded(self):
        self.assertFalse(cb.should_exclude("hooks/run-stop.js"))


class TestBuildBundle(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.claude_home = os.path.join(self.tmpdir, ".claude")
        os.makedirs(self.claude_home)
        # Create minimal config
        with open(os.path.join(self.claude_home, "settings.json"), "w") as f:
            json.dump({"model": "opus", "path": "C:/Users/testuser/.claude/"}, f)
        with open(os.path.join(self.claude_home, "CLAUDE.md"), "w") as f:
            f.write("# Claude Config\nUser: joelg\n")
        os.makedirs(os.path.join(self.claude_home, "rules"))
        with open(os.path.join(self.claude_home, "rules", "test.md"), "w") as f:
            f.write("# Test Rule\n")
        # Excluded file
        with open(os.path.join(self.claude_home, ".credentials.json"), "w") as f:
            json.dump({"secret": "abc123"}, f)

    def test_build_creates_zip(self):
        bundle_dir = os.path.join(self.tmpdir, "bundles")
        defaults_dir = os.path.join(self.tmpdir, "defaults")

        # Monkey-patch module globals for test
        old_bundle = cb.BUNDLE_DIR
        old_defaults = cb.DEFAULTS_DIR
        old_home = cb.CLAUDE_HOME
        cb.BUNDLE_DIR = bundle_dir
        cb.DEFAULTS_DIR = defaults_dir
        cb.CLAUDE_HOME = self.claude_home
        try:
            cb.cmd_build(type("Args", (), {})())
        finally:
            cb.BUNDLE_DIR = old_bundle
            cb.DEFAULTS_DIR = old_defaults
            cb.CLAUDE_HOME = old_home

        latest = os.path.join(bundle_dir, "config-bundle-latest.zip")
        self.assertTrue(os.path.isfile(latest))

        # Verify it's a valid zip
        with zipfile.ZipFile(latest, "r") as zf:
            names = zf.namelist()
            self.assertIn("settings.json", names)
            self.assertIn("CLAUDE.md", names)
            self.assertIn("MANIFEST.json", names)
            self.assertIn("rules/test.md", names)
            # Credentials should NOT be in the zip
            self.assertNotIn(".credentials.json", names)

    def test_sanitization_in_bundle(self):
        bundle_dir = os.path.join(self.tmpdir, "bundles")
        defaults_dir = os.path.join(self.tmpdir, "defaults")

        old_bundle = cb.BUNDLE_DIR
        old_defaults = cb.DEFAULTS_DIR
        old_home = cb.CLAUDE_HOME
        cb.BUNDLE_DIR = bundle_dir
        cb.DEFAULTS_DIR = defaults_dir
        cb.CLAUDE_HOME = self.claude_home
        try:
            cb.cmd_build(type("Args", (), {})())
        finally:
            cb.BUNDLE_DIR = old_bundle
            cb.DEFAULTS_DIR = old_defaults
            cb.CLAUDE_HOME = old_home

        # Check settings.json was sanitized
        settings_path = os.path.join(defaults_dir, "settings.json")
        with open(settings_path) as f:
            content = f.read()
        self.assertNotIn("C:/Users/testuser", content)
        self.assertIn("/home/claude", content)

        # Check CLAUDE.md was sanitized
        claude_md = os.path.join(defaults_dir, "CLAUDE.md")
        with open(claude_md) as f:
            content = f.read()
        self.assertNotIn("joelg", content)


class TestComputeVersion(unittest.TestCase):
    def test_deterministic(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as f:
            f.write(b"test content")
            path = f.name
        try:
            v1 = cb.compute_version(path)
            v2 = cb.compute_version(path)
            self.assertEqual(v1, v2)
            self.assertEqual(len(v1), 12)
        finally:
            os.unlink(path)

    def test_different_content_different_version(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as f:
            f.write(b"content A")
            path_a = f.name
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as f:
            f.write(b"content B")
            path_b = f.name
        try:
            self.assertNotEqual(cb.compute_version(path_a),
                                cb.compute_version(path_b))
        finally:
            os.unlink(path_a)
            os.unlink(path_b)


if __name__ == "__main__":
    unittest.main()
