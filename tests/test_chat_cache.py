#!/usr/bin/env python3
"""Tests for rolling chat cache (write_chat_cache)."""

import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

_script_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "teams-dispatch.py")
_loader = importlib.machinery.SourceFileLoader("teams_dispatch", _script_path)
_spec = importlib.util.spec_from_loader("teams_dispatch", _loader)
teams_dispatch = importlib.util.module_from_spec(_spec)
# Prevent argparse from running and the HTTP server from starting
sys.modules["teams_dispatch"] = teams_dispatch
_loader.exec_module(teams_dispatch)


class TestWriteChatCache(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig_cache_dir = teams_dispatch.CHAT_CACHE_DIR
        teams_dispatch.CHAT_CACHE_DIR = self.tmpdir

    def tearDown(self):
        teams_dispatch.CHAT_CACHE_DIR = self._orig_cache_dir
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_messages(self, count):
        """Create mock Teams messages (newest first, like Graph API)."""
        msgs = []
        for i in range(count, 0, -1):
            msgs.append({
                "createdDateTime": f"2026-03-29T10:{i:02d}:00Z",
                "from": {"user": {"displayName": f"User{i}"}},
                "body": {"content": f"<p>Message number {i}</p>"},
            })
        return msgs

    @patch.object(teams_dispatch, "fetch_messages")
    def test_writes_file_with_correct_format(self, mock_fetch):
        mock_fetch.return_value = self._make_messages(5)
        teams_dispatch.write_chat_cache("fake-chat-id", count=5)

        cache_path = os.path.join(self.tmpdir, "group-chat.txt")
        self.assertTrue(os.path.isfile(cache_path))

        with open(cache_path) as f:
            lines = f.read().strip().splitlines()

        self.assertEqual(len(lines), 5)
        # Should be chronological (oldest first)
        self.assertIn("User1", lines[0])
        self.assertIn("User5", lines[4])
        # Format: [timestamp] sender: message
        self.assertRegex(lines[0], r"^\[2026-03-29T10:01:00\] User1: Message number 1$")

    @patch.object(teams_dispatch, "fetch_messages")
    def test_50_messages(self, mock_fetch):
        mock_fetch.return_value = self._make_messages(50)
        teams_dispatch.write_chat_cache("fake-chat-id", count=50)

        cache_path = os.path.join(self.tmpdir, "group-chat.txt")
        with open(cache_path) as f:
            lines = f.read().strip().splitlines()

        self.assertEqual(len(lines), 50)
        mock_fetch.assert_called_once_with("fake-chat-id", count=50)

    @patch.object(teams_dispatch, "fetch_messages")
    def test_empty_messages(self, mock_fetch):
        mock_fetch.return_value = []
        teams_dispatch.write_chat_cache("fake-chat-id")

        cache_path = os.path.join(self.tmpdir, "group-chat.txt")
        self.assertFalse(os.path.isfile(cache_path))

    @patch.object(teams_dispatch, "fetch_messages")
    def test_strips_html_tags(self, mock_fetch):
        mock_fetch.return_value = [{
            "createdDateTime": "2026-03-29T10:00:00Z",
            "from": {"user": {"displayName": "Alice"}},
            "body": {"content": "<p>Hello <b>world</b></p>"},
        }]
        teams_dispatch.write_chat_cache("fake-chat-id")

        cache_path = os.path.join(self.tmpdir, "group-chat.txt")
        with open(cache_path) as f:
            content = f.read().strip()

        self.assertEqual(content, "[2026-03-29T10:00:00] Alice: Hello world")

    @patch.object(teams_dispatch, "fetch_messages")
    def test_collapses_newlines(self, mock_fetch):
        mock_fetch.return_value = [{
            "createdDateTime": "2026-03-29T10:00:00Z",
            "from": {"user": {"displayName": "Bob"}},
            "body": {"content": "line one\nline two\n  line three"},
        }]
        teams_dispatch.write_chat_cache("fake-chat-id")

        cache_path = os.path.join(self.tmpdir, "group-chat.txt")
        with open(cache_path) as f:
            lines = f.read().strip().splitlines()

        self.assertEqual(len(lines), 1)
        self.assertIn("line one line two line three", lines[0])

    @patch.object(teams_dispatch, "fetch_messages")
    def test_overwrites_on_each_call(self, mock_fetch):
        mock_fetch.return_value = self._make_messages(3)
        teams_dispatch.write_chat_cache("fake-chat-id")

        mock_fetch.return_value = self._make_messages(2)
        teams_dispatch.write_chat_cache("fake-chat-id")

        cache_path = os.path.join(self.tmpdir, "group-chat.txt")
        with open(cache_path) as f:
            lines = f.read().strip().splitlines()

        # Should have 2 lines, not 5
        self.assertEqual(len(lines), 2)

    @patch.object(teams_dispatch, "fetch_messages")
    def test_handles_missing_sender(self, mock_fetch):
        mock_fetch.return_value = [{
            "createdDateTime": "2026-03-29T10:00:00Z",
            "from": {},
            "body": {"content": "anonymous message"},
        }]
        teams_dispatch.write_chat_cache("fake-chat-id")

        cache_path = os.path.join(self.tmpdir, "group-chat.txt")
        with open(cache_path) as f:
            content = f.read().strip()

        self.assertIn("(unknown)", content)


if __name__ == "__main__":
    unittest.main()
