"""MCP Server scanner - finds all MCP servers in home folder."""
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Any
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.path_utils import get_home, get_claude_dir, normalize_path, get_relative_display
from utils.security_checks import check_file_security, check_path_location

# Directories to skip during full scan
SKIP_DIRS = {
    'node_modules', '.git', '__pycache__', '.venv', 'venv', 'env',
    '.npm', '.cache', '.local', 'Cache', 'Caches', 'CachedData',
    'Temp', 'tmp', 'temp', 'logs', 'Logs', 'log',
    'AppData', 'Application Data', 'Local Settings',
    'site-packages', 'dist-packages', '.pyenv', '.nvm',
    'Microsoft', 'Google', 'Mozilla', 'Adobe',
    '.vscode-server', '.cursor-server',
}

class MCPScanner:
    """Scan for MCP servers across the system."""
    
    def __init__(self, verbose=False):
        self.home = get_home()
        self.claude_dir = get_claude_dir()
        self.servers = {"running": [], "stopped": [], "disabled": [], "unregistered": []}
        self.mcp_manager_info = None
        self.routed_server_names = set()
        self.referenced_files = []
        self.security_flags = []
        self.verbose = verbose
        self.dirs_scanned = 0
    
    def scan(self, quick: bool = False) -> Dict[str, Any]:
        self._scan_settings_json()
        self._scan_mcp_json()
        self._scan_mcp_manager_registry()
        if not quick:
            self._scan_home_for_servers()
        self._scan_referenced_files()
        # Mark servers that are routed through mcp-manager
        for cat in self.servers.values():
            for server in cat:
                server["routed"] = server.get("name", "") in self.routed_server_names
        return {"servers": self.servers, "mcp_manager": self.mcp_manager_info, "referenced_files": self.referenced_files, "security_flags": self.security_flags}
    
    def _scan_settings_json(self):
        settings_path = self.claude_dir / "settings.json"
        if not settings_path.exists():
            return
        try:
            data = json.loads(settings_path.read_text())
            for name, config in data.get("mcpServers", {}).items():
                server = {"name": name, "source": "user-settings", "config": config,
                          "command": config.get("command", ""), "args": config.get("args", []),
                          "path": get_relative_display(settings_path), "status": "stopped"}
                if config.get("command"):
                    cmd_path = self._resolve_command_path(config["command"], config.get("args", []))
                    if cmd_path:
                        self.referenced_files.append(cmd_path)
                        server["script_path"] = get_relative_display(cmd_path)
                self.servers["stopped"].append(server)
        except Exception as e:
            self.security_flags.append({"type": "parse_error", "file": str(settings_path), "message": str(e)})
    
    def _scan_mcp_json(self):
        mcp_json = Path.cwd() / ".mcp.json"
        if not mcp_json.exists():
            return
        try:
            data = json.loads(mcp_json.read_text())
            for name, config in data.get("mcpServers", {}).items():
                if name == "mcp-manager":
                    # Capture mcp-manager info and routed servers
                    self.mcp_manager_info = {
                        "name": "mcp-manager",
                        "source": "project-mcp-json",
                        "command": config.get("command", ""),
                        "args": config.get("args", []),
                        "routed_servers": config.get("servers", []),
                        "path": get_relative_display(mcp_json),
                        "status": "router"
                    }
                    self.routed_server_names = set(config.get("servers", []))
                    continue
                server = {"name": name, "source": "project-mcp-json", "config": config,
                          "path": get_relative_display(mcp_json), "status": "stopped"}
                self.servers["stopped"].append(server)
        except Exception as e:
            self.security_flags.append({"type": "parse_error", "file": str(mcp_json), "message": str(e)})
    
    def _scan_mcp_manager_registry(self):
        yaml_paths = [
            self.home / "mcp" / "mcp-manager" / "servers.yaml",
            Path.cwd().parent / "MCP" / "mcp-manager" / "servers.yaml",
        ]
        for yaml_path in yaml_paths:
            if yaml_path.exists():
                self._parse_servers_yaml(yaml_path)
                break
    
    def _parse_servers_yaml(self, yaml_path: Path):
        try:
            import yaml
            data = yaml.safe_load(yaml_path.read_text())
            for name, config in data.get("servers", {}).items():
                existing = any(s["name"] == name for cat in self.servers.values() for s in cat)
                if existing:
                    continue
                enabled = config.get("enabled", True)
                server = {"name": name, "source": "mcp-manager", "description": config.get("description", ""),
                          "command": config.get("command", ""), "args": config.get("args", []),
                          "path": get_relative_display(yaml_path), "status": "disabled" if not enabled else "stopped"}
                self.servers["disabled" if not enabled else "stopped"].append(server)
        except ImportError:
            pass
        except Exception as e:
            self.security_flags.append({"type": "parse_error", "file": str(yaml_path), "message": str(e)})
    
    def _scan_home_for_servers(self):
        known_names = {s["name"] for cat in self.servers.values() for s in cat}
        # Also build set of name variants for dedup (mcp-wiki-lite <-> wiki-lite)
        known_variants = set(known_names)
        for n in list(known_names):
            if n.startswith("mcp-"):
                known_variants.add(n[4:])  # mcp-wiki-lite -> wiki-lite
            else:
                known_variants.add("mcp-" + n)  # wiki-lite -> mcp-wiki-lite

        for root, dirs, files in os.walk(self.home):
            # Skip unwanted directories
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith('.')]

            self.dirs_scanned += 1
            if self.verbose and self.dirs_scanned % 500 == 0:
                print(f"  Scanned {self.dirs_scanned} directories...", file=sys.stderr)

            root_path = Path(root)
            if "server.py" in files:
                server_py = root_path / "server.py"
                content = ""
                try:
                    content = server_py.read_text(errors="ignore")[:2000]
                except:
                    pass
                if "mcp" in content.lower() or "fastmcp" in content.lower():
                    name = root_path.name
                    if name not in known_variants and name != "__pycache__":
                        desc = self._extract_description(content)
                        self.servers["unregistered"].append({
                            "name": name, "source": "discovered", "path": get_relative_display(server_py),
                            "status": "unregistered", "description": desc
                        })
                        known_names.add(name)
                        known_variants.add(name)
                        if name.startswith("mcp-"):
                            known_variants.add(name[4:])
                        else:
                            known_variants.add("mcp-" + name)
                        self.referenced_files.append(server_py)
    
    def _resolve_command_path(self, command: str, args: List[str]) -> Path:
        if command in ("python", "python3", "node") and args:
            script = normalize_path(args[0])
            if script and script.exists():
                return script
        cmd_path = normalize_path(command)
        if cmd_path and cmd_path.exists():
            return cmd_path
        return None
    
    def _extract_description(self, content: str) -> str:
        """Extract description from Python MCP server source.

        Tries in order: triple-quote docstring (multiline-aware),
        single-line # comment header, NAME variable assignment.
        Falls back to empty string -- never returns raw import lines.
        """
        import re
        # 1. Triple-quote docstring (multiline)
        match = re.search(r'"""([\s\S]*?)"""', content)
        if match:
            text = match.group(1).strip()
            # Take first meaningful line (skip blank lines)
            for line in text.split('\n'):
                line = line.strip()
                if line and not line.startswith('import') and not line.startswith('from'):
                    return line[:120]
        # 2. Single-quote docstring
        match = re.search(r"'''([\s\S]*?)'''", content)
        if match:
            text = match.group(1).strip()
            for line in text.split('\n'):
                line = line.strip()
                if line:
                    return line[:120]
        # 3. Comment block at top of file (after imports)
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('#') and len(line) > 5 and not line.startswith('#!'):
                return line.lstrip('# ').strip()[:120]
        # 4. NAME or DESCRIPTION variable
        match = re.search(r'(?:NAME|DESCRIPTION|SERVER_NAME)\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1).strip()[:120]
        return ""
    
    def _scan_referenced_files(self):
        expected_roots = [self.claude_dir, self.home / "mcp", Path.cwd() / ".claude", Path.cwd().parent / "MCP"]
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
