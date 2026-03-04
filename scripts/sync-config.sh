#!/bin/bash
# Pull Claude config from git repos, driven by components.yaml manifest.
# Runs inside the container at startup.
set -euo pipefail

CLAUDE_DIR="$HOME/.claude"
MCP_DIR="/opt/mcp"
CACHE_DIR="/opt/claude-portable/repos"
MANIFEST="/opt/claude-portable/config/components.yaml"

# Configure git auth if token available
if [ -n "${GITHUB_TOKEN:-}" ]; then
  git config --global url."https://${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"
fi

mkdir -p "$CACHE_DIR" "$CLAUDE_DIR" "$MCP_DIR"

# Parse components.yaml with Python (available in container)
python3 << 'PYEOF'
import yaml, json, os, subprocess, sys, shutil

manifest = os.environ.get("MANIFEST", "/opt/claude-portable/config/components.yaml")
cache_dir = os.environ.get("CACHE_DIR", "/opt/claude-portable/repos")
claude_dir = os.environ.get("CLAUDE_DIR", os.path.expanduser("~/.claude"))
mcp_dir = os.environ.get("MCP_DIR", "/opt/mcp")
has_token = bool(os.environ.get("GITHUB_TOKEN"))

if not os.path.exists(manifest):
    print("  WARNING: components.yaml not found, using legacy sync")
    sys.exit(1)

with open(manifest) as f:
    components = yaml.safe_load(f)

if not components:
    print("  WARNING: components.yaml is empty")
    sys.exit(1)

# Group components by repo to minimize clones
repos = {}
for comp in components:
    if not comp.get("enabled", True):
        continue
    if comp.get("visibility") == "private" and not has_token:
        print(f"  SKIP {comp['name']} (private, no GITHUB_TOKEN)")
        continue
    repo = comp["repo"]
    repos.setdefault(repo, []).append(comp)

def clone_or_pull(repo, repo_dir):
    """Clone or pull a repo, return True if repo exists."""
    if os.path.isdir(os.path.join(repo_dir, ".git")):
        subprocess.run(["git", "pull", "-q"], cwd=repo_dir,
                       capture_output=True, timeout=60)
        return True
    else:
        url = f"https://github.com/{repo}.git"
        r = subprocess.run(["git", "clone", "-q", "--depth=1", url, repo_dir],
                           capture_output=True, timeout=120)
        if r.returncode != 0:
            print(f"  WARNING: Failed to clone {repo}: {r.stderr.decode()[:100]}")
            return False
        return True

def copy_tree(src, dst):
    """Copy directory tree, creating parents as needed."""
    if not os.path.isdir(src):
        return
    os.makedirs(dst, exist_ok=True)
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)

