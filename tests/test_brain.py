#!/usr/bin/env python3
"""
Tests for brain/ modules -- storage, fleet, blockers, conversation, context.

All tests run without API keys or AWS access (mocked where needed).
"""

import json
import os
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.storage import Storage
from brain.fleet import Fleet
from brain.blockers import BlockerResolver
from brain.context import build_system_prompt, estimate_tokens, _read_file
from brain.conversation import ConversationManager


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.storage = Storage(data_dir=self.tmpdir)

    def test_jsonl_append_and_read(self):
        self.storage.append_jsonl("test.jsonl", {"key": "val1"})
        self.storage.append_jsonl("test.jsonl", {"key": "val2"})
        records = self.storage.read_jsonl("test.jsonl")
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["key"], "val1")
        self.assertEqual(records[1]["key"], "val2")

    def test_jsonl_read_last_n(self):
        for i in range(10):
            self.storage.append_jsonl("test.jsonl", {"i": i})
        records = self.storage.read_jsonl("test.jsonl", last_n=3)
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]["i"], 7)

    def test_jsonl_read_nonexistent(self):
        self.assertEqual(self.storage.read_jsonl("nope.jsonl"), [])

    def test_jsonl_count(self):
        for i in range(5):
            self.storage.append_jsonl("test.jsonl", {"i": i})
        self.assertEqual(self.storage.count_jsonl("test.jsonl"), 5)
        self.assertEqual(self.storage.count_jsonl("nope.jsonl"), 0)

    def test_jsonl_truncate(self):
        for i in range(10):
            self.storage.append_jsonl("test.jsonl", {"i": i})
        self.storage.truncate_jsonl("test.jsonl", keep_last_n=3)
        records = self.storage.read_jsonl("test.jsonl")
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]["i"], 7)

    def test_jsonl_truncate_noop_when_small(self):
        for i in range(2):
            self.storage.append_jsonl("test.jsonl", {"i": i})
        self.storage.truncate_jsonl("test.jsonl", keep_last_n=5)
        self.assertEqual(len(self.storage.read_jsonl("test.jsonl")), 2)

    def test_json_read_write(self):
        self.storage.write_json("config.json", {"a": 1, "b": [2, 3]})
        data = self.storage.read_json("config.json")
        self.assertEqual(data, {"a": 1, "b": [2, 3]})

    def test_json_read_nonexistent(self):
        self.assertEqual(self.storage.read_json("nope.json"), {})
        self.assertEqual(self.storage.read_json("nope.json", default=[]), [])

    def test_record_task_outcome(self):
        self.storage.record_task_outcome("t1", "Fix the bug", "success", "w1")
        outcomes = self.storage.get_recent_outcomes()
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["task_id"], "t1")
        self.assertEqual(outcomes[0]["outcome"], "success")

    def test_message_append_and_get(self):
        self.storage.append_message("user", "hello")
        self.storage.append_message("assistant", "hi there")
        msgs = self.storage.get_messages()
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0], {"role": "user", "content": "hello"})
        self.assertEqual(msgs[1], {"role": "assistant", "content": "hi there"})

    def test_clear_messages(self):
        self.storage.append_message("user", "hello")
        self.storage.clear_messages()
        self.assertEqual(self.storage.get_messages(), [])


