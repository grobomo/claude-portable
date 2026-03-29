"""Tree view reporter for console output."""
from typing import Dict, List, Any

class TreeReporter:
    """Generate tree view output for console."""
    
    def __init__(self):
        self.output = []
    
    def generate(self, mcp_data: Dict, skill_data: Dict, hook_data: Dict) -> str:
        self.output = []
        self._add_mcp_tree(mcp_data)
        self._add_skill_tree(skill_data)
        self._add_hook_tree(hook_data)
        return "\n".join(self.output)
    
    def _add_mcp_tree(self, data: Dict):
        servers = data.get("servers", {})
        mcp_mgr = data.get("mcp_manager")
        total = sum(len(v) for v in servers.values())
        
        self.output.append(f"\n## MCP Servers ({total} total)")
        self.output.append("```")
        self.output.append("mcp-servers")
        
        # Separate routed vs standalone servers
        routed = []
        standalone = {"running": [], "stopped": [], "disabled": [], "unregistered": []}
        
        for cat, items in servers.items():
            for server in items:
                if server.get("routed"):
                    routed.append((server, cat))
                else:
                    standalone[cat].append(server)
        
        # Show mcp-manager section with routed servers nested under it
        if mcp_mgr:
            self.output.append("|   # MCP-MANAGER (router)")
            args = mcp_mgr.get("args", [])
            script = args[-1].split("/")[-1] if args else "unknown"
            self.output.append(f"|    |-- script: {script}")
            
            if routed:
                # Group routed servers by status
                by_status = {}
                for server, status in routed:
                    if status not in by_status:
                        by_status[status] = []
                    by_status[status].append(server)
                
                for status in ["running", "stopped", "disabled"]:
                    if status not in by_status:
                        continue
                    items = by_status[status]
                    for j, server in enumerate(items):
                        is_last = (j == len(items) - 1) and (status == list(by_status.keys())[-1])
                        prefix = "    +-- " if is_last else "    |-- "
                        name = server.get("name", "unknown")
                        desc = server.get("description", "")[:35]
                        status_tag = f"({status})"
                        if desc:
                            self.output.append(f"|{prefix}{name} {status_tag} - {desc}")
                        else:
                            self.output.append(f"|{prefix}{name} {status_tag}")
            else:
                self.output.append("|    +-- (no routed servers)")
        
        # Show standalone servers
        has_standalone = any(standalone[cat] for cat in standalone)
        if has_standalone:
            categories = [("running", "# STANDALONE RUNNING"), ("stopped", "# STANDALONE STOPPED"),
                          ("disabled", "# STANDALONE DISABLED"), ("unregistered", "# STANDALONE UNREGISTERED")]
            
            for i, (cat, label) in enumerate(categories):
                items = standalone.get(cat, [])
                if not items:
                    continue
                self.output.append(f"|   {label}")
                for j, server in enumerate(items):
                    is_last = j == len(items) - 1
                    item_prefix = "    +-- " if is_last else "    |-- "
                    desc = server.get("description", "")[:40]
                    name = server.get("name", "unknown")
                    if desc:
                        self.output.append(f"|{item_prefix}{name} - {desc}")
                    else:
                        self.output.append(f"|{item_prefix}{name}")
        
        self.output.append("```")
    
    def _add_skill_tree(self, data: Dict):
        skills = data.get("skills", {})
        total = sum(len(v) for v in skills.values())
        self.output.append(f"\n## Skills ({total} total)")
        self.output.append("```")
        self.output.append("skills")
        
        categories = [("user", "# USER-LEVEL"), ("project", "# PROJECT-LEVEL"),
                      ("marketplace", "# MARKETPLACE"), ("unregistered", "# UNREGISTERED")]
        
        for i, (cat, label) in enumerate(categories):
            items = skills.get(cat, [])
            if not items:
                continue
            self.output.append(f"|   {label}")
            for j, skill in enumerate(items):
                is_last = j == len(items) - 1
                item_prefix = "    +-- " if is_last else "    |-- "
                name = skill.get("name", "unknown")
                reg = "[R]" if skill.get("registered") else "[U]"
                self.output.append(f"|{item_prefix}{name} {reg}")
        self.output.append("```")
    
    def _add_hook_tree(self, data: Dict):
        hooks = data.get("hooks", {})
        active = hooks.get("active", {})
        archived = hooks.get("archived", [])
        orphaned = hooks.get("orphaned", [])
        total = sum(len(v) for v in active.values()) + len(archived) + len(orphaned)
        
        self.output.append(f"\n## Hooks ({total} total)")
        self.output.append("```")
        self.output.append("hooks")
        
        for event, hook_list in active.items():
            self.output.append(f"|   # {event}")
            for j, hook in enumerate(hook_list):
                is_last = j == len(hook_list) - 1
                item_prefix = "    +-- " if is_last else "    |-- "
                matcher = hook.get("matcher", "*")
                cmd = hook.get("command", "")[:50]
                self.output.append(f"|{item_prefix}[{matcher}] {cmd}...")
        
        if archived:
            self.output.append("|   # ARCHIVED")
            for j, hook in enumerate(archived):
                is_last = j == len(archived) - 1
                item_prefix = "    +-- " if is_last else "    |-- "
                self.output.append(f"|{item_prefix}{hook.get('name', 'unknown')}")
        
        if orphaned:
            self.output.append("|   # ORPHANED (not in config)")
            for j, hook in enumerate(orphaned):
                is_last = j == len(orphaned) - 1
                item_prefix = "    +-- " if is_last else "    |-- "
                self.output.append(f"|{item_prefix}{hook.get('name', 'unknown')}")
        self.output.append("```")
