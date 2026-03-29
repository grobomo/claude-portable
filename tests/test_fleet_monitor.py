#!/usr/bin/env python3
"""Tests for fleet monitor daemon in git-dispatch.py.

Validates:
- Idle workers get stopped after 35-min stale threshold
- Busy workers (active Claude process) are left alone
- Unreachable workers (SSH fails) are retried, not killed
- Fresh workers (reported recently) are skipped
- Workers already stopping are skipped
- Unregistered workers are skipped
- Workers with no IP are skipped
"""

import json
import os
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

# Add scripts/ to path so we can import git-dispatch
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import importlib

# git-dispatch.py has a hyphen — use importlib
loader = importlib.machinery.SourceFileLoader(
    "git_dispatch",
    os.path.join(os.path.dirname(__file__), "..", "scripts", "git-dispatch.py"),
)
spec = importlib.util.spec_from_loader("git_dispatch", loader)
gd = importlib.util.module_from_spec(spec)
loader.exec_module(gd)


def _make_worker(registered=True, status="idle", last_report=None, ip="10.0.1.10"):
    """Helper to build a fleet roster entry."""
    return {
        "registered": registered,
        "status": status,
        "last_report": last_report or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ip": ip,
        "last_task": None,
        "completions": 0,
    }


def _stale_timestamp(minutes_ago=40):
    """Return an ISO timestamp N minutes in the past."""
    t = time.gmtime(time.time() - minutes_ago * 60)
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", t)


class TestParseIsoTimestamp(unittest.TestCase):
    def test_valid_z_suffix(self):
        ts = "2026-03-28T12:00:00Z"
        result = gd._parse_iso_timestamp(ts)
        self.assertGreater(result, 0)

    def test_empty_string(self):
        self.assertEqual(gd._parse_iso_timestamp(""), 0.0)

    def test_none(self):
        self.assertEqual(gd._parse_iso_timestamp(None), 0.0)

    def test_garbage(self):
        self.assertEqual(gd._parse_iso_timestamp("not-a-date"), 0.0)