class TestFleet(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.storage = Storage(data_dir=self.tmpdir)
        self.fleet = Fleet(self.storage)

    def test_register_worker(self):
        self.fleet.register_worker("w1", ip="10.0.0.1")
        workers = self.fleet.get_all_workers()
        self.assertEqual(len(workers), 1)
        self.assertEqual(workers[0]["id"], "w1")
        self.assertEqual(workers[0]["ip"], "10.0.0.1")
        self.assertEqual(workers[0]["status"], "idle")

    def test_update_status(self):
        self.fleet.register_worker("w1")
        self.fleet.update_worker_status("w1", "busy", "task-123")
        w = self.fleet.get_all_workers()[0]
        self.assertEqual(w["status"], "busy")
        self.assertEqual(w["current_task"], "task-123")

    def test_record_task_completion(self):
        self.fleet.register_worker("w1")
        self.fleet.record_task_completion("w1", "chrome-ext", True)
        self.fleet.record_task_completion("w1", "audio", True)
        self.fleet.record_task_completion("w1", "audio", False)
        w = self.fleet.get_all_workers()[0]
        self.assertEqual(w["tasks_completed"], 2)
        self.assertEqual(w["tasks_failed"], 1)
        self.assertIn("chrome-ext", w["areas"])
        self.assertIn("audio", w["areas"])

    def test_get_idle_workers(self):
        self.fleet.register_worker("w1")
        self.fleet.register_worker("w2")
        self.fleet.update_worker_status("w1", "busy")
        idle = self.fleet.get_idle_workers()
        self.assertEqual(len(idle), 1)
        self.assertEqual(idle[0]["id"], "w2")

    def test_select_best_worker_prefers_area_match(self):
        self.fleet.register_worker("w1")
        self.fleet.register_worker("w2")
        self.fleet.record_task_completion("w1", "chrome", True)
        self.fleet.record_task_completion("w2", "audio", True)
        # Task about chrome should prefer w1
        best = self.fleet.select_best_worker("Fix chrome extension click tracking")
        self.assertEqual(best, "w1")

    def test_select_best_worker_avoids_busy(self):
        self.fleet.register_worker("w1")
        self.fleet.register_worker("w2")
        self.fleet.update_worker_status("w1", "busy")
        best = self.fleet.select_best_worker("Any task")
        self.assertEqual(best, "w2")

    def test_select_best_worker_empty_fleet(self):
        self.assertIsNone(self.fleet.select_best_worker("Any task"))

    def test_get_summary(self):
        self.fleet.register_worker("w1")
        self.fleet.record_task_completion("w1", "chrome", True)
        summary = self.fleet.get_summary()
        self.assertIn("w1", summary)
        self.assertIn("1/1", summary)

    def test_remove_worker(self):
        self.fleet.register_worker("w1")
        self.fleet.register_worker("w2")
        self.fleet.remove_worker("w1")
        self.assertEqual(len(self.fleet.get_all_workers()), 1)


class TestBlockerResolver(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.storage = Storage(data_dir=self.tmpdir)
        self.resolver = BlockerResolver(self.storage)

    def test_match_known_patterns_auth(self):
        matches = self.resolver.match_known_patterns("Error: 403 permission denied on S3")
        categories = [m["category"] for m in matches]
        self.assertIn("auth", categories)

    def test_match_known_patterns_timeout(self):
        matches = self.resolver.match_known_patterns("Operation timed out after 30s")
        categories = [m["category"] for m in matches]
        self.assertIn("timeout", categories)

    def test_match_known_patterns_no_match(self):
        matches = self.resolver.match_known_patterns("Everything is fine")
        self.assertEqual(matches, [])

    def test_record_and_search_past_resolutions(self):
        self.resolver.record_blocker(
            "S3 permission denied when uploading audio",
            worker_id="w1", task_id="t1",
            resolution="Added s3:PutObject to IAM role",
        )
        results = self.resolver.search_past_resolutions("permission denied uploading files")
        self.assertGreater(len(results), 0)
        self.assertIn("IAM role", results[0]["resolution"])

    def test_search_no_past_blockers(self):
        results = self.resolver.search_past_resolutions("some error")
        self.assertEqual(results, [])

    def test_suggest_resolution_known(self):
        result = self.resolver.suggest_resolution("403 forbidden on API call")
        self.assertIn("known_fixes", result)
        self.assertGreater(len(result["known_fixes"]), 0)
        self.assertIn("recommended_action", result)

    def test_suggest_resolution_from_past(self):
        self.resolver.record_blocker(
            "Chrome extension manifest invalid",
            resolution="Fixed manifest version to 3",
        )
        result = self.resolver.suggest_resolution("Chrome extension manifest error")
        self.assertIn("past_resolutions", result)

    def test_suggest_resolution_unknown(self):
        result = self.resolver.suggest_resolution("Completely novel issue xyz")
        self.assertIn("recommended_action", result)
        self.assertIn("No known resolution", result["recommended_action"])

    def test_resolve_blocker(self):
        self.resolver.record_blocker("S3 error", task_id="t1")
        self.resolver.resolve_blocker("t1", "Fixed IAM policy")
        records = self.storage.read_jsonl("blockers.jsonl")
        self.assertEqual(records[0]["resolution"], "Fixed IAM policy")


class TestContext(unittest.TestCase):
    def test_build_system_prompt_basic(self):
        with tempfile.TemporaryDirectory() as d:
            # Create a minimal CLAUDE.md
            with open(os.path.join(d, "CLAUDE.md"), "w") as f:
                f.write("# Test Project\nThis is a test.")
            prompt = build_system_prompt(d)
            self.assertIn("dispatcher brain", prompt)
            self.assertIn("Test Project", prompt)

    def test_build_system_prompt_with_fleet_and_tasks(self):
        with tempfile.TemporaryDirectory() as d:
            prompt = build_system_prompt(
                d,
                fleet_summary="Workers:\n  w1: idle",
                task_summaries="- Task: fix bug | Outcome: success",
            )
            self.assertIn("w1: idle", prompt)
            self.assertIn("fix bug", prompt)

    def test_estimate_tokens(self):
        self.assertEqual(estimate_tokens(""), 0)
        self.assertEqual(estimate_tokens("a" * 100), 25)

    def test_read_file_nonexistent(self):
        self.assertEqual(_read_file("/nonexistent/path"), "")

    def test_read_file_truncation(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("x" * 200)
            f.flush()
            content = _read_file(f.name, max_chars=50)
            self.assertEqual(len(content), 50 + len("\n... (truncated)"))
            os.unlink(f.name)


class TestConversationManager(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.storage = Storage(data_dir=self.tmpdir)
        self.repo_dir = tempfile.mkdtemp()
        # Create minimal CLAUDE.md
        with open(os.path.join(self.repo_dir, "CLAUDE.md"), "w") as f:
            f.write("# Test\nTest project.")

    def test_parse_spec_response_delimited(self):
        text = (
            "===SPEC===\n# Spec\nDo the thing\n"
            "===PLAN===\n# Plan\nStep 1\n"
            "===TASKS===\n# Tasks\n- [ ] Task 1\n"
        )
        result = ConversationManager._parse_spec_response(text, "test")
        self.assertIn("Do the thing", result["spec"])
        self.assertIn("Step 1", result["plan"])
        self.assertIn("Task 1", result["tasks"])

    def test_parse_spec_response_no_delimiters(self):
        text = "# Full Specification\nJust a big block of text."
        result = ConversationManager._parse_spec_response(text, "test")
        self.assertIn("Full Specification", result["spec"])
        self.assertIn("Plan", result["plan"])

    def test_fallback_spec(self):
        result = ConversationManager._fallback_spec("Build a widget")
        self.assertIn("Build a widget", result["spec"])
        self.assertIn("Success Criteria", result["spec"])
        self.assertIn("Plan", result["plan"])

    @patch("brain.conversation._create_client")
    def test_generate_spec_success(self, mock_create):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=(
            "===SPEC===\n# Spec\nBuild widget\n"
            "===PLAN===\n# Plan\nUse React\n"
            "===TASKS===\n# Tasks\n- [ ] Create component\n"
        ))]
        mock_client.messages.create.return_value = mock_response
        mock_create.return_value = mock_client

        mgr = ConversationManager(self.storage, self.repo_dir)
        mgr._client = mock_client

        result = mgr.generate_spec("Build a widget", "req-1")
        self.assertIn("Build widget", result["spec"])
        self.assertIn("React", result["plan"])
        self.assertIn("Create component", result["tasks"])

        # Verify messages were persisted
        msgs = self.storage.get_messages()
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0]["role"], "user")
        self.assertEqual(msgs[1]["role"], "assistant")

    @patch("brain.conversation._create_client")
    def test_generate_spec_api_failure_returns_fallback(self, mock_create):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API down")
        mock_create.return_value = mock_client

        mgr = ConversationManager(self.storage, self.repo_dir)
        mgr._client = mock_client

        result = mgr.generate_spec("Build a widget", "req-1")
        self.assertIn("Build a widget", result["spec"])
        self.assertIn("Success Criteria", result["spec"])

    @patch("brain.conversation._create_client")
    def test_append_outcome(self, mock_create):
        mgr = ConversationManager(self.storage, self.repo_dir)
        mgr.append_outcome("t1", "Fix bug", "success", "w1")

        msgs = self.storage.get_messages()
        self.assertEqual(len(msgs), 1)
        self.assertIn("Task completed", msgs[0]["content"])

        outcomes = self.storage.get_recent_outcomes()
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["task_id"], "t1")

    @patch("brain.conversation._create_client")
    def test_context_summarization_triggered(self, mock_create):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Summary of previous work.")]
        mock_client.messages.create.return_value = mock_response
        mock_create.return_value = mock_client

        mgr = ConversationManager(self.storage, self.repo_dir)
        mgr._client = mock_client

        # Simulate large conversation
        big_msg = "x" * 200_000  # ~50k tokens
        mgr._messages = [
            {"role": "user", "content": big_msg},
            {"role": "assistant", "content": big_msg},
            {"role": "user", "content": big_msg},
            {"role": "assistant", "content": big_msg},
        ]
        mgr._total_tokens = 200_000

        mgr._check_context_limit()

        # After summarization, should have exactly 2 messages
        self.assertEqual(len(mgr._messages), 2)
        self.assertEqual(mgr._messages[0]["role"], "user")
        self.assertIn("summary", mgr._messages[0]["content"].lower())

    def test_invalidate_system_prompt(self):
        mgr = ConversationManager(self.storage, self.repo_dir)
        # Force cache
        _ = mgr._get_system_prompt()
        self.assertIsNotNone(mgr._system_prompt)
        mgr.invalidate_system_prompt()
        self.assertIsNone(mgr._system_prompt)


class TestGetApiKey(unittest.TestCase):
    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-123"})
    def test_env_var_priority(self):
        from brain.conversation import _get_api_key
        self.assertEqual(_get_api_key(), "test-key-123")

    @patch.dict(os.environ, {}, clear=True)
    def test_secrets_manager_raw_key(self):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        mock_boto3 = MagicMock()
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": "sk-ant-raw-key"
        }
        mock_boto3.client.return_value = mock_client
        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            from brain.conversation import _get_api_key
            self.assertEqual(_get_api_key(), "sk-ant-raw-key")

    @patch.dict(os.environ, {}, clear=True)
    def test_secrets_manager_json_key(self):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        mock_boto3 = MagicMock()
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": '{"api_key": "sk-ant-json-key"}'
        }
        mock_boto3.client.return_value = mock_client
        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            from brain.conversation import _get_api_key
            self.assertEqual(_get_api_key(), "sk-ant-json-key")


if __name__ == "__main__":
    unittest.main()
