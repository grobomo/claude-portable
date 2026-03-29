"""
install.py - Cross-platform OS scheduler installer for claude-scheduler.

Installs a recurring trigger that runs `python scheduler.py run-all` at the
configured interval using the native OS scheduler:
  - Windows: schtasks (Task Scheduler)
  - macOS: launchd (LaunchAgent plist)
  - Linux: systemd user timer

Usage:
    python install.py install     # Register with OS scheduler
    python install.py uninstall   # Remove from OS scheduler
    python install.py status      # Check if registered
"""
import sys
import os
import platform
import subprocess
import shutil

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEDULER_PY = os.path.join(SKILL_DIR, "scheduler.py")
TASK_NAME = "ClaudeScheduler"
INTERVAL_MINUTES = 60  # Check hourly; scheduler.py handles per-task intervals

# Find Python
PYTHON = sys.executable or shutil.which("python3") or shutil.which("python") or "python"


def _get_platform():
    s = platform.system().lower()
    if s == "windows":
        return "windows"
    elif s == "darwin":
        return "macos"
    elif s == "linux":
        return "linux"
    return s


# ---------------------------------------------------------------------------
# Windows: schtasks
# ---------------------------------------------------------------------------

def _win_install():
    cmd = f'"{PYTHON}" "{SCHEDULER_PY}" run-all'
    args = [
        "schtasks", "/Create",
        "/TN", TASK_NAME,
        "/TR", cmd,
        "/SC", "MINUTE",
        "/MO", str(INTERVAL_MINUTES),
        "/F",  # force overwrite if exists
    ]
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"[OK] Windows Task Scheduler: {TASK_NAME}")
        print(f"     Runs every {INTERVAL_MINUTES} minutes")
        print(f"     Command: {cmd}")
    else:
        print(f"[ERROR] schtasks failed: {result.stderr.strip()}")
        sys.exit(1)


def _win_uninstall():
    result = subprocess.run(
        ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"[OK] Removed: {TASK_NAME}")
    else:
        print(f"[WARN] {result.stderr.strip()}")


def _win_status():
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", TASK_NAME, "/FO", "LIST"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"[OK] Task registered: {TASK_NAME}")
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line.startswith(("Status:", "Next Run Time:", "Last Run Time:", "Task To Run:")):
                print(f"     {line}")
    else:
        print(f"[--] Not registered: {TASK_NAME}")


# ---------------------------------------------------------------------------
# macOS: launchd
# ---------------------------------------------------------------------------

def _mac_plist_path():
    return os.path.expanduser(f"~/Library/LaunchAgents/com.claude.scheduler.plist")


def _mac_install():
    plist_path = _mac_plist_path()
    interval_seconds = INTERVAL_MINUTES * 60
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claude.scheduler</string>
    <key>ProgramArguments</key>
    <array>
        <string>{PYTHON}</string>
        <string>{SCHEDULER_PY}</string>
        <string>run-all</string>
    </array>
    <key>StartInterval</key>
    <integer>{interval_seconds}</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{os.path.expanduser("~/.claude/super-manager/logs/scheduler-stdout.log")}</string>
    <key>StandardErrorPath</key>
    <string>{os.path.expanduser("~/.claude/super-manager/logs/scheduler-stderr.log")}</string>
