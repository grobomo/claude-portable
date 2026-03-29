"""Hook scanner - finds all Claude Code hooks."""
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Any
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.path_utils import get_home, get_claude_dir, normalize_path, get_relative_display
from utils.security_checks import check_file_security, check_path_location

SKIP_DIRS = {
    'node_modules', '.git', '__pycache__', '.venv', 'venv', 'env',
    '.npm', '.cache', '.local', 'Cache', 'Caches', 'CachedData',
    'Temp', 'tmp', 'temp', 'logs', 'Logs', 'log',
    'AppData', 'Application Data', 'Local Settings',
    'site-packages', 'dist-packages', '.pyenv', '.nvm',
    'Microsoft', 'Google', 'Mozilla', 'Adobe',
    '.vscode-server', '.cursor-server',
}

class HookScanner:
    def __init__(self, verbose=False):
        self.home = get_home()
        self.claude_dir = get_claude_dir()
        self.hooks = {"active": {}, "archived": [], "orphaned": []}
        self.referenced_files = []
        self.security_flags = []
        self.hook_flow = []
        self.verbose = verbose
        self.dirs_scanned = 0
    
    def scan(self, quick=False):
        configured_scripts = set()
        self._scan_user_settings(configured_scripts)
        self._scan_project_settings(configured_scripts)
        self._scan_hook_files(configured_scripts)
        if not quick:
            self._scan_home_for_hooks(configured_scripts)
        self._scan_referenced_files()
        self._build_hook_flow()
        return {"hooks": self.hooks, "hook_flow": self.hook_flow, "referenced_files": self.referenced_files, "security_flags": self.security_flags}
    
    def _scan_user_settings(self, configured_scripts):
        settings_path = self.claude_dir / "settings.json"
        if not settings_path.exists():
            return
        try:
            data = json.loads(settings_path.read_text())
            for event, matchers in data.get("hooks", {}).items():
                if event not in self.hooks["active"]:
                    self.hooks["active"][event] = []
                for mc in matchers:
                    matcher = mc.get("matcher", "*")
                    for hook in mc.get("hooks", []):
                        cmd = hook.get("command", "")
                        script_path = self._extract_script_path(cmd)
                        info = {"event": event, "matcher": matcher, "command": cmd, "source": "user-settings", "async": hook.get("async", False)}
                        if script_path:
                            info["script_path"] = get_relative_display(script_path)
                            configured_scripts.add(str(script_path))
                            self.referenced_files.append(script_path)
                        self.hooks["active"][event].append(info)
        except Exception as e:
            self.security_flags.append({"type": "parse_error", "file": str(settings_path), "message": str(e)})
    
    def _scan_project_settings(self, configured_scripts):
        settings_path = Path.cwd() / ".claude" / "settings.json"
        if not settings_path.exists():
            return
        try:
            data = json.loads(settings_path.read_text())
            for event, matchers in data.get("hooks", {}).items():
                if event not in self.hooks["active"]:
                    self.hooks["active"][event] = []
                for mc in matchers:
                    matcher = mc.get("matcher", "*")
                    for hook in mc.get("hooks", []):
                        cmd = hook.get("command", "")
                        script_path = self._extract_script_path(cmd)
                        info = {"event": event, "matcher": matcher, "command": cmd, "source": "project-settings", "async": hook.get("async", False)}
                        if script_path:
                            info["script_path"] = get_relative_display(script_path)
                            configured_scripts.add(str(script_path))
                            self.referenced_files.append(script_path)
                        self.hooks["active"][event].append(info)
        except Exception as e:
            self.security_flags.append({"type": "parse_error", "file": str(settings_path), "message": str(e)})
    
    def _scan_hook_files(self, configured_scripts):
        hooks_dir = self.claude_dir / "hooks"
        if not hooks_dir.exists():
            return
        for js_file in hooks_dir.glob("*.js"):
            if str(js_file) not in configured_scripts:
                self.hooks["orphaned"].append({"name": js_file.stem, "path": get_relative_display(js_file), "source": "orphaned"})
                self.referenced_files.append(js_file)
        archive_dir = hooks_dir / "Archive"
        if archive_dir.exists():
            for js_file in archive_dir.rglob("*.js"):
                self.hooks["archived"].append({"name": js_file.stem, "path": get_relative_display(js_file), "source": "archived"})
    
    def _scan_home_for_hooks(self, configured_scripts):
        known_paths = set(str(p) for p in self.referenced_files)
        hook_patterns = ["hook", "claude"]
        for root, dirs, files in os.walk(self.home):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
            self.dirs_scanned += 1
            if self.verbose and self.dirs_scanned % 500 == 0:
                print(f"  Scanned {self.dirs_scanned} directories...", file=sys.stderr)
            for f in files:
                if f.endswith(".js"):
                    fpath = Path(root) / f
                    if str(fpath) not in known_paths:
                        try:
                            content = fpath.read_text(errors="ignore")[:1000].lower()
                            if any(p in content for p in hook_patterns):
                                self.hooks["orphaned"].append({"name": f, "path": get_relative_display(fpath), "source": "discovered"})
                                self.referenced_files.append(fpath)
                                known_paths.add(str(fpath))
                        except:
                            pass
    
    def _extract_script_path(self, command):
        match = re.search(r'["\x27]([^"\x27]*\.js)["\x27]', command)
        if match:
            return normalize_path(match.group(1))
        if ".js" in command:
            for part in command.split():
                if part.endswith(".js"):
                    return normalize_path(part.strip('"\x27'))
        return None
    
    def _scan_referenced_files(self):
        expected_roots = [self.claude_dir, Path.cwd() / ".claude"]
        for fp in self.referenced_files:
            if not isinstance(fp, Path):
                fp = Path(fp)
            loc_flag = check_path_location(fp, expected_roots)
            if loc_flag:
                loc_flag["file"] = get_relative_display(fp)
                self.security_flags.append(loc_flag)
            for flag in check_file_security(fp):
                flag["file"] = get_relative_display(fp)
                self.security_flags.append(flag)
    
    def _build_hook_flow(self):
        for event in ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "SessionEnd"]:
            hooks = self.hooks["active"].get(event, [])
            if hooks:
                self.hook_flow.append({"event": event, "hooks": hooks})
