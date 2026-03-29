#!/usr/bin/env python3
"""
User Story Analysis for API Skills

Analyzes available API operations against common user stories.
Generates SUGGESTED_CALLS.md with prioritized API recommendations.

Usage:
    python analyze_userstories.py                # Full analysis (research + compare)
    python analyze_userstories.py --skip-research  # Use cached stories only
    python analyze_userstories.py --quiet        # Minimal output (no research)

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

# Default user stories - UPDATE FOR YOUR API
DEFAULT_USERSTORIES = {
    "my_api": {
        "name": "My API",
        "sources": [
            # Add documentation URLs
        ],
        "official_mcp_tools": [
            # Add official MCP tool names if exists
        ],
        "user_stories": [
            {
                "story": "List items",
                "description": "Get a list of available items",
                "operations": ["list", "list_items"],
                "priority": "high",
                "example": "list limit=10",
            },
            {
                "story": "Get single item",
                "description": "Retrieve details of a specific item",
                "operations": ["get", "get_item"],
                "priority": "high",
                "example": "get id=12345",
            },
            {
                "story": "Create item",
                "description": "Create a new item",
                "operations": ["create", "create_item"],
                "priority": "high",
                "example": "create name=\"New Item\"",
            },
            {
                "story": "Update item",
                "description": "Modify an existing item",
                "operations": ["update", "update_item"],
                "priority": "medium",
                "example": "update id=12345 name=\"Updated\"",
            },
            {
                "story": "Delete item",
                "description": "Remove an item",
                "operations": ["delete", "delete_item"],
                "priority": "low",
                "example": "delete id=12345",
            },
            {
                "story": "Search",
                "description": "Search for items by query",
                "operations": ["search", "find"],
                "priority": "high",
                "example": "search query=\"keyword\"",
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
                    matched.extend(partial[:2])
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
        print("  'claude' CLI not found. Using default stories.")
        return None
    except subprocess.TimeoutExpired:
        print("  Claude research timed out.")
        return None
    except Exception as e:
        print(f"  Error: {e}")
        return None


def main():
    do_research = "--research" in sys.argv
    compare_mcp = "--compare-mcp" in sys.argv
    quiet = "--quiet" in sys.argv

    if not quiet:
        print("=" * 60)
        print("  User Story Analysis")
        print("=" * 60)

    # Load operations
    operations = load_operations()
    if not quiet:
        print(f"\nLoaded {len(operations)} operations from api_index/")

    # Load user stories
    all_stories = load_userstories()
    api_key = list(all_stories.keys())[0] if all_stories else "unknown"
    stories_data = all_stories.get(api_key, {})

    # Research if requested
    if do_research:
        new_stories = research_with_claude(stories_data.get("name", api_key))
        if new_stories:
            stories_data["user_stories"] = new_stories.get("user_stories", [])
            all_stories[api_key] = stories_data
            save_userstories(all_stories)
            print("  Updated user stories from research")

    # Match stories to operations
    stories = stories_data.get("user_stories", [])
    if not stories:
        if not quiet:
            print("\nNo user stories defined. Run with --research or update userstories.yaml")
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


if __name__ == "__main__":
    main()
