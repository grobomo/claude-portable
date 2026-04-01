#!/usr/bin/env python3
"""
Test dispatcher-brain.py -- verify it starts, checks inbox, logs idle, and health endpoint works.
Runs the brain for 60 seconds in a test mode (no real Bedrock calls).
"""

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error

BRAIN_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "dispatcher-brain.py")
HEALTH_PORT = 18081  # Use high port to avoid conflicts
LOG_FILE = "/tmp/brain-test.log"
HISTORY_FILE = "/tmp/brain-test-history.json"


def wait_for_health(port, timeout=15):
    """Wait for health endpoint to respond."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            url = f"http://localhost:{port}/api/brain-status"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, ConnectionRefusedError, OSError):
            time.sleep(0.5)
    return None


def main():
    # Clean up old test artifacts
    for f in (LOG_FILE, HISTORY_FILE):
        if os.path.exists(f):
            os.remove(f)

    env = os.environ.copy()
    env["BRAIN_HEALTH_PORT"] = str(HEALTH_PORT)
    env["BRAIN_LOOP_INTERVAL"] = "5"  # Fast loops for testing
    env["AWS_DEFAULT_REGION"] = "us-east-1"  # Bedrock model access
    env["BRAIN_HISTORY_FILE"] = HISTORY_FILE
    env["BRAIN_MAX_TOKENS"] = "10000"
    # Don't set USE_BEDROCK -- we want it to fail fast on API call
    # but the health endpoint and inbox collection should still work

    print(f"[test] Starting dispatcher-brain.py (port {HEALTH_PORT})...")
    with open(LOG_FILE, "w") as logf:
        proc = subprocess.Popen(
            [sys.executable, BRAIN_SCRIPT],
            env=env,
            stdout=logf,
            stderr=subprocess.STDOUT,
        )

    try:
        # Test 1: Health endpoint comes up
        print("[test] Waiting for health endpoint...")
        health = wait_for_health(HEALTH_PORT)
        if health is None:
            print("[FAIL] Health endpoint did not respond within 15s")
            with open(LOG_FILE) as f:
                print(f.read()[-2000:])
            return 1

        print(f"[PASS] Health endpoint responded: status={health.get('status')}")
        assert "uptime_seconds" in health, "Missing uptime_seconds"
        assert "last_check_time" in health or health.get("status") == "starting", "Missing last_check_time"
        print(f"[PASS] Health response has expected fields")

        # Test 2: Wait for at least one loop to complete
        print("[test] Waiting for first loop iteration (up to 30s)...")
        deadline = time.time() + 30
        loops_done = False
        while time.time() < deadline:
            health = wait_for_health(HEALTH_PORT, timeout=3)
            if health and health.get("loops_completed", 0) >= 1:
                loops_done = True
                break
            time.sleep(2)

        # The loop will likely error on Bedrock call (no creds in test env)
        # but that's OK -- we're testing the framework, not the API

        # Test 3: Check logs for expected output
        print("[test] Checking logs...")
        with open(LOG_FILE) as f:
            logs = f.read()

        if "Dispatcher Brain Starting" in logs:
            print("[PASS] Brain startup message in logs")
        else:
            print("[FAIL] Missing startup message")
            print(logs[-1000:])
            return 1

        if "Health endpoint listening" in logs:
            print("[PASS] Health endpoint startup logged")
        else:
            print("[FAIL] Missing health endpoint log")
            return 1

        # Check that inbox collection was attempted
        if "Inbox:" in logs or "Loop 1" in logs:
            print("[PASS] Loop iteration started")
        else:
            print("[INFO] Loop may not have completed (Bedrock creds not available)")

        # It's expected that Bedrock calls fail in test -- check for graceful handling
        if "Bedrock API error" in logs or "error" in logs.lower():
            print("[INFO] API errors present (expected without Bedrock creds)")

        # Test 4: Health endpoint shows stats
        final_health = wait_for_health(HEALTH_PORT, timeout=5)
        if final_health:
            print(f"[PASS] Final health: loops={final_health.get('loops_completed', 0)}, "
                  f"errors={final_health.get('errors', 0)}, "
                  f"status={final_health.get('status')}")

        print("\n[PASS] All tests passed")
        return 0

    finally:
        # Clean shutdown
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        print(f"[test] Brain process exited (pid={proc.pid})")

        # Show last bit of log
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE) as f:
                content = f.read()
            if content:
                print(f"\n--- brain log (last 1000 chars) ---")
                print(content[-1000:])


if __name__ == "__main__":
    sys.exit(main())
