#!/usr/bin/env python3
"""
User Story Analysis for API Skills

Analyzes available API operations against common user stories.
Generates SUGGESTED_CALLS.md with prioritized API recommendations.

Usage:
    python analyze_userstories.py                # Full analysis (research + compare)
    python analyze_userstories.py --skip-research  # Use cached stories only
    python analyze_userstories.py --quiet        # Minimal output

By default, this script:
1. Uses Claude to research common user stories online
2. Compares against official MCP servers
3. Generates SUGGESTED_CALLS.md with prioritized recommendations
"""

import os
import sys
import json
import yaml
import subprocess
from pathlib import Path
from datetime import datetime

SKILL_DIR = Path(__file__).parent
API_INDEX_DIR = SKILL_DIR / "api_index"
OUTPUT_FILE = SKILL_DIR / "SUGGESTED_CALLS.md"
USERSTORIES_FILE = SKILL_DIR / "userstories.yaml"

# Default user stories for Confluence (curated from research)
DEFAULT_USERSTORIES = {
    "confluence": {
        "name": "Confluence Wiki",
        "sources": [
            "https://github.com/atlassian/atlassian-mcp-server",
            "https://github.com/sooperset/mcp-atlassian",
            "https://atlassian-python-api.readthedocs.io/confluence.html",
            "https://n8n.io/integrations/confluence/",
        ],
        "official_mcp_tools": [
            "confluence_search",
            "confluence_get_page",
            "confluence_create_page",
            "confluence_update_page",
            "confluence_add_comment",
        ],
        "user_stories": [
            {
                "story": "Search documentation",
                "description": "Find pages containing specific keywords or topics",
                "operations": ["search", "list_search"],
                "priority": "high",
                "example": "search query=\"API documentation\" limit=10",
            },
            {
                "story": "Read page content",
                "description": "Get full content of a wiki page for reference or processing",
                "operations": ["read", "get_page"],
                "priority": "high",
                "example": "read page_id=1234567 format=text",
            },
            {
                "story": "Create new documentation",
                "description": "Create new wiki pages from templates or generated content",
                "operations": ["create", "create_page"],
                "priority": "high",
                "example": "create space_key=MYSPACE title=\"New Feature\" content=\"<p>...</p>\"",
            },
            {
                "story": "Update existing pages",
                "description": "Modify page content, fix errors, add new sections",
                "operations": ["update", "update_page"],
                "priority": "high",
                "example": "update page_id=1234567 title=\"Updated Title\" content=\"<p>New content</p>\"",
            },
            {
                "story": "Sync docs from GitHub",
                "description": "Push README/markdown files to Confluence automatically",
                "operations": ["create", "update", "search"],
                "priority": "high",
                "example": "# Workflow: search for existing -> update or create",
            },
            {
                "story": "Navigate page hierarchy",
                "description": "Browse child pages, find parent pages, understand structure",
                "operations": ["children", "list_content_descendant", "get_content_descendant"],
                "priority": "medium",
                "example": "children page_id=1234567",
            },
            {
                "story": "Manage page labels",
                "description": "Add, remove, or list labels for organization and filtering",
                "operations": ["labels", "delete_content_label", "list_label"],
                "priority": "medium",
                "example": "labels page_id=1234567 add=\"api-docs\"",
            },
            {
                "story": "Add comments and feedback",
                "description": "Post comments on pages for collaboration",
                "operations": ["comments"],
                "priority": "medium",
                "example": "comments page_id=1234567 add=\"Reviewed and approved\"",
            },
            {
                "story": "Manage attachments",
                "description": "Upload, download, or list file attachments on pages",
                "operations": ["create_content_child_attachment", "list_content_child_attachment_download"],
                "priority": "medium",
                "example": "# Use create_content_child_attachment to upload files",
            },
            {
                "story": "Archive or delete pages",
                "description": "Clean up outdated content, archive old documentation",
                "operations": ["delete", "create_content_archive", "delete_content_page_tree"],
                "priority": "low",
                "example": "delete page_id=1234567",
            },
            {
                "story": "Manage spaces",
                "description": "Create, update, or configure Confluence spaces",
                "operations": ["create_space", "update_space", "delete_space", "list_space_settings"],
                "priority": "low",
                "example": "create_space key=NEWSPACE name=\"New Project Space\"",
            },
            {
                "story": "Set permissions",
                "description": "Control who can view or edit pages and spaces",
                "operations": ["create_space_permission", "list_content_restriction", "create_content_restriction"],
                "priority": "low",
                "example": "# Use restriction APIs to control access",
            },
            {
                "story": "Export content",
                "description": "Export pages as PDF or other formats",
                "operations": ["list_audit_export"],
                "priority": "low",
                "example": "# Export via audit or direct page export",
            },
            {
                "story": "Track page analytics",
                "description": "See page views and viewer statistics",
                "operations": ["list_analytics_content_views", "list_analytics_content_viewers"],
                "priority": "low",
                "example": "list_analytics_content_views contentId=1234567",
            },
            {
                "story": "Manage templates",
                "description": "Create, list, or use page templates",
                "operations": ["list_template_page", "create_template", "get_template"],
                "priority": "low",
                "example": "list_template_page",
            },
        ]
    }
}


