#!/bin/bash
# Pull Claude config (rules, hooks, skills, settings) from git repos.
# Runs inside the container at startup.
set -euo pipefail

CLAUDE_DIR="$HOME/.claude"
MCP_DIR="/opt/mcp"
DEFAULTS_REPO="https://github.com/grobomo/claude-code-defaults.git"
SKILLS_REPO="https://github.com/grobomo/claude-code-skills.git"

# Configure git auth if token available
if [ -n "${GITHUB_TOKEN:-}" ]; then
  git config --global url."https://${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"
fi

# --- Clone/pull config defaults ---
DEFAULTS_DIR="/opt/claude-portable/defaults"
if [ -d "$DEFAULTS_DIR/.git" ]; then
  (cd "$DEFAULTS_DIR" && git pull -q 2>/dev/null) || true
else
  git clone -q "$DEFAULTS_REPO" "$DEFAULTS_DIR" 2>/dev/null || true
fi

if [ -d "$DEFAULTS_DIR" ]; then
  # Copy CLAUDE.md
  [ -f "$DEFAULTS_DIR/claude-md/CLAUDE.md" ] && cp "$DEFAULTS_DIR/claude-md/CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md"

  # Copy settings.json (will be path-rewritten in next step)
  [ -f "$DEFAULTS_DIR/settings.json" ] && cp "$DEFAULTS_DIR/settings.json" "$CLAUDE_DIR/settings.json"

  # Copy hooks
  if [ -d "$DEFAULTS_DIR/hooks" ]; then
    mkdir -p "$CLAUDE_DIR/hooks"
    cp -r "$DEFAULTS_DIR/hooks/"* "$CLAUDE_DIR/hooks/" 2>/dev/null || true
  fi

  # Copy rules
  if [ -d "$DEFAULTS_DIR/instructions" ]; then
    mkdir -p "$CLAUDE_DIR/rules"
    cp -r "$DEFAULTS_DIR/instructions/"* "$CLAUDE_DIR/rules/" 2>/dev/null || true
  fi

  # Copy credentials helper
  if [ -d "$DEFAULTS_DIR/credentials" ]; then
    mkdir -p "$CLAUDE_DIR/super-manager/credentials"
    cp -r "$DEFAULTS_DIR/credentials/"* "$CLAUDE_DIR/super-manager/credentials/" 2>/dev/null || true
  fi

  # Copy skills
  if [ -d "$DEFAULTS_DIR/skills" ]; then
    for skill_dir in "$DEFAULTS_DIR/skills"/*/; do
      skill_name=$(basename "$skill_dir")
      mkdir -p "$CLAUDE_DIR/skills/$skill_name"
      cp -r "$skill_dir"* "$CLAUDE_DIR/skills/$skill_name/" 2>/dev/null || true
    done
  fi

  echo "  Config synced from claude-code-defaults."
fi

# --- Clone/pull published skills ---
SKILLS_DIR="/opt/claude-portable/skills-marketplace"
if [ -d "$SKILLS_DIR/.git" ]; then
  (cd "$SKILLS_DIR" && git pull -q 2>/dev/null) || true
else
  git clone -q "$SKILLS_REPO" "$SKILLS_DIR" 2>/dev/null || true
fi

if [ -d "$SKILLS_DIR/plugins" ]; then
  for plugin_dir in "$SKILLS_DIR/plugins"/*/; do
    plugin_name=$(basename "$plugin_dir")
    if [ -d "$plugin_dir/skills" ]; then
      for skill_dir in "$plugin_dir/skills"/*/; do
        skill_name=$(basename "$skill_dir")
        mkdir -p "$CLAUDE_DIR/skills/$skill_name"
        cp -r "$skill_dir"* "$CLAUDE_DIR/skills/$skill_name/" 2>/dev/null || true
      done
    fi
  done
  echo "  Skills synced from marketplace."
fi

# --- Clone MCP server repos (private -- needs GITHUB_TOKEN) ---
if [ -n "${GITHUB_TOKEN:-}" ]; then
  MCP_REPOS="${CLAUDE_PORTABLE_MCP_REPOS:-mcp-manager mcp-v1-lite mcp-wiki-lite mcp-jira-lite mcp-trello-lite mcp-trendgpt}"
  MCP_ORG="${CLAUDE_PORTABLE_MCP_ORG:-joel-ginsberg_tmemu}"

  for repo in $MCP_REPOS; do
    target="$MCP_DIR/$repo"
    if [ -d "$target/.git" ]; then
      (cd "$target" && git pull -q 2>/dev/null) || true
    else
      git clone -q "https://github.com/${MCP_ORG}/${repo}.git" "$target" 2>/dev/null || {
        echo "  WARNING: Failed to clone $repo"
      }
    fi
  done
  echo "  MCP repos synced."
else
  echo "  No GITHUB_TOKEN -- skipping MCP repo clone."
fi

# Clean up git credential helper
git config --global --unset url."https://${GITHUB_TOKEN:-}@github.com/".insteadOf 2>/dev/null || true
