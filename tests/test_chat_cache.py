#!/usr/bin/env python3
"""Tests for chat cache in teams-chat-bridge.py.

Tests:
- update_chat_cache writes group-chat.txt and per-user files
- get_chat_context_prompt returns correct context prefix
- Reply capture appends to cache
- Cache limits (50 group, 20 per-user)
"""

import importlib.machinery
import importlib.util
import os
import sys
import tempfile
import unittest

# Load teams-chat-bridge as a module
_bridge_path = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "scripts", "teams-chat-bridge.py"
))

# Set required env vars before importing
os.environ.setdefault("GRAPH_TOKEN_FILE", "/dev/null")

loader = importlib.machinery.SourceFileLoader("teams_chat_bridge", _bridge_path)
spec = importlib.util.spec_from_loader("teams_chat_bridge", loader)
bridge = importlib.util.module_from_spec(spec)

# Prevent main() from running and avoid argparse issues
sys.modules["teams_chat_bridge"] = bridge
try:
    loader.exec_module(bridge)
except SystemExit:
    pass  # argparse may exit on import


def _make_message(sender, text, ts="2026-03-28T10:00:00Z", mid=None):
    """Create a fake Graph API message object."""
    return {
        "id": mid or f"msg-{hash(text) % 10000}",
        "createdDateTime": ts,
        "from": {"user": {"displayName": sender}},
        "body": {"content": f"<p>{text}</p>"},
    }


class TestUpdateChatCache(unittest.TestCase):
    """Test update_chat_cache writes correct files."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig = bridge.CHAT_CACHE_DIR
        bridge.CHAT_CACHE_DIR = self.tmpdir

    def tearDown(self):
        bridge.CHAT_CACHE_DIR = self._orig
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_group_file_created(self):
        msgs = [_make_message("Alice", "hello"), _make_message("Bob", "hi")]
        bridge.update_chat_cache(msgs)
        group_file = os.path.join(self.tmpdir, "group-chat.txt")
        self.assertTrue(os.path.isfile(group_file))

    def test_group_file_contains_messages(self):
        msgs = [_make_message("Alice", "hello"), _make_message("Bob", "hi")]
        bridge.update_chat_cache(msgs)
        with open(os.path.join(self.tmpdir, "group-chat.txt")) as f:
            content = f.read()
        self.assertIn("Alice: hello", content)
        self.assertIn("Bob: hi", content)

    def test_per_user_files_created(self):
        msgs = [_make_message("Alice", "hello"), _make_message("Bob", "hi")]
        bridge.update_chat_cache(msgs)
        alice_file = os.path.join(self.tmpdir, "users", "Alice.txt")
        bob_file = os.path.join(self.tmpdir, "users", "Bob.txt")
        self.assertTrue(os.path.isfile(alice_file))
        self.assertTrue(os.path.isfile(bob_file))

    def test_per_user_file_content(self):
        msgs = [_make_message("Alice", "hello"), _make_message("Alice", "how are you")]
        bridge.update_chat_cache(msgs)
        with open(os.path.join(self.tmpdir, "users", "Alice.txt")) as f:
            content = f.read()
        self.assertIn("hello", content)
        self.assertIn("how are you", content)

    def test_group_file_limit_50(self):
        msgs = [_make_message("Alice", f"msg{i}", ts=f"2026-03-28T10:{i:02d}:00Z")
                for i in range(60)]
        bridge.update_chat_cache(msgs)
        with open(os.path.join(self.tmpdir, "group-chat.txt")) as f:
            lines = [l for l in f.readlines() if l.strip()]
        self.assertLessEqual(len(lines), 50)

    def test_per_user_limit_20(self):
        msgs = [_make_message("Alice", f"msg{i}", ts=f"2026-03-28T10:{i:02d}:00Z")
                for i in range(30)]
        bridge.update_chat_cache(msgs)
        with open(os.path.join(self.tmpdir, "users", "Alice.txt")) as f:
            lines = [l for l in f.readlines() if l.strip()]
        self.assertLessEqual(len(lines), 20)

    def test_bot_replies_appended(self):
        msgs = [_make_message("Alice", "what is 2+2")]
        bridge.update_chat_cache(msgs, bot_replies=[("Alice", "what is 2+2", "4")])
        with open(os.path.join(self.tmpdir, "group-chat.txt")) as f:
            content = f.read()
        self.assertIn("Claude Bot: 4", content)

    def test_bot_reply_in_user_file(self):
        msgs = [_make_message("Alice", "hello")]
        bridge.update_chat_cache(msgs, bot_replies=[("Alice", "hello", "Hi Alice!")])
        with open(os.path.join(self.tmpdir, "users", "Alice.txt")) as f:
            content = f.read()
        self.assertIn("Claude Bot: Hi Alice!", content)

    def test_empty_messages_no_crash(self):
        bridge.update_chat_cache([])
        self.assertTrue(os.path.isfile(os.path.join(self.tmpdir, "group-chat.txt")))

    def test_special_chars_in_name(self):
        msgs = [_make_message("O'Brien, Jr.", "test")]
        bridge.update_chat_cache(msgs)
        # Should create a safe filename
        users_dir = os.path.join(self.tmpdir, "users")
        files = os.listdir(users_dir)
        self.assertEqual(len(files), 1)
        # File should exist and be readable
        with open(os.path.join(users_dir, files[0])) as f:
            self.assertIn("test", f.read())


class TestGetChatContextPrompt(unittest.TestCase):
    """Test get_chat_context_prompt returns correct file references."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig = bridge.CHAT_CACHE_DIR
        bridge.CHAT_CACHE_DIR = self.tmpdir

    def tearDown(self):
        bridge.CHAT_CACHE_DIR = self._orig
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_no_files_returns_empty(self):
        result = bridge.get_chat_context_prompt("Alice")
        self.assertEqual(result, "")

    def test_group_file_referenced(self):
        os.makedirs(os.path.join(self.tmpdir, "users"), exist_ok=True)
        with open(os.path.join(self.tmpdir, "group-chat.txt"), "w") as f:
            f.write("test\n")
        result = bridge.get_chat_context_prompt("Alice")
        self.assertIn("group-chat.txt", result)
        self.assertIn("CONTEXT", result)

    def test_user_file_referenced(self):
        os.makedirs(os.path.join(self.tmpdir, "users"), exist_ok=True)
        with open(os.path.join(self.tmpdir, "group-chat.txt"), "w") as f:
            f.write("test\n")
        with open(os.path.join(self.tmpdir, "users", "Alice.txt"), "w") as f:
            f.write("test\n")
        result = bridge.get_chat_context_prompt("Alice")
        self.assertIn("Alice.txt", result)
        self.assertIn("NEW MESSAGE", result)