def load_operations():
    """Load all operations from api_index."""
    operations = {}
    if not API_INDEX_DIR.exists():
        return operations

    for folder in API_INDEX_DIR.iterdir():
        if not folder.is_dir() or folder.name.startswith("_"):
            continue
        config_file = folder / "config.yaml"
        if config_file.exists():
            try:
                data = yaml.safe_load(config_file.read_text())
                if data and "name" in data:
                    operations[data["name"]] = data
            except Exception:
                pass
    return operations


def load_userstories():
    """Load user stories from file or use defaults."""
    if USERSTORIES_FILE.exists():
        try:
            return yaml.safe_load(USERSTORIES_FILE.read_text())
        except Exception:
            pass
    return DEFAULT_USERSTORIES


def save_userstories(stories):
    """Save user stories to file."""
    USERSTORIES_FILE.write_text(yaml.dump(stories, default_flow_style=False, sort_keys=False))


def match_operations(stories, operations):
    """Match user stories to available operations."""
    results = []
    op_names = set(operations.keys())

    for story in stories:
        matched = []
        missing = []

        for op in story.get("operations", []):
            if op in op_names:
                matched.append(op)
            else:
                # Try partial match
                partial = [o for o in op_names if op in o or o in op]
                if partial:
                    matched.extend(partial[:2])  # Limit to 2 partial matches
                else:
                    missing.append(op)

        results.append({
            "story": story["story"],
            "description": story.get("description", ""),
            "priority": story.get("priority", "medium"),
            "example": story.get("example", ""),
            "matched": list(set(matched)),
            "missing": missing,
            "coverage": len(matched) / max(len(story.get("operations", [])), 1),
        })

    return results


def generate_markdown(api_name, results, operations, sources):
    """Generate SUGGESTED_CALLS.md content."""
    lines = [
        f"# Suggested API Calls - {api_name}",
        "",
        f"*Auto-generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
        "## Quick Start",
        "",
        "The most common operations based on user research:",
        "",
    ]

    # High priority
    high = [r for r in results if r["priority"] == "high" and r["matched"]]
    if high:
        lines.append("### Essential Operations")
        lines.append("")
        for r in high:
            lines.append(f"**{r['story']}** - {r['description']}")
            lines.append("```bash")
            if r.get("example"):
                lines.append(f"python executor.py {r['example']}")
            else:
                lines.append(f"python executor.py {r['matched'][0]}")
            lines.append("```")
            lines.append(f"Operations: `{', '.join(r['matched'])}`")
            lines.append("")

    # Medium priority
    med = [r for r in results if r["priority"] == "medium" and r["matched"]]
    if med:
        lines.append("### Common Operations")
        lines.append("")
        for r in med:
            lines.append(f"**{r['story']}** - {r['description']}")
            lines.append(f"- Operations: `{', '.join(r['matched'])}`")
            if r.get("example"):
                lines.append(f"- Example: `{r['example']}`")
            lines.append("")

    # Low priority
    low = [r for r in results if r["priority"] == "low" and r["matched"]]
    if low:
        lines.append("### Advanced Operations")
        lines.append("")
        for r in low:
            lines.append(f"- **{r['story']}**: `{', '.join(r['matched'][:3])}`")
        lines.append("")

    # Coverage summary
    lines.append("## Coverage Analysis")
    lines.append("")
    total_ops = len(operations)
    matched_ops = set()
    for r in results:
        matched_ops.update(r["matched"])

    lines.append(f"- **Total operations available**: {total_ops}")
    lines.append(f"- **Operations mapped to user stories**: {len(matched_ops)}")
    lines.append(f"- **Coverage**: {len(matched_ops)/max(total_ops,1)*100:.1f}%")
    lines.append("")

    # Missing capabilities
    all_missing = set()
    for r in results:
        all_missing.update(r["missing"])
    if all_missing:
        lines.append("### Gaps (not yet implemented)")
        lines.append("")
        for m in sorted(all_missing):
            lines.append(f"- `{m}`")
        lines.append("")

    # Unmapped operations
    unmapped = set(operations.keys()) - matched_ops
    if unmapped:
        lines.append("### Available but Unmapped")
        lines.append("")
        lines.append("Operations available but not linked to common user stories:")
        lines.append("")
        # Group by prefix
        by_prefix = {}
        for op in sorted(unmapped):
            prefix = op.split("_")[0]
            if prefix not in by_prefix:
                by_prefix[prefix] = []
            by_prefix[prefix].append(op)

        for prefix in sorted(by_prefix.keys()):
            ops = by_prefix[prefix]
            if len(ops) <= 5:
                lines.append(f"- **{prefix}**: `{', '.join(ops)}`")
            else:
                lines.append(f"- **{prefix}** ({len(ops)} ops): `{', '.join(ops[:3])}`, ...")
        lines.append("")

    # Sources
    if sources:
        lines.append("## Research Sources")
        lines.append("")
        for src in sources:
            lines.append(f"- {src}")
        lines.append("")

    return "\n".join(lines)


