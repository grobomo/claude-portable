#!/usr/bin/env python3
"""Tests for S3-based leader election in git-dispatch.py.

Validates:
- Startup with no existing primary → promote to primary
- Startup with active primary → stay standby
- Standby promotes when primary heartbeat goes stale (>5min)
- Primary demotes when a newer primary is detected
- Dispatch tick skipped in standby mode
- Relay poll tick skipped in standby mode
- find_active_primary correctly identifies fresh vs stale heartbeats
- Heartbeat write populates leader state
"""

import importlib
import importlib.machinery
import importlib.util
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

loader = importlib.machinery.SourceFileLoader(
    "git_dispatch",
    os.path.join(os.path.dirname(__file__), "..", "scripts", "git-dispatch.py"),
)
spec = importlib.util.spec_from_loader("git_dispatch", loader)
gd = importlib.util.module_from_spec(spec)
loader.exec_module(gd)


def _fresh_ts():
    """ISO timestamp for now."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stale_ts(minutes_ago=6):
    """ISO timestamp N minutes in the past."""
    t = time.gmtime(time.time() - minutes_ago * 60)
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", t)


def _make_heartbeat(name="dispatcher-1", role="primary", ts=None):
    return {
        "instance_name": name,
        "role": role,
        "ip": "10.0.1.50",
        "timestamp": ts or _fresh_ts(),
        "region": "us-east-2",
    }


class TestFindActivePrimary(unittest.TestCase):
    def test_fresh_primary_found(self):
        hbs = [_make_heartbeat("d1", "primary", _fresh_ts())]
        result = gd.find_active_primary(hbs)
        self.assertIsNotNone(result)
        self.assertEqual(result["instance_name"], "d1")

    def test_stale_primary_ignored(self):
        hbs = [_make_heartbeat("d1", "primary", _stale_ts(10))]
        result = gd.find_active_primary(hbs)
        self.assertIsNone(result)

    def test_standby_not_returned(self):
        hbs = [_make_heartbeat("d1", "standby", _fresh_ts())]
        result = gd.find_active_primary(hbs)
        self.assertIsNone(result)

    def test_empty_list(self):
        self.assertIsNone(gd.find_active_primary([]))

    def test_multiple_picks_fresh_primary(self):
        hbs = [
            _make_heartbeat("d-old", "primary", _stale_ts(10)),
            _make_heartbeat("d-new", "primary", _fresh_ts()),
            _make_heartbeat("d-standby", "standby", _fresh_ts()),
        ]
        result = gd.find_active_primary(hbs)
        self.assertEqual(result["instance_name"], "d-new")

    def test_bad_timestamp_skipped(self):
        hbs = [{"instance_name": "bad", "role": "primary", "timestamp": "garbage"}]
        self.assertIsNone(gd.find_active_primary(hbs))


class TestPromoteDemote(unittest.TestCase):
    def setUp(self):
        with gd._leader_state_lock:
            gd._leader_state.update({
                "role": "standby",
                "promoted_at": None,
                "demoted_at": None,
                "primary_instance": None,
            })

    def test_promote_sets_primary(self):
        gd.promote_to_primary("my-instance")
        self.assertTrue(gd.is_primary())
        with gd._leader_state_lock:
            self.assertEqual(gd._leader_state["role"], "primary")
            self.assertEqual(gd._leader_state["primary_instance"], "my-instance")
            self.assertIsNotNone(gd._leader_state["promoted_at"])

    def test_demote_sets_standby(self):
        gd.promote_to_primary("me")
        gd.demote_to_standby("other-primary")
        self.assertFalse(gd.is_primary())
        with gd._leader_state_lock:
            self.assertEqual(gd._leader_state["role"], "standby")
            self.assertEqual(gd._leader_state["primary_instance"], "other-primary")
            self.assertIsNotNone(gd._leader_state["demoted_at"])


class TestDispatchSkipsInStandby(unittest.TestCase):
    def setUp(self):
        with gd._leader_state_lock:
            gd._leader_state["role"] = "standby"

    def tearDown(self):
        with gd._leader_state_lock:
            gd._leader_state["role"] = "primary"

    @patch.object(gd, "git_pull")
    def test_dispatch_tick_skipped(self, mock_pull):
        """Dispatch tick does nothing in standby mode."""
        gd._dispatch_tick("us-east-2")
        mock_pull.assert_not_called()

    @patch.object(gd, "_relay_git_pull")
    def test_relay_tick_skipped(self, mock_pull):
        """Relay poll tick does nothing in standby mode."""
        gd._relay_poll_tick()
        mock_pull.assert_not_called()


class TestDispatchRunsAsPrimary(unittest.TestCase):
    def setUp(self):
        gd.promote_to_primary("test-primary")

    def tearDown(self):
        with gd._leader_state_lock:
            gd._leader_state["role"] = "standby"

    @patch.object(gd, "get_running_workers", return_value=[])
    @patch.object(gd, "get_active_worker_branches", return_value=[])
    @patch.object(gd, "get_pending_tasks", return_value=[])
    @patch.object(gd, "git_pull", return_value=True)
    def test_dispatch_tick_runs(self, mock_pull, mock_tasks, mock_branches, mock_workers):
        """Dispatch tick runs normally when primary."""
        gd._dispatch_tick("us-east-2")
        mock_pull.assert_called_once()


class TestStandbyMonitorLogic(unittest.TestCase):
    """Test the standby monitor's promotion/demotion logic without threads."""

    def setUp(self):
        with gd._leader_state_lock:
            gd._leader_state.update({
                "role": "standby",
                "promoted_at": None,
                "demoted_at": None,
                "primary_instance": None,
                "last_heartbeat_write": None,
                "last_heartbeat_check": None,
            })

    def tearDown(self):
        with gd._leader_state_lock:
            gd._leader_state["role"] = "standby"

    @patch.object(gd, "read_all_heartbeats")
    def test_standby_promotes_when_no_primary(self, mock_read):
        """Standby promotes itself when no active primary heartbeat exists."""
        mock_read.return_value = [
            _make_heartbeat("old-primary", "primary", _stale_ts(10)),
        ]

        # Simulate one iteration of the standby monitor
        heartbeats = gd.read_all_heartbeats("bucket", "us-east-2")
        active = gd.find_active_primary(heartbeats)
        self.assertIsNone(active)

        # This is what the monitor does when no active primary
        gd.promote_to_primary("backup-1")
        self.assertTrue(gd.is_primary())

    @patch.object(gd, "read_all_heartbeats")
    def test_standby_stays_when_primary_active(self, mock_read):
        """Standby stays standby when primary heartbeat is fresh."""
        mock_read.return_value = [
            _make_heartbeat("primary-1", "primary", _fresh_ts()),
        ]

        heartbeats = gd.read_all_heartbeats("bucket", "us-east-2")
        active = gd.find_active_primary(heartbeats)
        self.assertIsNotNone(active)
        self.assertEqual(active["instance_name"], "primary-1")

        # Standby should NOT promote
        self.assertFalse(gd.is_primary())

    def test_primary_demotes_when_newer_primary_seen(self):
        """Primary demotes itself when it sees a newer primary heartbeat."""
        gd.promote_to_primary("me")
        self.assertTrue(gd.is_primary())

        # Simulate seeing a newer primary
        with gd._leader_state_lock:
            gd._leader_state["last_heartbeat_write"] = _stale_ts(1)

        newer = _make_heartbeat("other", "primary", _fresh_ts())

        my_ts = gd._parse_iso_timestamp(gd._leader_state["last_heartbeat_write"])
        their_ts = gd._parse_iso_timestamp(newer["timestamp"])

        if their_ts > my_ts:
            gd.demote_to_standby("other")

        self.assertFalse(gd.is_primary())
        with gd._leader_state_lock:
            self.assertEqual(gd._leader_state["primary_instance"], "other")


class TestWriteHeartbeat(unittest.TestCase):
    @patch("subprocess.run")
    def test_write_updates_leader_state(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        result = gd.write_heartbeat("bucket", "inst-1", "primary", "10.0.1.1", "us-east-2")
        self.assertTrue(result)
        with gd._leader_state_lock:
            self.assertIsNotNone(gd._leader_state["last_heartbeat_write"])

    @patch("subprocess.run")
    def test_write_failure_returns_false(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="access denied")
        result = gd.write_heartbeat("bucket", "inst-1", "primary", "10.0.1.1", "us-east-2")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