class TestConversationContinuity(unittest.TestCase):
    """Test that chat cache preserves context across multiple exchanges.

    Simulates the flow: user sends "what is 2+2", Claude replies "4",
    user sends "multiply that by 10". Verifies the cache and context
    prompt contain the full conversation so Claude can answer "40".
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self._orig = bridge.CHAT_CACHE_DIR
        bridge.CHAT_CACHE_DIR = self.tmpdir

    def tearDown(self):
        bridge.CHAT_CACHE_DIR = self._orig
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_second_message_sees_first_exchange(self):
        """After caching msg1 + reply, cache files contain the full exchange."""
        # Step 1: User asks "what is 2+2"
        msg1 = _make_message("Alice", "what is 2+2", ts="2026-03-28T10:00:00Z")
        bridge.update_chat_cache(
            [msg1],
            bot_replies=[("Alice", "what is 2+2", "4")],
        )

        # Step 2: User asks "multiply that by 10" — cache should contain prior context
        msg2 = _make_message("Alice", "multiply that by 10", ts="2026-03-28T10:01:00Z")
        bridge.update_chat_cache(
            [msg2, msg1],
            bot_replies=[("Alice", "what is 2+2", "4")],
        )

        # Verify group chat has full conversation
        with open(os.path.join(self.tmpdir, "group-chat.txt")) as f:
            group = f.read()
        self.assertIn("what is 2+2", group)
        self.assertIn("Claude Bot: 4", group)
        self.assertIn("multiply that by 10", group)

    def test_user_file_has_full_exchange(self):
        """Per-user file shows both messages and Claude's reply."""
        msg1 = _make_message("Alice", "what is 2+2", ts="2026-03-28T10:00:00Z")
        bridge.update_chat_cache(
            [msg1],
            bot_replies=[("Alice", "what is 2+2", "4")],
        )

        msg2 = _make_message("Alice", "multiply that by 10", ts="2026-03-28T10:01:00Z")
        bridge.update_chat_cache(
            [msg2, msg1],
            bot_replies=[("Alice", "what is 2+2", "4")],
        )

        user_file = os.path.join(self.tmpdir, "users", "Alice.txt")
        with open(user_file) as f:
            content = f.read()
        self.assertIn("what is 2+2", content)
        self.assertIn("Claude Bot: 4", content)
        self.assertIn("multiply that by 10", content)

    def test_context_prompt_includes_files_after_exchange(self):
        """get_chat_context_prompt references both group and user files."""
        msg1 = _make_message("Alice", "what is 2+2", ts="2026-03-28T10:00:00Z")
        bridge.update_chat_cache(
            [msg1],
            bot_replies=[("Alice", "what is 2+2", "4")],
        )

        prompt = bridge.get_chat_context_prompt("Alice")
        self.assertIn("group-chat.txt", prompt)
        self.assertIn("Alice.txt", prompt)
        self.assertIn("CONTEXT", prompt)
        self.assertIn("NEW MESSAGE", prompt)

    def test_chronological_order_preserved(self):
        """Messages appear in chronological order in the cache."""
        msg1 = _make_message("Alice", "what is 2+2", ts="2026-03-28T10:00:00Z")
        msg2 = _make_message("Alice", "multiply that by 10", ts="2026-03-28T10:01:00Z")
        # Graph API returns newest first
        bridge.update_chat_cache(
            [msg2, msg1],
            bot_replies=[("Alice", "what is 2+2", "4")],
        )

        with open(os.path.join(self.tmpdir, "group-chat.txt")) as f:
            content = f.read()
        # "what is 2+2" should appear before "multiply that by 10"
        pos_first = content.index("what is 2+2")
        pos_second = content.index("multiply that by 10")
        self.assertLess(pos_first, pos_second,
                        "First message should appear before second in chronological order")

    def test_multiple_users_isolated(self):
        """Two users' conversations don't bleed into each other's files."""
        msg_a = _make_message("Alice", "what is 2+2", ts="2026-03-28T10:00:00Z")
        msg_b = _make_message("Bob", "what is 3+3", ts="2026-03-28T10:00:30Z")
        bridge.update_chat_cache(
            [msg_b, msg_a],
            bot_replies=[
                ("Alice", "what is 2+2", "4"),
                ("Bob", "what is 3+3", "6"),
            ],
        )

        with open(os.path.join(self.tmpdir, "users", "Alice.txt")) as f:
            alice = f.read()
        with open(os.path.join(self.tmpdir, "users", "Bob.txt")) as f:
            bob = f.read()

        self.assertIn("2+2", alice)
        self.assertIn("Claude Bot: 4", alice)
        self.assertNotIn("3+3", alice)

        self.assertIn("3+3", bob)
        self.assertIn("Claude Bot: 6", bob)
        self.assertNotIn("2+2", bob)

    def test_reply_capture_accumulates(self):
        """Multiple reply captures build up conversation history."""
        msg1 = _make_message("Alice", "what is 2+2", ts="2026-03-28T10:00:00Z")
        bridge.update_chat_cache(
            [msg1],
            bot_replies=[("Alice", "what is 2+2", "4")],
        )

        msg2 = _make_message("Alice", "multiply that by 10", ts="2026-03-28T10:01:00Z")
        bridge.update_chat_cache(
            [msg2, msg1],
            bot_replies=[
                ("Alice", "what is 2+2", "4"),
                ("Alice", "multiply that by 10", "40"),
            ],
        )

        with open(os.path.join(self.tmpdir, "group-chat.txt")) as f:
            content = f.read()
        self.assertIn("Claude Bot: 4", content)
        self.assertIn("Claude Bot: 40", content)


if __name__ == "__main__":
    unittest.main()
