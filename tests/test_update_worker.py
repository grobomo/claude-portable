#!/usr/bin/env python3
"""Tests for scripts/update-worker.sh -- worker self-update from ECR.

Verifies the script has the correct structure:
- ECR login
- Image pull and comparison
- Container config capture via docker inspect
- Stop/start with same volumes and env
- Dispatcher re-registration
"""

import os
import re
import subprocess
import unittest


SCRIPT_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "scripts", "update-worker.sh"
))


class TestUpdateWorkerScript(unittest.TestCase):
    """Verify update-worker.sh structure and correctness."""

    @classmethod
    def setUpClass(cls):
        with open(SCRIPT_PATH) as f:
            cls.script = f.read()

    def test_syntax_valid(self):
        """update-worker.sh passes bash -n."""
        with open(SCRIPT_PATH, "rb") as f:
            content = f.read().replace(b"\r\n", b"\n")
        result = subprocess.run(["bash", "-n"], input=content, capture_output=True)
        self.assertEqual(result.returncode, 0,
                         f"Syntax error: {result.stderr.decode(errors='replace')}")

    def test_set_euo_pipefail(self):
        """Script uses strict mode."""
        self.assertIn("set -euo pipefail", self.script)

    def test_ecr_repo_defined(self):
        """ECR repo URL is correctly defined."""
        self.assertIn(
            "752266476357.dkr.ecr.us-east-2.amazonaws.com/hackathon26/worker",
            self.script,
        )

    def test_default_region(self):
        """Default AWS region is us-east-2."""
        self.assertIn('AWS_REGION="${AWS_REGION:-us-east-2}"', self.script)

    def test_ecr_login(self):
        """Script logs into ECR."""
        self.assertIn("aws ecr get-login-password", self.script)
        self.assertIn("docker login", self.script)

    def test_image_pull(self):
        """Script pulls latest image."""
        self.assertIn("docker pull", self.script)
        self.assertIn(":latest", self.script)

    def test_image_comparison_skips_if_current(self):
        """Script compares old and new image IDs and exits if unchanged."""
        self.assertIn("OLD_IMAGE_ID", self.script)
        self.assertIn("NEW_IMAGE_ID", self.script)
        self.assertIn("Nothing to do", self.script)

    def test_captures_env_vars(self):
        """Script extracts env vars from running container."""
        self.assertIn(".Config.Env", self.script)
        self.assertIn("ENV_ARGS", self.script)

    def test_captures_volumes(self):
        """Script extracts volume mounts from running container."""
        self.assertIn(".Mounts", self.script)
        self.assertIn("VOLUME_ARGS", self.script)

    def test_captures_ports(self):
        """Script extracts port mappings."""
        self.assertIn("PORT_ARGS", self.script)
        self.assertIn(".NetworkSettings.Ports", self.script)

    def test_captures_restart_policy(self):
        """Script preserves restart policy."""
        self.assertIn("RestartPolicy", self.script)

    def test_captures_network_mode(self):
        """Script preserves network mode."""
        self.assertIn("NetworkMode", self.script)

    def test_stops_old_container(self):
        """Script stops the old container before starting new one."""
        stop_idx = self.script.index("docker stop")
        run_idx = self.script.index("docker run -d")
        self.assertLess(stop_idx, run_idx)

    def test_starts_new_container_with_same_name(self):
        """New container uses the same name."""
        self.assertIn('--name "$CONTAINER_NAME"', self.script)

    def test_dispatcher_registration(self):
        """Script re-registers with dispatcher after restart."""
        self.assertIn("/worker/register", self.script)
        self.assertIn("DISPATCHER_URL", self.script)

    def test_registration_payload_fields(self):
        """Registration payload includes required fields."""
        self.assertIn("worker_id", self.script)
        self.assertIn("capabilities", self.script)
        self.assertIn("tdd-pipeline", self.script)

    def test_registration_is_non_fatal(self):
        """Registration failure doesn't crash the script."""
        # The WARNING message indicates non-fatal handling
        self.assertIn("Could not register with dispatcher", self.script)

    def test_registration_skipped_without_url(self):
        """Script skips registration if DISPATCHER_URL is not set."""
        self.assertIn("DISPATCHER_URL not set", self.script)

    def test_auto_detects_container(self):
        """Script auto-detects container by image ancestry."""
        self.assertIn("docker ps", self.script)
        self.assertIn("--filter", self.script)

    def test_steps_in_order(self):
        """Major steps happen in correct order: login, pull, capture, stop, start, register."""
        login_idx = self.script.index("ECR login")
        pull_idx = self.script.index("Pull latest")
        capture_idx = self.script.index("Capture")
        stop_idx = self.script.index("Stop and remove")
        start_idx = self.script.index("Start new container")
        register_idx = self.script.index("Re-register")
        self.assertLess(login_idx, pull_idx)
        self.assertLess(pull_idx, capture_idx)
        self.assertLess(capture_idx, stop_idx)
        self.assertLess(stop_idx, start_idx)
        self.assertLess(start_idx, register_idx)


if __name__ == "__main__":
    unittest.main()
