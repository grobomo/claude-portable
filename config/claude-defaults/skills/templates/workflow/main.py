#!/usr/bin/env python3
"""
{{SKILL_NAME}} - Workflow skill template

Usage:
    python main.py <command> [args]
"""

import argparse
import sys
from pathlib import Path


def cmd_list(args):
    """List all items."""
    print("Listing items...")
    # TODO: Implement listing logic


def cmd_create(args):
    """Create a new item."""
    print(f"Creating: {args.name}")
    # TODO: Implement creation logic


def cmd_delete(args):
    """Delete an item."""
    print(f"Deleting: {args.name}")
    # TODO: Implement deletion logic


def cmd_info(args):
    """Show item details."""
    print(f"Info for: {args.name}")
    # TODO: Implement info logic


def main():
    parser = argparse.ArgumentParser(description="{{SKILL_NAME}}")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # list
    subparsers.add_parser("list", help="List all items")

    # create
    p_create = subparsers.add_parser("create", help="Create new item")
    p_create.add_argument("name", nargs="?", help="Item name")

    # delete
    p_delete = subparsers.add_parser("delete", help="Delete item")
    p_delete.add_argument("name", help="Item name")

    # info
    p_info = subparsers.add_parser("info", help="Show item details")
    p_info.add_argument("name", help="Item name")

    args = parser.parse_args()

    commands = {
        "list": cmd_list,
        "create": cmd_create,
        "delete": cmd_delete,
        "info": cmd_info,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
