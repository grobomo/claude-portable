#!/usr/bin/env python3
"""Check that unchecked tasks in TODO.md follow the task template format.

Required fields per task: What, Why, How, Acceptance, PR title.
Optional: Context.

Exit 0 if all tasks pass, exit 1 if any task is missing required fields.
"""

import re
import sys

REQUIRED_FIELDS = {"what", "why", "how", "acceptance", "pr title"}


def parse_tasks(content: str) -> list[dict]:
    """Parse TODO.md into a list of unchecked tasks with their sub-fields."""
    lines = content.splitlines()
    tasks = []
    current_task = None

    for i, line in enumerate(lines):
        # Unchecked task line
        if re.match(r"^\s*-\s+\[\s+\]\s+", line):
            if current_task:
                tasks.append(current_task)
            desc = re.sub(r"^\s*-\s+\[\s+\]\s+", "", line).strip()
            current_task = {
                "line": i + 1,
                "description": desc,
                "fields": set(),
            }
        elif current_task:
            # Sub-field line (indented, starts with "- Field:")
            m = re.match(r"^\s+-\s+(\w[\w\s]*?):\s+", line)
            if m:
                field_name = m.group(1).strip().lower()
                current_task["fields"].add(field_name)
            # End of task block (next task, heading, or blank followed by non-indent)
            elif re.match(r"^\s*-\s+\[", line) or re.match(r"^#", line):
                tasks.append(current_task)
                current_task = None
                # Check if this is a new unchecked task
                if re.match(r"^\s*-\s+\[\s+\]\s+", line):
                    desc = re.sub(r"^\s*-\s+\[\s+\]\s+", "", line).strip()
                    current_task = {
                        "line": i + 1,
                        "description": desc,
                        "fields": set(),
                    }

    if current_task:
        tasks.append(current_task)

    return tasks


def check_tasks(tasks: list[dict]) -> list[str]:
    """Return list of error messages for tasks missing required fields."""
    errors = []
    for task in tasks:
        missing = REQUIRED_FIELDS - task["fields"]
        if missing:
            desc_short = task["description"][:60]
            missing_str = ", ".join(sorted(missing))
            errors.append(
                f"Line {task['line']}: \"{desc_short}\" missing: {missing_str}"
            )
    return errors


def main():
    todo_path = sys.argv[1] if len(sys.argv) > 1 else "TODO.md"
    try:
        with open(todo_path, "r") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"TODO.md not found at {todo_path}")
        return 0  # No TODO.md = nothing to check

    tasks = parse_tasks(content)
    if not tasks:
        print("No unchecked tasks found.")
        return 0

    errors = check_tasks(tasks)
    if errors:
        print(f"Task template check FAILED ({len(errors)} task(s) missing fields):\n")
        for err in errors:
            print(f"  {err}")
        print(f"\nSee .github/TASK_TEMPLATE.md for required format.")
        return 1

    print(f"All {len(tasks)} unchecked task(s) pass template check.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
