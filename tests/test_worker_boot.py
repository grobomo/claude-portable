#!/usr/bin/env python3
"""Tests for worker zero-touch boot in bootstrap.sh.

Verifies that bootstrap.sh contains the worker boot sequence:
- SSH key generation and S3 upload
- Dispatcher registration
- Continuous-claude auto-start with proper env vars
"""

import os
import re
import subprocess
import unittest


BOOTSTRAP_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "scripts", "bootstrap.sh"
))
CCC_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "ccc"
))


class TestBootstrapWorkerBoot(unittest.TestCase):
    """Verify bootstrap.sh has worker zero-touch boot steps."""

    @classmethod
    def setUpClass(cls):
        with open(BOOTSTRAP_PATH) as f:
            cls.script = f.read()

    def test_syntax_valid(self):
        """bootstrap.sh passes bash -n."""
        with open(BOOTSTRAP_PATH, "rb") as f:
            content = f.read().replace(b"\r\n", b"\n")
        result = subprocess.run(["bash", "-n"], input=content, capture_output=True)
        self.assertEqual(result.returncode, 0,
                         f"Syntax error: {result.stderr.decode(errors='replace')}")

    def test_ssh_key_generation(self):
        """Bootstrap generates SSH keypair if missing."""
        self.assertIn("ssh-keygen", self.script)
        self.assertIn("id_ed25519", self.script)

    def test_ssh_key_s3_upload(self):
        """Bootstrap uploads SSH public key to S3 fleet-keys."""
        self.assertIn("fleet-keys", self.script)
        self.assertIn("aws s3 cp", self.script)

    def test_dispatcher_registration(self):
        """Bootstrap registers with dispatcher via POST /worker/register."""
        self.assertIn("/worker/register", self.script)
        self.assertIn("DISPATCHER_URL", self.script)

    def test_registration_payload_has_required_fields(self):
        """Registration JSON includes worker_id, ip, role, capabilities."""
        self.assertIn("worker_id", self.script)
        self.assertIn("capabilities", self.script)
        self.assertIn("tdd-pipeline", self.script)

    def test_boot_steps_before_continuous_claude(self):
        """SSH upload and registration happen BEFORE continuous-claude starts."""
        ssh_upload_idx = self.script.index("fleet-keys")
        cc_start_idx = self.script.index("Start continuous-claude runner")
        self.assertLess(ssh_upload_idx, cc_start_idx)

    def test_registration_is_non_fatal(self):
        """Registration failure doesn't prevent boot."""
        self.assertIn("non-fatal", self.script)

    def test_continuous_claude_autostart(self):
        """Bootstrap starts continuous-claude when env vars are set."""
        self.assertIn("CONTINUOUS_CLAUDE_ENABLED", self.script)
        self.assertIn("CONTINUOUS_CLAUDE_REPO", self.script)
        self.assertIn("continuous-claude.sh", self.script)


class TestCccDispatcherUrlConfig(unittest.TestCase):
    """Verify ccc launcher passes DISPATCHER_URL to workers."""

    @classmethod
    def setUpClass(cls):
        with open(CCC_PATH) as f:
            cls.ccc = f.read()

    def test_dispatcher_url_in_worker_env(self):
        """Workers get DISPATCHER_URL from ccc.config.json."""
        self.assertIn("dispatcher_url", self.ccc)
        self.assertIn("DISPATCHER_URL", self.ccc)

    def test_dispatcher_url_only_when_configured(self):
        """DISPATCHER_URL is only set when config has a value."""
        # Find the dispatcher_url block
        idx = self.ccc.index('dispatcher_url = CFG.get("dispatcher_url"')
        block = self.ccc[idx:idx + 200]
        self.assertIn("if dispatcher_url:", block)


if __name__ == "__main__":
    unittest.main()
