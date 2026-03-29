"""Skill scanner - finds all Claude Code skills."""
import json
import os
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

class SkillScanner:
    """Scan for Claude Code skills."""
    
    def __init__(self, verbose=False):
        self.home = get_home()
        self.claude_dir = get_claude_dir()
        self.skills = {"user": [], "project": [], "marketplace": [], "unregistered": []}
        self.referenced_files = []
        self.security_flags = []
        self.verbose = verbose
        self.dirs_scanned = 0
    
    def scan(self, quick: bool = False) -> Dict[str, Any]:
        registry = self._load_registry()
        registered_paths = {normalize_path(s.get("skillPath", "")) for s in registry if s.get("skillPath")}
        self._scan_user_skills(registered_paths)
        self._scan_project_skills(registered_paths)
        self._scan_marketplace_skills(registered_paths)
        if not quick:
            self._scan_home_for_skills(registered_paths)
        self._check_orphaned_registry(registry)
        self._scan_referenced_files()
        return {"skills": self.skills, "referenced_files": self.referenced_files, "security_flags": self.security_flags}
    
    def _load_registry(self) -> List[Dict]:
        registry_path = self.claude_dir / "hooks" / "skill-registry.json"
        if not registry_path.exists():
            return []
        try:
            return json.loads(registry_path.read_text()).get("skills", [])
        except Exception as e:
            self.security_flags.append({"type": "parse_error", "file": str(registry_path), "message": str(e)})
            return []
    
    def _scan_user_skills(self, registered_paths: set):
        skills_dir = self.claude_dir / "skills"
        if not skills_dir.exists():
            return
        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                skill = self._parse_skill(skill_dir, skill_md, "user")
                skill["registered"] = any(p and skill_md.resolve() == p.resolve() for p in registered_paths if p)
                self.skills["user"].append(skill)
                self.referenced_files.append(skill_md)
    
    def _scan_project_skills(self, registered_paths: set):
        skills_dir = Path.cwd() / ".claude" / "skills"
        if not skills_dir.exists():
            return
        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                skill = self._parse_skill(skill_dir, skill_md, "project")
                skill["registered"] = any(p and skill_md.resolve() == p.resolve() for p in registered_paths if p)
                self.skills["project"].append(skill)
                self.referenced_files.append(skill_md)
    
    def _scan_marketplace_skills(self, registered_paths: set):
        # Read installed_plugins.json for marketplace -> plugin mapping
        installed_path = self.claude_dir / "plugins" / "installed_plugins.json"
        installed = {}
        if installed_path.exists():
            try:
                data = json.loads(installed_path.read_text())
                for key, entries in data.get("plugins", {}).items():
                    # key format: "plugin-name@marketplace-name"
                    if "@" in key:
                        plugin_name, marketplace_name = key.rsplit("@", 1)
                        for entry in (entries if isinstance(entries, list) else [entries]):
                            install_path = entry.get("installPath", "")
                            if install_path:
                                installed[Path(install_path)] = {
                                    "plugin": plugin_name,
                                    "marketplace": marketplace_name,
                                    "version": entry.get("version", ""),
                                    "scope": entry.get("scope", "user"),
                                }
            except Exception as e:
                self.security_flags.append({"type": "parse_error", "file": str(installed_path), "message": str(e)})

        # Scan cache directory for all marketplace plugin skills
        cache_dir = self.claude_dir / "plugins" / "cache"
        if not cache_dir.exists():
            return
        for marketplace_dir in cache_dir.iterdir():
            if not marketplace_dir.is_dir():
                continue
            marketplace_name = marketplace_dir.name
            for plugin_dir in marketplace_dir.iterdir():
                if not plugin_dir.is_dir():
                    continue
                # Each plugin may have multiple versions; find the latest (or installed) one
                version_dirs = sorted([d for d in plugin_dir.iterdir() if d.is_dir()], reverse=True)
                for vdir in version_dirs:
                    skills_dir = vdir / "skills"
                    if not skills_dir.exists():
                        continue
                    for skill_dir in skills_dir.iterdir():
                        if not skill_dir.is_dir():
                            continue
                        skill_md = skill_dir / "SKILL.md"
                        if skill_md.exists():
                            skill = self._parse_skill(skill_dir, skill_md, "marketplace")
                            skill["marketplace"] = marketplace_name
                            skill["plugin"] = plugin_dir.name
                            skill["version"] = vdir.name
                            # Check if this version is the installed one
                            meta = installed.get(vdir)
                            if meta:
                                skill["installed"] = True
                                skill["scope"] = meta.get("scope", "user")
                            skill["registered"] = any(p and skill_md.resolve() == p.resolve() for p in registered_paths if p)
                            self.skills["marketplace"].append(skill)
                            self.referenced_files.append(skill_md)
                    break  # Only scan first (latest) version dir with skills
    
    def _scan_home_for_skills(self, registered_paths: set):
        known_paths = set(str(p) for p in self.referenced_files)
        for root, dirs, files in os.walk(self.home):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]
            
            self.dirs_scanned += 1
            if self.verbose and self.dirs_scanned % 500 == 0:
                print(f"  Scanned {self.dirs_scanned} directories...", file=sys.stderr)
            
            root_path = Path(root)
            if "SKILL.md" in files:
                skill_md = root_path / "SKILL.md"
                if str(skill_md) not in known_paths:
                    skill = self._parse_skill(root_path, skill_md, "unregistered")
                    skill["registered"] = any(p and skill_md.resolve() == p.resolve() for p in registered_paths if p)
                    self.skills["unregistered"].append(skill)
                    self.referenced_files.append(skill_md)
                    known_paths.add(str(skill_md))
    
    def _parse_skill(self, skill_dir: Path, skill_md: Path, source: str) -> Dict[str, Any]:
        content = ""
        try:
            content = skill_md.read_text(errors="ignore")
        except:
            pass
        title = skill_dir.name
        for line in content.split("\n"):
            if line.startswith("# "):
                title = line[2:].strip()
                break
        return {
            "name": skill_dir.name, "title": title, "source": source,
            "path": get_relative_display(skill_md), "dir": get_relative_display(skill_dir),
            "has_main": (skill_dir / "main.py").exists(),
            "has_executor": (skill_dir / "executor.py").exists(), "keywords": []
        }
    
    def _check_orphaned_registry(self, registry: List[Dict]):
        for entry in registry:
            skill_path = normalize_path(entry.get("skillPath", ""))
            if skill_path and not skill_path.exists():
                self.security_flags.append({
                    "type": "orphaned_registry", "file": entry.get("skillPath", ""),
                    "message": f"Skill '{entry.get('name')}' registered but file missing", "severity": "warning"
                })
    
    def _scan_referenced_files(self):
        expected_roots = [self.claude_dir, Path.cwd() / ".claude"]
        for filepath in self.referenced_files:
            if not isinstance(filepath, Path):
                filepath = Path(filepath)
            loc_flag = check_path_location(filepath, expected_roots)
            if loc_flag:
                loc_flag["file"] = get_relative_display(filepath)
                self.security_flags.append(loc_flag)
            content_flags = check_file_security(filepath)
            for flag in content_flags:
                flag["file"] = get_relative_display(filepath)
                self.security_flags.append(flag)