def research_with_claude(api_name):
    """Use claude -p to research user stories for an API."""
    print(f"\nResearching user stories for {api_name} with Claude...")

    prompt = f"""Research common user stories and use cases for the {api_name} API.

Find:
1. What are the top 10 things people want to do with this API?
2. What operations does the official MCP server provide (if any)?
3. What automation workflows are most common?
4. What do people on Reddit/forums ask about?

Output as YAML with this structure:
```yaml
user_stories:
  - story: "Short name"
    description: "What the user wants to accomplish"
    operations: ["api_operation_1", "api_operation_2"]
    priority: high/medium/low
    example: "example command"
```

Focus on practical, real-world use cases. Include 10-15 user stories.
"""

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            # Extract YAML from response
            output = result.stdout
            if "```yaml" in output:
                yaml_content = output.split("```yaml")[1].split("```")[0]
                stories = yaml.safe_load(yaml_content)
                return stories
            else:
                print("  Could not parse Claude response as YAML")
                return None
        else:
            print(f"  Claude returned error: {result.stderr}")
            return None
    except FileNotFoundError:
        print("  'claude' CLI not found. Install Claude Code or use default stories.")
        return None
    except subprocess.TimeoutExpired:
        print("  Claude research timed out.")
        return None
    except Exception as e:
        print(f"  Error: {e}")
        return None


def compare_to_official_mcp(stories_data, operations):
    """Compare our operations to official MCP tools."""
    print("\nComparing to official MCP servers...")

    official_tools = stories_data.get("official_mcp_tools", [])
    if not official_tools:
        print("  No official MCP tools defined for comparison")
        return

    print(f"  Official MCP provides {len(official_tools)} tools:")
    for tool in official_tools:
        # Check if we have equivalent
        matches = [op for op in operations.keys() if tool.replace("confluence_", "") in op]
        if matches:
            print(f"    [OK] {tool} -> {', '.join(matches[:2])}")
        else:
            print(f"    [--] {tool} (not directly mapped)")


def main():
    # Default: do research and compare. Use --skip-research to skip.
    skip_research = "--skip-research" in sys.argv
    quiet = "--quiet" in sys.argv

    if not quiet:
        print("=" * 60)
        print("  User Story Analysis")
        print("=" * 60)

    # Load operations
    operations = load_operations()
    if not quiet:
        print(f"\nLoaded {len(operations)} operations from api_index/")

    # Load or research user stories
    all_stories = load_userstories()

    # Detect API type from skill name
    skill_name = SKILL_DIR.name
    api_key = None
    for key in all_stories.keys():
        if key in skill_name or skill_name in key:
            api_key = key
            break

    if not api_key:
        api_key = list(all_stories.keys())[0] if all_stories else "unknown"

    stories_data = all_stories.get(api_key, {})

    # Research online by default (unless --skip-research or --quiet)
    if not skip_research and not quiet:
        new_stories = research_with_claude(stories_data.get("name", api_key))
        if new_stories:
            stories_data["user_stories"] = new_stories.get("user_stories", [])
            all_stories[api_key] = stories_data
            save_userstories(all_stories)
            print("  Updated user stories from research")

    # Compare to official MCP by default
    if not quiet:
        compare_to_official_mcp(stories_data, operations)

    # Match stories to operations
    stories = stories_data.get("user_stories", [])
    if not stories:
        if not quiet:
            print("\nNo user stories defined. Using defaults.")
        # Fall back to defaults
        stories = DEFAULT_USERSTORIES.get(api_key, {}).get("user_stories", [])
        if not stories:
            print("No user stories available.")
            return

    results = match_operations(stories, operations)

    # Generate markdown
    sources = stories_data.get("sources", [])
    markdown = generate_markdown(
        stories_data.get("name", api_key),
        results,
        operations,
        sources
    )

    OUTPUT_FILE.write_text(markdown)
    if not quiet:
        print(f"\nGenerated: {OUTPUT_FILE.name}")

    # Summary
    if not quiet:
        high_coverage = [r for r in results if r["priority"] == "high" and r["coverage"] > 0]
        print(f"\nUser story coverage:")
        print(f"  High priority: {len(high_coverage)}/{len([r for r in results if r['priority'] == 'high'])}")
        print(f"  Total matched: {sum(1 for r in results if r['matched'])}/{len(results)}")


if __name__ == "__main__":
    main()