class TestFleetMonitorTick(unittest.TestCase):
    def setUp(self):
        # Clear global state before each test
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()

    def tearDown(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()

    @patch.object(gd, "stop_worker_instance", return_value=True)
    @patch.object(gd, "_ssh_check_claude_process", return_value=False)
    def test_idle_stale_worker_gets_stopped(self, mock_ssh, mock_stop):
        """Worker stale for 40min + no Claude process → stop it."""
        with gd._fleet_roster_lock:
            gd._fleet_roster["worker-1"] = _make_worker(
                last_report=_stale_timestamp(40),
            )

        gd._fleet_monitor_tick("us-east-2")

        mock_ssh.assert_called_once_with("10.0.1.10", "worker-1")
        # stop_worker_instance is called in a thread — give it a moment
        time.sleep(0.1)
        mock_stop.assert_called_once_with("worker-1", "us-east-2")

        with gd._fleet_roster_lock:
            self.assertEqual(gd._fleet_roster["worker-1"]["status"], "stopping")
            self.assertEqual(gd._fleet_roster["worker-1"]["stopped_by"], "fleet-monitor")

    @patch.object(gd, "stop_worker_instance")
    @patch.object(gd, "_ssh_check_claude_process", return_value=True)
    def test_busy_worker_not_stopped(self, mock_ssh, mock_stop):
        """Worker stale but has active Claude process → leave it alone."""
        with gd._fleet_roster_lock:
            gd._fleet_roster["worker-2"] = _make_worker(
                last_report=_stale_timestamp(40),
            )

        gd._fleet_monitor_tick("us-east-2")

        mock_ssh.assert_called_once()
        mock_stop.assert_not_called()
        with gd._fleet_roster_lock:
            self.assertEqual(gd._fleet_roster["worker-2"]["status"], "idle")

    @patch.object(gd, "stop_worker_instance")
    @patch.object(gd, "_ssh_check_claude_process", return_value=None)
    def test_unreachable_worker_not_stopped(self, mock_ssh, mock_stop):
        """Worker stale + SSH unreachable → retry next tick, don't kill."""
        with gd._fleet_roster_lock:
            gd._fleet_roster["worker-3"] = _make_worker(
                last_report=_stale_timestamp(40),
            )

        gd._fleet_monitor_tick("us-east-2")

        mock_ssh.assert_called_once()
        mock_stop.assert_not_called()
        with gd._fleet_roster_lock:
            self.assertEqual(gd._fleet_roster["worker-3"]["status"], "idle")

    @patch.object(gd, "stop_worker_instance")
    @patch.object(gd, "_ssh_check_claude_process")
    def test_fresh_worker_skipped(self, mock_ssh, mock_stop):
        """Worker reported 5 min ago → skip entirely (no SSH check)."""
        with gd._fleet_roster_lock:
            gd._fleet_roster["worker-4"] = _make_worker(
                last_report=_stale_timestamp(5),
            )

        gd._fleet_monitor_tick("us-east-2")

        mock_ssh.assert_not_called()
        mock_stop.assert_not_called()

    @patch.object(gd, "stop_worker_instance")
    @patch.object(gd, "_ssh_check_claude_process")
    def test_35min_boundary(self, mock_ssh, mock_stop):
        """Worker reported exactly 34 min ago → still fresh, skip."""
        with gd._fleet_roster_lock:
            gd._fleet_roster["worker-5"] = _make_worker(
                last_report=_stale_timestamp(34),
            )

        gd._fleet_monitor_tick("us-east-2")

        mock_ssh.assert_not_called()
        mock_stop.assert_not_called()

    @patch.object(gd, "stop_worker_instance")
    @patch.object(gd, "_ssh_check_claude_process")
    def test_stopping_worker_skipped(self, mock_ssh, mock_stop):
        """Worker already in 'stopping' state → skip."""
        with gd._fleet_roster_lock:
            gd._fleet_roster["worker-6"] = _make_worker(
                status="stopping",
                last_report=_stale_timestamp(40),
            )

        gd._fleet_monitor_tick("us-east-2")

        mock_ssh.assert_not_called()
        mock_stop.assert_not_called()

    @patch.object(gd, "stop_worker_instance")
    @patch.object(gd, "_ssh_check_claude_process")
    def test_unregistered_worker_skipped(self, mock_ssh, mock_stop):
        """Worker not registered → skip (registration monitor handles it)."""
        with gd._fleet_roster_lock:
            gd._fleet_roster["worker-7"] = _make_worker(
                registered=False,
                last_report=_stale_timestamp(40),
            )

        gd._fleet_monitor_tick("us-east-2")

        mock_ssh.assert_not_called()
        mock_stop.assert_not_called()

    @patch.object(gd, "stop_worker_instance")
    @patch.object(gd, "_ssh_check_claude_process")
    def test_no_ip_worker_skipped(self, mock_ssh, mock_stop):
        """Worker stale but has no IP → can't SSH, skip."""
        with gd._fleet_roster_lock:
            gd._fleet_roster["worker-8"] = _make_worker(
                ip="",
                last_report=_stale_timestamp(40),
            )

        gd._fleet_monitor_tick("us-east-2")

        mock_ssh.assert_not_called()
        mock_stop.assert_not_called()

    @patch.object(gd, "stop_worker_instance", return_value=True)
    @patch.object(gd, "_ssh_check_claude_process")
    def test_multiple_workers_mixed(self, mock_ssh, mock_stop):
        """Mix of fresh, stale-busy, and stale-idle workers."""
        mock_ssh.side_effect = lambda ip, name: {
            "worker-a": True,   # busy
            "worker-b": False,  # idle
        }.get(name)

        with gd._fleet_roster_lock:
            gd._fleet_roster["worker-fresh"] = _make_worker(
                last_report=_stale_timestamp(5),
            )
            gd._fleet_roster["worker-a"] = _make_worker(
                last_report=_stale_timestamp(40),
                ip="10.0.1.11",
            )
            gd._fleet_roster["worker-b"] = _make_worker(
                last_report=_stale_timestamp(40),
                ip="10.0.1.12",
            )

        gd._fleet_monitor_tick("us-east-2")
        time.sleep(0.1)

        # SSH checked stale workers only (not fresh)
        self.assertEqual(mock_ssh.call_count, 2)
        # Only worker-b (idle+stale) gets stopped
        mock_stop.assert_called_once_with("worker-b", "us-east-2")


def _hb_timestamp(seconds_ago=0):
    """Return an ISO timestamp N seconds in the past."""
    t = time.gmtime(time.time() - seconds_ago)
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", t)


class TestHeartbeatStaleness(unittest.TestCase):
    """Test heartbeat miss detection in fleet monitor."""

    def setUp(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()

    def tearDown(self):
        with gd._fleet_roster_lock:
            gd._fleet_roster.clear()

    @patch.object(gd, "stop_worker_instance")
    @patch.object(gd, "_ssh_check_claude_process")
    def test_fresh_heartbeat_marked_healthy(self, mock_ssh, mock_stop):
        """Worker with recent heartbeat is marked healthy."""
        with gd._fleet_roster_lock:
            gd._fleet_roster["hb-1"] = _make_worker(
                last_report=_stale_timestamp(5),
            )
            gd._fleet_roster["hb-1"]["last_heartbeat"] = _hb_timestamp(10)

        gd._fleet_monitor_tick("us-east-2")

        with gd._fleet_roster_lock:
            self.assertTrue(gd._fleet_roster["hb-1"]["healthy"])
            self.assertEqual(gd._fleet_roster["hb-1"]["missed_heartbeats"], 0)

    @patch.object(gd, "stop_worker_instance")
    @patch.object(gd, "_ssh_check_claude_process")
    def test_stale_heartbeat_marked_unhealthy(self, mock_ssh, mock_stop):
        """Worker missing 3+ heartbeats is marked unhealthy."""
        with gd._fleet_roster_lock:
            gd._fleet_roster["hb-2"] = _make_worker(
                last_report=_stale_timestamp(5),
            )
            gd._fleet_roster["hb-2"]["last_heartbeat"] = _hb_timestamp(100)

        gd._fleet_monitor_tick("us-east-2")

        with gd._fleet_roster_lock:
            self.assertFalse(gd._fleet_roster["hb-2"]["healthy"])
            self.assertGreaterEqual(gd._fleet_roster["hb-2"]["missed_heartbeats"], 3)

    @patch.object(gd, "stop_worker_instance")
    @patch.object(gd, "_ssh_check_claude_process")
    def test_no_heartbeat_field_skipped(self, mock_ssh, mock_stop):
        """Worker without last_heartbeat field is not marked unhealthy."""
        with gd._fleet_roster_lock:
            gd._fleet_roster["hb-3"] = _make_worker(
                last_report=_stale_timestamp(5),
            )
            # No last_heartbeat key

        gd._fleet_monitor_tick("us-east-2")

        with gd._fleet_roster_lock:
            self.assertNotIn("healthy", gd._fleet_roster["hb-3"])

    @patch.object(gd, "stop_worker_instance")
    @patch.object(gd, "_ssh_check_claude_process")
    def test_heartbeat_boundary_89s_still_healthy(self, mock_ssh, mock_stop):
        """89 seconds since last heartbeat (< 90s threshold) → still healthy."""
        with gd._fleet_roster_lock:
            gd._fleet_roster["hb-4"] = _make_worker(
                last_report=_stale_timestamp(5),
            )
            gd._fleet_roster["hb-4"]["last_heartbeat"] = _hb_timestamp(89)

        gd._fleet_monitor_tick("us-east-2")

        with gd._fleet_roster_lock:
            self.assertTrue(gd._fleet_roster["hb-4"]["healthy"])


if __name__ == "__main__":
    unittest.main()
