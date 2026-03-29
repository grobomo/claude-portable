#!/usr/bin/env python3
"""
config-bundle.py -- Scrape, sanitize, bundle, deploy, and patch Claude Code config.

Subcommands:
  scrape      Scan local ~/.claude and collect all config files + dependencies
  build       Sanitize secrets/paths and create versioned zip bundle
  deploy      Push bundle to one or all CCC workers
  status      Show which config version each worker has
  patch       Update specific files on running workers without full redeploy
  simulate    Deploy bundle to a test instance for validation

Usage:
  python config-bundle.py scrape                      # scan local config
  python config-bundle.py build                       # build bundle zip
  python config-bundle.py deploy --all                # deploy to all workers
  python config-bundle.py deploy --name worker-1      # deploy to one worker
  python config-bundle.py status                      # version report
  python config-bundle.py patch settings.json --all   # patch one file
  python config-bundle.py simulate --name test-1      # deploy + validate on test instance

Environment:
  CONFIG_BUNDLE_DIR     Where bundles are stored (default: config/bundles/)
  CLAUDE_HOME           Local Claude config dir (default: ~/.claude)
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
BUNDLE_DIR = os.environ.get("CONFIG_BUNDLE_DIR",
                             os.path.join(PROJECT_DIR, "config", "bundles"))
DEFAULTS_DIR = os.path.join(PROJECT_DIR, "config", "claude-defaults")
CLAUDE_HOME = os.environ.get("CLAUDE_HOME",
                              os.path.expanduser("~/.claude"))

# Files/dirs to always include
INCLUDE_FILES = [
    "settings.json",
    "CLAUDE.md",
    "remote-settings.json",
]
INCLUDE_DIRS = [
    "rules",
    "hooks",
    "skills",
]
# Files to never include (secrets, cache, ephemeral)
EXCLUDE_PATTERNS = [
    ".credentials.json",
    "history.jsonl",
    "*.log",
    "cache/",
    "file-history/",
    "plans/",
    "downloads/",
    "paste-cache/",
    "projects/",
    "backups/",
    "plugins/",
    "policy-limits.json",
    "*.enc",
    "*.pem",
    "*.html",
    ".git/",
    "__pycache__/",
    "node_modules/",
    "archive/",
]

# Patterns to sanitize in file contents
SECRET_PATTERNS = [
    # OAuth/API tokens
    (r'"access_token"\s*:\s*"[^"]{20,}"', '"access_token": "${OAUTH_ACCESS_TOKEN}"'),
    (r'"refresh_token"\s*:\s*"[^"]{20,}"', '"refresh_token": "${OAUTH_REFRESH_TOKEN}"'),
    (r'"expires_at"\s*:\s*"?\d{10,}"?', '"expires_at": "${OAUTH_EXPIRES_AT}"'),
    (r'(api[_-]?key|token|secret)\s*[=:]\s*["\']?[A-Za-z0-9_\-]{20,}["\']?',
     r'\1=${REDACTED_SECRET}'),
    # Windows personal paths -> container paths
    (r'C:[/\\]+Users[/\\]+\w+[/\\]+Documents[/\\]+ProjectsCL1',
     '/workspace'),
    (r'C:[/\\]+Users[/\\]+\w+[/\\]+\.claude',
     '/home/claude/.claude'),
    (r'C:[/\\]+Users[/\\]+\w+',
     '/home/claude'),
    # PII patterns
    (r'joel\.?ginsberg|joelg\b', '${USER_NAME}'),
    (r'joel-ginsberg_tmemu', '${TMEMU_ACCOUNT}'),
]

# Path rewrites for container environment
PATH_REWRITES = [
    (r'C:/Users/\w+/Documents/ProjectsCL1/MCP/', '/opt/mcp/'),
    (r'C:/Users/\w+/Documents/ProjectsCL1/', '/workspace/'),
    (r'C:/Users/\w+/.claude/', '/home/claude/.claude/'),
    (r'C:/Users/\w+/', '/home/claude/'),
    (r'C:\\\\Users\\\\[^\\\\]+\\\\Documents\\\\ProjectsCL1\\\\MCP\\\\', '/opt/mcp/'),
    (r'C:\\\\Users\\\\[^\\\\]+\\\\Documents\\\\ProjectsCL[^\\\\]*\\\\', '/workspace/'),
    (r'C:\\\\Users\\\\[^\\\\]+\\\\', '/home/claude/'),
    # Quadruple-escaped (inside strings inside strings)
    (r'C:\\\\\\\\Users\\\\\\\\[^\\\\]+\\\\\\\\', '/home/claude/'),
    # Dash-separated project paths (e.g. C--Users-joelg-...)
    (r'C--Users-\w+(?:-[^/\s"\']+)*', '${PROJECT_PATH}'),
]


def log(msg):
    print(f"  {msg}")


def sanitize_content(content: str, filename: str = "") -> str:
    """Replace secrets, tokens, paths, and PII with variables."""
    result = content
    # Path rewrites first (more specific)
    for pattern, replacement in PATH_REWRITES:
        result = re.sub(pattern, replacement, result)
    # Then secret patterns
    for pattern, replacement in SECRET_PATTERNS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def should_exclude(path: str) -> bool:
    """Check if a path matches any exclusion pattern."""
    for pat in EXCLUDE_PATTERNS:
        if pat.endswith("/"):
            if pat.rstrip("/") in path.split(os.sep):
                return True
        elif "*" in pat:
            import fnmatch
            if fnmatch.fnmatch(os.path.basename(path), pat):
                return True
        else:
            if os.path.basename(path) == pat:
                return True
    return False


def compute_version(bundle_path: str) -> str:
    """Compute SHA256 hash of bundle zip as version string."""
    h = hashlib.sha256()
    with open(bundle_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


# ── Scrape ────────────────────────────────────────────────────────────────────

def cmd_scrape(args):
    """Scan local Claude config and report what would be bundled."""
    print("=" * 60)
    print("  Config Scrape Report")
    print("=" * 60)
    print(f"\n  Source: {CLAUDE_HOME}\n")

    total_files = 0
    total_size = 0
    excluded = 0

    # Individual files
    print("  Files:")
    for fname in INCLUDE_FILES:
        fpath = os.path.join(CLAUDE_HOME, fname)
        if os.path.isfile(fpath):
            size = os.path.getsize(fpath)
            total_files += 1
            total_size += size
            log(f"  + {fname} ({size:,} bytes)")
        else:
            log(f"  - {fname} (not found)")

    # Directories
    print("\n  Directories:")
    for dname in INCLUDE_DIRS:
        dpath = os.path.join(CLAUDE_HOME, dname)
        if not os.path.isdir(dpath):
            log(f"  - {dname}/ (not found)")
            continue
        dir_files = 0
        dir_size = 0
        dir_excluded = 0
        for root, dirs, files in os.walk(dpath):
            for f in files:
                fpath = os.path.join(root, f)
                relpath = os.path.relpath(fpath, CLAUDE_HOME)
                if should_exclude(relpath):
                    dir_excluded += 1
                    continue
                dir_files += 1
                dir_size += os.path.getsize(fpath)
        total_files += dir_files
        total_size += dir_size
        excluded += dir_excluded
        log(f"  + {dname}/ ({dir_files} files, {dir_size:,} bytes, {dir_excluded} excluded)")

    # MCP servers referenced in .mcp.json
    print("\n  MCP Servers:")
    mcp_path = os.path.join(CLAUDE_HOME, ".mcp.json")
    if os.path.isfile(mcp_path):
        with open(mcp_path) as f:
            mcp = json.load(f)
        for name, cfg in mcp.get("mcpServers", {}).items():
            mcp_args = cfg.get("args", [])
            for a in mcp_args:
                if os.path.isfile(a) or os.path.isdir(os.path.dirname(a)):
                    log(f"  + {name}: {a}")

    # Referenced binaries in hooks
    print("\n  Hook Dependencies:")
    hooks_dir = os.path.join(CLAUDE_HOME, "hooks")
    if os.path.isdir(hooks_dir):
        for f in os.listdir(hooks_dir):
            if f.endswith(".js"):
                fpath = os.path.join(hooks_dir, f)
                with open(fpath, "r", errors="replace") as fh:
                    content = fh.read()
                # Find require() calls
                requires = re.findall(r"require\(['\"]([^'\"]+)['\"]\)", content)
                for req in requires:
                    if not req.startswith(".") and not req.startswith("/"):
                        log(f"  {f} requires: {req}")

    print(f"\n  Summary: {total_files} files, {total_size:,} bytes, {excluded} excluded")
    print()


# ── Build ─────────────────────────────────────────────────────────────────────

def cmd_build(args):
    """Sanitize and bundle config into a versioned zip."""
    print("=" * 60)
    print("  Building Config Bundle")
    print("=" * 60)

    os.makedirs(BUNDLE_DIR, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")

    # Create temp staging dir
    with tempfile.TemporaryDirectory() as staging:
        staged_count = 0

        # Copy and sanitize individual files
        for fname in INCLUDE_FILES:
            src = os.path.join(CLAUDE_HOME, fname)
            if not os.path.isfile(src):
                continue
            dst = os.path.join(staging, fname)
            with open(src, "r", errors="replace") as f:
                content = f.read()
            sanitized = sanitize_content(content, fname)
            with open(dst, "w") as f:
                f.write(sanitized)
            staged_count += 1
            changed = content != sanitized
            log(f"+ {fname}" + (" (sanitized)" if changed else ""))

        # Copy and sanitize directories
        for dname in INCLUDE_DIRS:
            src_dir = os.path.join(CLAUDE_HOME, dname)
            if not os.path.isdir(src_dir):
                continue
            for root, dirs, files in os.walk(src_dir):
                for f in files:
                    src = os.path.join(root, f)
                    relpath = os.path.relpath(src, CLAUDE_HOME)
                    if should_exclude(relpath):
                        continue
                    dst = os.path.join(staging, relpath)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)

                    # Sanitize text files
                    if f.endswith((".json", ".js", ".md", ".yaml", ".yml", ".txt", ".sh", ".py", ".ts", ".cfg", ".ini", ".toml")):
                        try:
                            with open(src, "r", errors="replace") as fh:
                                content = fh.read()
                            sanitized = sanitize_content(content, f)
                            with open(dst, "w") as fh:
                                fh.write(sanitized)
                        except Exception:
                            shutil.copy2(src, dst)
                    else:
                        shutil.copy2(src, dst)
                    staged_count += 1

        # Write manifest (version computed after zip, then zip rebuilt)
        manifest = {
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": "local",
            "files": staged_count,
            "builder": "config-bundle.py",
            "version": "",  # filled after hash
        }
        manifest_path = os.path.join(staging, "MANIFEST.json")

        # First pass: create zip without final version
        zip_name = f"config-bundle-{timestamp}.zip"
        zip_path = os.path.join(BUNDLE_DIR, zip_name)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(staging):
                for fi in files:
                    fpath = os.path.join(root, fi)
                    arcname = os.path.relpath(fpath, staging)
                    zf.write(fpath, arcname)

        # Compute version from zip hash, then rebuild with version in manifest
        version = compute_version(zip_path)
        manifest["version"] = version
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        os.remove(zip_path)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(staging):
                for fi in files:
                    fpath = os.path.join(root, fi)
                    arcname = os.path.relpath(fpath, staging)
                    zf.write(fpath, arcname)

        # Also save as "latest"
        latest_path = os.path.join(BUNDLE_DIR, "config-bundle-latest.zip")
        shutil.copy2(zip_path, latest_path)

        # Save defaults snapshot to repo
        _save_defaults_snapshot(staging)

        zip_size = os.path.getsize(zip_path)
        print(f"\n  Bundle: {zip_path}")
        print(f"  Version: {version}")
        print(f"  Files: {staged_count}")
        print(f"  Size: {zip_size:,} bytes")
        print()


def _save_defaults_snapshot(staging_dir: str):
    """Copy the sanitized config to config/claude-defaults/ for git tracking."""
    if os.path.isdir(DEFAULTS_DIR):
        # On Windows, .git objects may be read-only — force delete
        def _rm_readonly(func, path, exc_info):
            import stat
            os.chmod(path, stat.S_IWRITE)
            func(path)
        shutil.rmtree(DEFAULTS_DIR, onexc=_rm_readonly)
    shutil.copytree(staging_dir, DEFAULTS_DIR)
    log(f"Saved defaults snapshot to {DEFAULTS_DIR}")


# ── Deploy ────────────────────────────────────────────────────────────────────

def _get_workers():
    """Get worker instances from ccc list."""
    try:
        ccc = os.path.join(PROJECT_DIR, "ccc")
        r = subprocess.run([sys.executable, ccc, "list", "--json"],
                           capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            instances = json.loads(r.stdout)
            return [i for i in instances
                    if i.get("state") == "running"
                    and i.get("role", "worker") not in ("dispatcher",)]
    except Exception:
        pass
    return []


def _find_ssh_key(worker_name: str) -> str:
    """Find SSH key for a worker."""
    key_dir = os.path.expanduser("~/.ssh/ccc-keys")
    for name in [worker_name, worker_name.replace("ccc-", ""),
                 f"ccc-{worker_name}"]:
        path = os.path.join(key_dir, f"{name}.pem")
        if os.path.isfile(path):
            return path
    return ""


def _deploy_to_worker(worker_ip: str, worker_name: str, bundle_path: str,
                       ssh_key: str) -> bool:
    """SCP bundle to worker and unzip into ~/.claude/."""
    remote_tmp = f"/tmp/config-bundle-{int(time.time())}.zip"
    ssh_opts = ["-o", "StrictHostKeyChecking=no", "-o", "LogLevel=ERROR",
                "-o", "ConnectTimeout=10", "-i", ssh_key]

    # SCP the bundle
    r = subprocess.run(
        ["scp"] + ssh_opts + [bundle_path, f"ubuntu@{worker_ip}:{remote_tmp}"],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode != 0:
        log(f"  SCP failed to {worker_name}: {r.stderr.strip()}")
        return False

    # Unzip on worker (into container's ~/.claude)
    deploy_cmd = (
        f"docker exec claude-portable bash -c '"
        f"cd /home/claude/.claude && "
        f"unzip -o /tmp/$(basename {remote_tmp}) -d /home/claude/.claude/ && "
        f"echo DEPLOYED'"
    )
    # First copy into container
    copy_cmd = f"docker cp {remote_tmp} claude-portable:/tmp/"
    r = subprocess.run(
        ["ssh"] + ssh_opts + [f"ubuntu@{worker_ip}",
         f"{copy_cmd} && {deploy_cmd} && rm {remote_tmp}"],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode == 0 and "DEPLOYED" in r.stdout:
        log(f"  Deployed to {worker_name} ({worker_ip})")
        return True
    else:
        log(f"  Deploy failed on {worker_name}: {r.stderr.strip()}")
        return False


def cmd_deploy(args):
    """Deploy config bundle to workers."""
    bundle_path = os.path.join(BUNDLE_DIR, "config-bundle-latest.zip")
    if not os.path.isfile(bundle_path):
        print("ERROR: No bundle found. Run 'build' first.")
        sys.exit(1)

    version = compute_version(bundle_path)
    print(f"  Deploying bundle version {version}")
    print()

    if args.name:
        workers = [{"name": args.name, "ip": args.ip or "",
                     "label": args.name}]
        if not args.ip:
            # Try to find from ccc list
            all_workers = _get_workers()
            for w in all_workers:
                if w.get("name", "").endswith(args.name) or \
                   w.get("label", "") == args.name:
                    workers = [w]
                    break
    else:
        workers = _get_workers()

    if not workers:
        print("  No workers found.")
        return

    success = 0
    for w in workers:
        name = w.get("label") or w.get("name", "?")
        ip = w.get("ip", "")
        if not ip:
            log(f"  {name}: no IP, skipping")
            continue
        ssh_key = _find_ssh_key(name)
        if not ssh_key:
            log(f"  {name}: no SSH key, skipping")
            continue
        if _deploy_to_worker(ip, name, bundle_path, ssh_key):
            success += 1

    print(f"\n  Deployed to {success}/{len(workers)} workers")


# ── Status ────────────────────────────────────────────────────────────────────

def cmd_status(args):
    """Show config bundle version on each worker."""
    print("=" * 60)
    print("  Config Bundle Status")
    print("=" * 60)

    latest_path = os.path.join(BUNDLE_DIR, "config-bundle-latest.zip")
    if os.path.isfile(latest_path):
        local_version = compute_version(latest_path)
        print(f"\n  Local bundle: {local_version}")
    else:
        local_version = "(none)"
        print(f"\n  Local bundle: (not built)")

    workers = _get_workers()
    if not workers:
        print("  No running workers found.\n")
        return

    print()
    ssh_opts = ["-o", "StrictHostKeyChecking=no", "-o", "LogLevel=ERROR",
                "-o", "ConnectTimeout=5"]

    for w in workers:
        name = w.get("label") or w.get("name", "?")
        ip = w.get("ip", "")
        if not ip:
            print(f"  {name:20}  (no IP)")
            continue
        ssh_key = _find_ssh_key(name)
        if not ssh_key:
            print(f"  {name:20}  (no SSH key)")
            continue

        # Read MANIFEST.json from worker
        try:
            r = subprocess.run(
                ["ssh"] + ssh_opts + ["-i", ssh_key, f"ubuntu@{ip}",
                 "docker exec claude-portable cat /home/claude/.claude/MANIFEST.json 2>/dev/null || echo '{}'"],
                capture_output=True, text=True, timeout=10,
            )
            manifest = json.loads(r.stdout.strip() or "{}")
            remote_version = manifest.get("version", "(unknown)")
            built_at = manifest.get("built_at", "?")

            if remote_version == local_version:
                status = "\033[92mCURRENT\033[0m"
            elif remote_version == "(unknown)":
                status = "\033[93mNO BUNDLE\033[0m"
            else:
                status = f"\033[91mSTALE\033[0m ({remote_version})"

            print(f"  {name:20}  {status:>30}  built {built_at}")
        except Exception as e:
            print(f"  {name:20}  (error: {e})")

    print()


# ── Patch ─────────────────────────────────────────────────────────────────────

def cmd_patch(args):
    """Patch specific files on running workers without full redeploy."""
    files_to_patch = args.files
    print(f"  Patching {len(files_to_patch)} file(s)")

    workers = _get_workers() if args.all else []
    if args.name:
        all_w = _get_workers()
        workers = [w for w in all_w
                   if w.get("name", "").endswith(args.name)
                   or w.get("label", "") == args.name]

    if not workers:
        print("  No workers found.")
        return

    ssh_opts = ["-o", "StrictHostKeyChecking=no", "-o", "LogLevel=ERROR",
                "-o", "ConnectTimeout=10"]

    for w in workers:
        name = w.get("label") or w.get("name", "?")
        ip = w.get("ip", "")
        ssh_key = _find_ssh_key(name)
        if not ip or not ssh_key:
            log(f"{name}: skipping (no IP or key)")
            continue

        for fname in files_to_patch:
            # Look for the file in the defaults dir first, then local claude home
            src = os.path.join(DEFAULTS_DIR, fname)
            if not os.path.isfile(src):
                src = os.path.join(CLAUDE_HOME, fname)
            if not os.path.isfile(src):
                log(f"{name}: {fname} not found locally, skipping")
                continue

            # Sanitize
            with open(src, "r", errors="replace") as f:
                content = f.read()
            sanitized = sanitize_content(content, fname)

            # Write to temp file and SCP
            with tempfile.NamedTemporaryFile(mode="w", suffix=f"_{os.path.basename(fname)}",
                                              delete=False) as tmp:
                tmp.write(sanitized)
                tmp_path = tmp.name

            remote_path = f"/home/claude/.claude/{fname}"
            try:
                # SCP to host, then docker cp into container
                remote_tmp = f"/tmp/_patch_{os.path.basename(fname)}"
                r = subprocess.run(
                    ["scp"] + ["-i", ssh_key] + ssh_opts +
                    [tmp_path, f"ubuntu@{ip}:{remote_tmp}"],
                    capture_output=True, text=True, timeout=30,
                )
                if r.returncode != 0:
                    log(f"{name}: SCP failed for {fname}")
                    continue

                r = subprocess.run(
                    ["ssh"] + ["-i", ssh_key] + ssh_opts +
                    [f"ubuntu@{ip}",
                     f"docker cp {remote_tmp} claude-portable:{remote_path} && rm {remote_tmp} && echo OK"],
                    capture_output=True, text=True, timeout=15,
                )
                if "OK" in r.stdout:
                    log(f"{name}: patched {fname}")
                else:
                    log(f"{name}: patch failed for {fname}")
            finally:
                os.unlink(tmp_path)

    print()


# ── Simulate ──────────────────────────────────────────────────────────────────

def cmd_simulate(args):
    """Deploy bundle to a test instance and validate the config."""
    bundle_path = os.path.join(BUNDLE_DIR, "config-bundle-latest.zip")
    if not os.path.isfile(bundle_path):
        print("ERROR: No bundle found. Run 'build' first.")
        sys.exit(1)

    name = args.name or "config-test"
    print(f"  Simulating config bundle on instance: {name}")
    print()

    # Find or launch the test instance
    workers = _get_workers()
    target = None
    for w in workers:
        if w.get("name", "").endswith(name) or w.get("label", "") == name:
            target = w
            break

    if not target:
        print(f"  Instance '{name}' not found. Launch it with: ccc --name {name} --new")
        print(f"  Then re-run: python config-bundle.py simulate --name {name}")
        return

    ip = target.get("ip", "")
    ssh_key = _find_ssh_key(name)
    if not ip or not ssh_key:
        print(f"  Cannot reach {name} (ip={ip}, key={'found' if ssh_key else 'missing'})")
        return

    # Deploy the bundle
    print("  [1/3] Deploying bundle...")
    if not _deploy_to_worker(ip, name, bundle_path, ssh_key):
        print("  Deploy failed. Aborting simulation.")
        return

    # Validate the config
    print("  [2/3] Validating config...")
    ssh_opts = ["-o", "StrictHostKeyChecking=no", "-o", "LogLevel=ERROR",
                "-o", "ConnectTimeout=10", "-i", ssh_key]
    checks = [
        ("settings.json exists",
         "docker exec claude-portable test -f /home/claude/.claude/settings.json && echo OK"),
        ("CLAUDE.md exists",
         "docker exec claude-portable test -f /home/claude/.claude/CLAUDE.md && echo OK"),
        ("rules/ populated",
         "docker exec claude-portable ls /home/claude/.claude/rules/*.md 2>/dev/null | wc -l"),
        ("hooks/ populated",
         "docker exec claude-portable ls /home/claude/.claude/hooks/*.js 2>/dev/null | wc -l"),
        ("skills/ populated",
         "docker exec claude-portable ls -d /home/claude/.claude/skills/*/ 2>/dev/null | wc -l"),
        ("No Windows paths leaked",
         "docker exec claude-portable grep -rl 'C:/Users/' /home/claude/.claude/settings.json /home/claude/.claude/CLAUDE.md 2>/dev/null | wc -l"),
        ("No secrets leaked",
         "docker exec claude-portable grep -rl 'access_token.*ey' /home/claude/.claude/ 2>/dev/null | wc -l"),
        ("MANIFEST.json present",
         "docker exec claude-portable test -f /home/claude/.claude/MANIFEST.json && echo OK"),
    ]

    passed = 0
    failed = 0
    for label, cmd in checks:
        r = subprocess.run(
            ["ssh"] + ssh_opts + [f"ubuntu@{ip}", cmd],
            capture_output=True, text=True, timeout=15,
        )
        output = r.stdout.strip()
        if label.startswith("No "):
            # These should be 0
            ok = output == "0"
        else:
            ok = output and output != "0"
        status = "\033[92mPASS\033[0m" if ok else "\033[91mFAIL\033[0m"
        if not ok:
            failed += 1
        else:
            passed += 1
        print(f"    {status}  {label} ({output})")

    # Show a sample of the settings.json on the worker
    print("\n  [3/3] Config preview (settings.json):")
    r = subprocess.run(
        ["ssh"] + ssh_opts + [f"ubuntu@{ip}",
         "docker exec claude-portable cat /home/claude/.claude/settings.json 2>/dev/null | head -20"],
        capture_output=True, text=True, timeout=10,
    )
    for line in r.stdout.splitlines()[:15]:
        print(f"    {line}")

    print(f"\n  Simulation: {passed} passed, {failed} failed")
    if failed == 0:
        print("  Config bundle is ready for fleet deployment.")
    else:
        print("  Fix issues and rebuild before deploying to fleet.")
    print()


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Claude Code config bundle manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("scrape", help="Scan local config and report what would be bundled")
    sub.add_parser("build", help="Sanitize and create versioned bundle zip")

    p_deploy = sub.add_parser("deploy", help="Push bundle to workers")
    p_deploy.add_argument("--name", help="Deploy to specific worker")
    p_deploy.add_argument("--ip", help="Worker IP (if name lookup fails)")
    p_deploy.add_argument("--all", action="store_true", help="Deploy to all running workers")

    sub.add_parser("status", help="Show config version on each worker")

    p_patch = sub.add_parser("patch", help="Patch specific files on workers")
    p_patch.add_argument("files", nargs="+", help="File paths relative to ~/.claude/")
    p_patch.add_argument("--name", help="Patch specific worker")
    p_patch.add_argument("--all", action="store_true", help="Patch all running workers")

    p_sim = sub.add_parser("simulate", help="Deploy + validate on test instance")
    p_sim.add_argument("--name", help="Test instance name (default: config-test)")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    {
        "scrape": cmd_scrape,
        "build": cmd_build,
        "deploy": cmd_deploy,
        "status": cmd_status,
        "patch": cmd_patch,
        "simulate": cmd_simulate,
    }[args.command](args)


if __name__ == "__main__":
    main()
