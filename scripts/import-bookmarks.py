#!/usr/bin/env python3
"""
Import bookmarks from bookmarks.json into Chrome profile.
Run inside the container: python3 /opt/claude-portable/scripts/import-bookmarks.py

Reads bookmarks.json from:
  1. /opt/claude-portable/bookmarks.json (baked into image)
  2. S3 state bucket (shared across instances)
"""
import json
import os
import subprocess
import time

CHROME_PROFILE = "/data/chrome-profile"
BOOKMARKS_FILE = os.path.join(CHROME_PROFILE, "Default", "Bookmarks")
SOURCE_FILES = [
    "/opt/claude-portable/bookmarks.json",
    os.path.expanduser("~/bookmarks.json"),
]

def load_source_bookmarks():
    """Load bookmarks from bookmarks.json."""
    for path in SOURCE_FILES:
        if os.path.isfile(path):
            with open(path) as f:
                return json.load(f), path
    # Try S3
    try:
        acct = subprocess.run(
            ["aws", "sts", "get-caller-identity", "--query", "Account", "--output", "text"],
            capture_output=True, text=True).stdout.strip()
        if acct:
            r = subprocess.run(
                ["aws", "s3", "cp", f"s3://claude-portable-state-{acct}/bookmarks.json", "-"],
                capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.strip():
                return json.loads(r.stdout), "s3"
    except Exception:
        pass
    return None, None

def load_chrome_bookmarks():
    """Load existing Chrome bookmarks file."""
    if os.path.isfile(BOOKMARKS_FILE):
        with open(BOOKMARKS_FILE) as f:
            return json.load(f)
    return {
        "checksum": "",
        "roots": {
            "bookmark_bar": {"children": [], "name": "Bookmarks bar", "type": "folder"},
            "other": {"children": [], "name": "Other bookmarks", "type": "folder"},
            "synced": {"children": [], "name": "Mobile bookmarks", "type": "folder"}
        },
        "version": 1
    }

def find_or_create_folder(parent, folder_name):
    """Find or create a folder in Chrome bookmarks."""
    for child in parent.get("children", []):
        if child.get("type") == "folder" and child.get("name") == folder_name:
            return child
    folder = {
        "children": [],
        "name": folder_name,
        "type": "folder",
        "id": str(int(time.time() * 1000)),
    }
    parent.setdefault("children", []).append(folder)
    return folder

def url_exists(parent, url):
    """Check if a URL already exists in a folder."""
    for child in parent.get("children", []):
        if child.get("type") == "url" and child.get("url") == url:
            return True
    return False

def import_bookmarks(source, chrome_bm):
    """Merge source bookmarks into Chrome bookmarks."""
    bar = chrome_bm["roots"]["bookmark_bar"]
    added = 0
    for group in source.get("bookmarks", []):
        folder_name = group.get("folder", "Imported")
        folder = find_or_create_folder(bar, folder_name)
        for item in group.get("items", []):
            if not url_exists(folder, item["url"]):
                folder["children"].append({
                    "name": item["name"],
                    "type": "url",
                    "url": item["url"],
                    "id": str(int(time.time() * 1000) + added),
                })
                added += 1
    return added

def main():
    source, path = load_source_bookmarks()
    if not source:
        print("No bookmarks.json found.")
        return

    print(f"Source: {path}")
    print(f"Bookmarks: {sum(len(g.get('items', [])) for g in source.get('bookmarks', []))}")

    chrome_bm = load_chrome_bookmarks()
    added = import_bookmarks(source, chrome_bm)

    os.makedirs(os.path.dirname(BOOKMARKS_FILE), exist_ok=True)
    with open(BOOKMARKS_FILE, "w") as f:
        json.dump(chrome_bm, f, indent=3)

    print(f"Added: {added} new bookmarks")
    print(f"Written: {BOOKMARKS_FILE}")
    print("Restart Chrome to see changes (browser restart)")

if __name__ == "__main__":
    main()