</dict>
</plist>
"""
    os.makedirs(os.path.dirname(plist_path), exist_ok=True)
    with open(plist_path, "w") as f:
        f.write(plist_content)

    subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
    result = subprocess.run(["launchctl", "load", plist_path], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"[OK] LaunchAgent loaded: com.claude.scheduler")
        print(f"     Runs every {INTERVAL_MINUTES} minutes")
        print(f"     Plist: {plist_path}")
    else:
        print(f"[ERROR] launchctl load failed: {result.stderr.strip()}")
        sys.exit(1)


def _mac_uninstall():
    plist_path = _mac_plist_path()
    if os.path.isfile(plist_path):
        subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
        os.remove(plist_path)
        print(f"[OK] Removed LaunchAgent: com.claude.scheduler")
    else:
        print(f"[--] Not installed: {plist_path}")


def _mac_status():
    result = subprocess.run(
        ["launchctl", "list", "com.claude.scheduler"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"[OK] LaunchAgent active: com.claude.scheduler")
        for line in result.stdout.strip().split("\n"):
            print(f"     {line}")
    else:
        print(f"[--] Not loaded: com.claude.scheduler")


# ---------------------------------------------------------------------------
# Linux: systemd user timer
# ---------------------------------------------------------------------------

def _linux_unit_dir():
    return os.path.expanduser("~/.config/systemd/user")


def _linux_install():
    unit_dir = _linux_unit_dir()
    os.makedirs(unit_dir, exist_ok=True)

    service_path = os.path.join(unit_dir, "claude-scheduler.service")
    timer_path = os.path.join(unit_dir, "claude-scheduler.timer")
    log_dir = os.path.expanduser("~/.claude/super-manager/logs")

    service_content = f"""[Unit]
Description=Claude Code Scheduler
After=default.target

[Service]
Type=oneshot
ExecStart={PYTHON} {SCHEDULER_PY} run-all
StandardOutput=append:{log_dir}/scheduler-stdout.log
StandardError=append:{log_dir}/scheduler-stderr.log

[Install]
WantedBy=default.target
"""

    timer_content = f"""[Unit]
Description=Claude Code Scheduler Timer

[Timer]
OnBootSec=5min
OnUnitActiveSec={INTERVAL_MINUTES}min
Persistent=true

[Install]
WantedBy=timers.target
"""

    with open(service_path, "w") as f:
        f.write(service_content)
    with open(timer_path, "w") as f:
        f.write(timer_content)

    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    result = subprocess.run(
        ["systemctl", "--user", "enable", "--now", "claude-scheduler.timer"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"[OK] systemd user timer enabled: claude-scheduler.timer")
        print(f"     Runs every {INTERVAL_MINUTES} minutes")
        print(f"     Units: {unit_dir}")
    else:
        print(f"[ERROR] systemctl failed: {result.stderr.strip()}")
        sys.exit(1)


def _linux_uninstall():
    unit_dir = _linux_unit_dir()
    subprocess.run(
        ["systemctl", "--user", "disable", "--now", "claude-scheduler.timer"],
        capture_output=True,
    )
    for fname in ("claude-scheduler.service", "claude-scheduler.timer"):
        fpath = os.path.join(unit_dir, fname)
        if os.path.isfile(fpath):
            os.remove(fpath)
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    print(f"[OK] Removed systemd timer: claude-scheduler")


def _linux_status():
    result = subprocess.run(
        ["systemctl", "--user", "status", "claude-scheduler.timer"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(f"[OK] systemd timer active:")
        for line in result.stdout.strip().split("\n")[:6]:
            print(f"     {line}")
    else:
        print(f"[--] Timer not active: claude-scheduler.timer")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

PLATFORM_FUNCS = {
    "windows": {"install": _win_install, "uninstall": _win_uninstall, "status": _win_status},
    "macos": {"install": _mac_install, "uninstall": _mac_uninstall, "status": _mac_status},
    "linux": {"install": _linux_install, "uninstall": _linux_uninstall, "status": _linux_status},
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print("Claude Scheduler Installer")
        print()
        print("  python install.py install     Register with OS scheduler")
        print("  python install.py uninstall   Remove from OS scheduler")
        print("  python install.py status      Check registration status")
        sys.exit(0)

    action = sys.argv[1]
    plat = _get_platform()
    funcs = PLATFORM_FUNCS.get(plat)

    if not funcs:
        print(f"Unsupported platform: {plat}")
        sys.exit(1)

    func = funcs.get(action)
    if not func:
        print(f"Unknown action: {action}")
        print("Use: install, uninstall, status")
        sys.exit(1)

    print(f"Platform: {plat}")
    func()


if __name__ == "__main__":
    main()
