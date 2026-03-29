"""Markdown file reporter."""
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
from .tree_reporter import TreeReporter
from .table_reporter import TableReporter

class MarkdownReporter:
    """Generate full markdown report file."""
    
    def __init__(self):
        self.tree = TreeReporter()
        self.table = TableReporter()
    
    def generate(self, mcp_data: Dict, skill_data: Dict, hook_data: Dict, output_path: Path = None) -> str:
        lines = []
        lines.append("# Claude Code Report")
        lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append(self.table.generate_summary(mcp_data, skill_data, hook_data))
        lines.append(self.tree.generate(mcp_data, skill_data, hook_data))
        lines.append(self.table.generate_hook_flow(hook_data))
        
        all_flags = (mcp_data.get("security_flags", []) + skill_data.get("security_flags", []) + hook_data.get("security_flags", []))
        lines.append(self.table.generate_security_table(all_flags))
        lines.append(self._generate_mcp_details(mcp_data))
        lines.append(self._generate_skill_details(skill_data))
        
        content = "\n".join(lines)
        if output_path:
            output_path.write_text(content)
        return content
    
    def _generate_mcp_details(self, data: Dict) -> str:
        lines = []
        lines.append("\n## MCP Server Details")
        lines.append("")
        lines.append("| Name | Status | Source | Command | Description |")
        lines.append("|------|--------|--------|---------|-------------|")
        
        for status, servers in data.get("servers", {}).items():
            for server in servers:
                name = server.get("name", "-")
                source = server.get("source", "-")
                cmd = server.get("command", "-")[:20]
                desc = server.get("description", "-")[:30]
                lines.append(f"| {name} | {status} | {source} | {cmd} | {desc} |")
        return "\n".join(lines)
    
    def _generate_skill_details(self, data: Dict) -> str:
        lines = []
        lines.append("\n## Skill Details")
        lines.append("")
        lines.append("| Name | Title | Source | Registered | Has Main |")
        lines.append("|------|-------|--------|------------|----------|")
        
        for source, skills in data.get("skills", {}).items():
            for skill in skills:
                name = skill.get("name", "-")
                title = skill.get("title", "-")[:25]
                reg = "Yes" if skill.get("registered") else "No"
                has_main = "Yes" if skill.get("has_main") else "No"
                lines.append(f"| {name} | {title} | {source} | {reg} | {has_main} |")
        return "\n".join(lines)
