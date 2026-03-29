"""Table reporter for summary tables."""
from typing import Dict, List, Any

class TableReporter:
    """Generate summary tables."""
    
    def generate_summary(self, mcp_data: Dict, skill_data: Dict, hook_data: Dict) -> str:
        lines = []
        lines.append("\n## Summary")
        lines.append("")
        lines.append("| Category | Running | Stopped | Disabled | Unregistered | Total |")
        lines.append("|----------|---------|---------|----------|--------------|-------|")
        
        servers = mcp_data.get("servers", {})
        mcp_total = sum(len(v) for v in servers.values())
        lines.append(f"| MCP Servers | {len(servers.get('running', []))} | {len(servers.get('stopped', []))} | {len(servers.get('disabled', []))} | {len(servers.get('unregistered', []))} | {mcp_total} |")
        
        skills = skill_data.get("skills", {})
        skill_total = sum(len(v) for v in skills.values())
        lines.append(f"| Skills | - | {len(skills.get('user', [])) + len(skills.get('project', []))} | - | {len(skills.get('unregistered', []))} | {skill_total} |")
        
        hooks = hook_data.get("hooks", {})
        active_count = sum(len(v) for v in hooks.get("active", {}).values())
        archived_count = len(hooks.get("archived", []))
        orphaned_count = len(hooks.get("orphaned", []))
        lines.append(f"| Hooks | {active_count} | - | {archived_count} | {orphaned_count} | {active_count + archived_count + orphaned_count} |")
        
        return "\n".join(lines)
    
    def generate_hook_flow(self, hook_data: Dict) -> str:
        lines = []
        lines.append("\n## Hook Flow")
        lines.append("")
        lines.append("```")
        lines.append("Event Flow:")
        
        flow = hook_data.get("hook_flow", [])
        for i, item in enumerate(flow):
            event = item.get("event", "")
            hooks = item.get("hooks", [])
            arrow = "  |" if i < len(flow) - 1 else ""
            lines.append(f"  [{event}] ({len(hooks)} hooks)")
            for hook in hooks:
                matcher = hook.get("matcher", "*")
                cmd = hook.get("command", "").split("/")[-1].split("\\")[-1][:30]
                lines.append(f"    -> [{matcher}] {cmd}")
            if arrow:
                lines.append(arrow)
                lines.append("  v")
        lines.append("```")
        return "\n".join(lines)
    
    def generate_security_table(self, all_flags: List[Dict]) -> str:
        if not all_flags:
            return "\n## Security Flags\n\nNo security concerns found."
        
        lines = []
        lines.append("\n## Security Flags")
        lines.append("")
        lines.append("| Type | File | Message | Severity |")
        lines.append("|------|------|---------|----------|")
        
        for flag in all_flags[:50]:
            ftype = flag.get("type", "unknown")
            ffile = flag.get("file", "-")[:40]
            msg = flag.get("message", "-")[:50]
            sev = flag.get("severity", "info")
            lines.append(f"| {ftype} | {ffile} | {msg} | {sev} |")
        
        if len(all_flags) > 50:
            lines.append(f"\n*... and {len(all_flags) - 50} more flags*")
        return "\n".join(lines)