for repo, comps in repos.items():
    # Use org_repo as cache dir name
    repo_slug = repo.replace("/", "_")
    repo_dir = os.path.join(cache_dir, repo_slug)

    if not clone_or_pull(repo, repo_dir):
        continue

    for comp in comps:
        name = comp["name"]
        ctype = comp["type"]
        target = comp["target"]
        sparse = comp.get("sparse")

        # Determine source directory
        if sparse:
            src = os.path.join(repo_dir, sparse)
        else:
            src = repo_dir

        if not os.path.exists(src):
            print(f"  WARNING: {name} source not found at {src}")
            continue

        if ctype == "config":
            # Config defaults: copy specific subdirs to ~/.claude/
            for subdir, dest in [
                ("claude-md/CLAUDE.md", os.path.join(claude_dir, "CLAUDE.md")),
                ("settings.json", os.path.join(claude_dir, "settings.json")),
            ]:
                s = os.path.join(src, subdir)
                if os.path.isfile(s):
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copy2(s, dest)

            # Copy hooks
            hooks_src = os.path.join(src, "hooks")
            if os.path.isdir(hooks_src):
                copy_tree(hooks_src, os.path.join(claude_dir, "hooks"))

            # Copy rules (instructions/ in repo -> rules/ in container)
            rules_src = os.path.join(src, "instructions")
            if os.path.isdir(rules_src):
                copy_tree(rules_src, os.path.join(claude_dir, "rules"))

            # Copy credentials helper
            creds_src = os.path.join(src, "credentials")
            if os.path.isdir(creds_src):
                copy_tree(creds_src, os.path.join(claude_dir, "super-manager", "credentials"))

            # Copy skills from defaults
            skills_src = os.path.join(src, "skills")
            if os.path.isdir(skills_src):
                for skill in os.listdir(skills_src):
                    skill_src = os.path.join(skills_src, skill)
                    if os.path.isdir(skill_src):
                        copy_tree(skill_src, os.path.join(claude_dir, "skills", skill))

            # Copy super-manager internals if present
            sm_src = os.path.join(src, "super-manager")
            if os.path.isdir(sm_src):
                copy_tree(sm_src, os.path.join(claude_dir, "super-manager"))

            print(f"  [config] {name} synced")

        elif ctype == "skill-marketplace":
            # Marketplace: copy plugins/*/skills/*/ to ~/.claude/skills/
            plugins_dir = os.path.join(src, "plugins")
            if os.path.isdir(plugins_dir):
                count = 0
                for plugin in os.listdir(plugins_dir):
                    plugin_skills = os.path.join(plugins_dir, plugin, "skills")
                    if os.path.isdir(plugin_skills):
                        for skill in os.listdir(plugin_skills):
                            skill_src = os.path.join(plugin_skills, skill)
                            if os.path.isdir(skill_src):
                                copy_tree(skill_src, os.path.join(claude_dir, "skills", skill))
                                count += 1
                print(f"  [marketplace] {name}: {count} skills synced")

        elif ctype == "mcp":
            # MCP server: copy to /opt/mcp/<name>/
            if sparse:
                copy_tree(src, target)
            else:
                copy_tree(src, target)
            print(f"  [mcp] {name} -> {target}")

        else:
            print(f"  WARNING: Unknown component type '{ctype}' for {name}")

print("  Component sync complete.")
PYEOF

# If Python manifest parsing failed, fall back to legacy behavior
if [ $? -ne 0 ]; then
  echo "  Falling back to legacy sync..."

  # Legacy: clone defaults
  DEFAULTS_REPO="https://github.com/grobomo/claude-code-defaults.git"
  DEFAULTS_DIR="$CACHE_DIR/grobomo_claude-code-defaults"
  if [ ! -d "$DEFAULTS_DIR/.git" ]; then
    git clone -q "$DEFAULTS_REPO" "$DEFAULTS_DIR" 2>/dev/null || true
  fi
  if [ -d "$DEFAULTS_DIR" ]; then
    [ -f "$DEFAULTS_DIR/claude-md/CLAUDE.md" ] && cp "$DEFAULTS_DIR/claude-md/CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md"
    [ -f "$DEFAULTS_DIR/settings.json" ] && cp "$DEFAULTS_DIR/settings.json" "$CLAUDE_DIR/settings.json"
    [ -d "$DEFAULTS_DIR/hooks" ] && mkdir -p "$CLAUDE_DIR/hooks" && cp -r "$DEFAULTS_DIR/hooks/"* "$CLAUDE_DIR/hooks/" 2>/dev/null || true
    [ -d "$DEFAULTS_DIR/instructions" ] && mkdir -p "$CLAUDE_DIR/rules" && cp -r "$DEFAULTS_DIR/instructions/"* "$CLAUDE_DIR/rules/" 2>/dev/null || true
    echo "  Legacy config synced."
  fi

  # Legacy: clone MCP monorepo
  if [ -n "${GITHUB_TOKEN:-}" ]; then
    MCP_DEV_DIR="$CACHE_DIR/joel-ginsberg_tmemu_mcp-dev"
    if [ ! -d "$MCP_DEV_DIR/.git" ]; then
      git clone -q "https://github.com/joel-ginsberg_tmemu/mcp-dev.git" "$MCP_DEV_DIR" 2>/dev/null || true
    fi
    if [ -d "$MCP_DEV_DIR" ]; then
      for server in mcp-manager mcp-v1-lite mcp-jira-lite mcp-trend-docs mcp-trendgpt; do
        [ -d "$MCP_DEV_DIR/$server" ] && cp -r "$MCP_DEV_DIR/$server" "$MCP_DIR/$server" 2>/dev/null || true
      done
      echo "  Legacy MCP synced."
    fi
  fi
fi

# Clean up git credential helper
git config --global --unset url."https://${GITHUB_TOKEN:-}@github.com/".insteadOf 2>/dev/null || true
