#!/usr/bin/env python3
"""Claude Report - Comprehensive inventory of MCPs, skills, hooks, and rules."""
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add skill directory to path
sys.path.insert(0, str(Path(__file__).parent))

from scanners import MCPScanner, SkillScanner, HookScanner, RuleScanner
from reporters import TreeReporter, TableReporter, MarkdownReporter, HtmlReporter

def main():
    parser = argparse.ArgumentParser(description="Generate Claude Code inventory report")
    parser.add_argument("--output", "-o", type=str, help="Output file path (default: auto-generated)")
    parser.add_argument("--quick", "-q", action="store_true", help="Quick scan (skip full home scan)")
    parser.add_argument("--json", "-j", action="store_true", help="Output JSON instead of tree view")
    parser.add_argument("--md", action="store_true", help="Output markdown instead of HTML")
    parser.add_argument("--console-only", "-c", action="store_true", help="Only print to console, no file")
    parser.add_argument("--no-open", action="store_true", help="Don't open report in browser")
    args = parser.parse_args()

    print("=" * 60)
    print("  Claude Code Inventory Report")
    print("=" * 60)
    print()

    # Run scanners
    print("Scanning MCP servers...")
    mcp_scanner = MCPScanner()
    mcp_data = mcp_scanner.scan(quick=args.quick)

    print("Scanning skills...")
    skill_scanner = SkillScanner()
    skill_data = skill_scanner.scan(quick=args.quick)

    print("Scanning hooks...")
    hook_scanner = HookScanner()
    hook_data = hook_scanner.scan(quick=args.quick)

    print("Scanning rules...")
    rule_scanner = RuleScanner()
    rule_data = rule_scanner.scan(quick=args.quick)

    print()

    if args.json:
        import json
        result = {
            "mcp": mcp_data,
            "skills": skill_data,
            "hooks": hook_data,
            "rules": rule_data
        }
        print(json.dumps(result, indent=2, default=str))
        return

    # Console summary (always print)
    tree_reporter = TreeReporter()
    table_reporter = TableReporter()
    print(table_reporter.generate_summary(mcp_data, skill_data, hook_data))

    # Write to file
    if not args.console_only:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if args.md:
            # Legacy markdown output
            if args.output:
                output_path = Path(args.output)
            else:
                output_path = Path(f"claude_report_{timestamp}.md")
            md_reporter = MarkdownReporter()
            md_reporter.generate(mcp_data, skill_data, hook_data, output_path)
        else:
            # Default: interactive HTML output
            if args.output:
                output_path = Path(args.output)
            else:
                output_path = Path(f"claude_report_{timestamp}.html")

            # Start rule editor server for live editing
            editor_port = 0
            try:
                from rule_editor_server import start_server
                _server, editor_port = start_server()
                print(f"Rule editor server on http://127.0.0.1:{editor_port}")
            except Exception as e:
                print(f"Warning: Rule editor server failed to start: {e}")

            html_reporter = HtmlReporter()
            html_reporter.generate(mcp_data, skill_data, hook_data, output_path,
                                   rule_data=rule_data, editor_port=editor_port)

        print(f"\nReport written to: {output_path}")

        # Open in browser (HTML only, unless --no-open)
        if not args.no_open and not args.md:
            abs_path = str(output_path.resolve())
            if sys.platform == 'win32':
                subprocess.Popen(['start', '', abs_path], shell=True)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', abs_path])
            else:
                subprocess.Popen(['xdg-open', abs_path])

            # Keep process alive while editor server runs
            if editor_port:
                import time
                print("Editor server running. Press Ctrl+C to stop.")
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    print("\nShutting down editor server.")

if __name__ == "__main__":
    main()
