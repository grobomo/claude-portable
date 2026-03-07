#!/bin/bash
# Health check: verify Claude auth, MCP servers, skills, and session storage.
set -euo pipefail

PASS=0
FAIL=0
WARN=0

check() {
  local label="$1"; shift
  if "$@" > /dev/null 2>&1; then
    echo "  [OK]   $label"
    ((PASS++))
  else
    echo "  [FAIL] $label"
    ((FAIL++))
  fi
}

warn() {
  local label="$1"
  echo "  [WARN] $label"
  ((WARN++))
}

echo "=== Claude Portable Health Check ==="
echo ""

# 1. Claude CLI installed
echo "[1/7] Claude CLI"
check "claude binary exists" which claude
CLAUDE_VER=$(claude --version 2>/dev/null || echo "unknown")
echo "       Version: $CLAUDE_VER"

# 2. OAuth credentials
echo "[2/7] Authentication"
CREDS_FILE="$HOME/.claude/.credentials.json"
if [ -f "$CREDS_FILE" ]; then
  check "credentials.json exists" test -f "$CREDS_FILE"
  # Check token is not empty
  if python3 -c "import json; d=json.load(open('$CREDS_FILE')); assert d.get('claudeAiOauth',{}).get('accessToken','')" 2>/dev/null; then
    echo "  [OK]   OAuth access token present"
    ((PASS++))
  else
    echo "  [FAIL] OAuth access token missing or empty"
    ((FAIL++))
  fi
else
  echo "  [FAIL] credentials.json not found"
  ((FAIL++))
fi

# 3. Onboarding bypass
echo "[3/7] Onboarding"
check ".claude.json exists at ~/" test -f "$HOME/.claude.json"
check "settings.local.json exists" test -f "$HOME/.claude/settings.local.json"
if [ -f "$HOME/.claude.json" ]; then
  if python3 -c "import json; assert json.load(open('$HOME/.claude.json')).get('hasCompletedOnboarding')" 2>/dev/null; then
    echo "  [OK]   hasCompletedOnboarding = true"
    ((PASS++))
  else
    echo "  [FAIL] hasCompletedOnboarding not set"
    ((FAIL++))
  fi
fi

# 4. Config sync (skills, hooks, rules)
echo "[4/7] Config"
CLAUDE_DIR="$HOME/.claude"
SKILLS_COUNT=$(find "$CLAUDE_DIR/skills" -name "SKILL.md" 2>/dev/null | wc -l)
HOOKS_COUNT=$(find "$CLAUDE_DIR/hooks" -name "*.js" -o -name "*.sh" 2>/dev/null | wc -l)
RULES_COUNT=$(find "$CLAUDE_DIR/rules" -name "*.md" 2>/dev/null | wc -l)
echo "       Skills: $SKILLS_COUNT | Hooks: $HOOKS_COUNT | Rules: $RULES_COUNT"
if [ "$SKILLS_COUNT" -gt 0 ]; then
  echo "  [OK]   Skills loaded"
  ((PASS++))
else
  warn "No skills found (sync may not have run)"
fi
if [ "$HOOKS_COUNT" -gt 0 ]; then
  echo "  [OK]   Hooks loaded"
  ((PASS++))
else
  warn "No hooks found"
fi

# 5. MCP servers
echo "[5/7] MCP Servers"
MCP_COUNT=$(find /opt/mcp -maxdepth 1 -type d -name "mcp-*" 2>/dev/null | wc -l)
echo "       MCP server dirs: $MCP_COUNT"
for dir in /opt/mcp/mcp-*/; do
  [ -d "$dir" ] || continue
  svc=$(basename "$dir")
  if [ -f "$dir/package.json" ] || [ -f "$dir/server.py" ]; then
    echo "  [OK]   $svc"
    ((PASS++))
  else
    warn "$svc (no server entry point found)"
  fi
done
if [ "$MCP_COUNT" -eq 0 ]; then
  warn "No MCP servers installed"
fi

# 6. SSH server
echo "[6/7] SSH Server"
if pgrep -x sshd > /dev/null 2>&1; then
  echo "  [OK]   sshd running"
  ((PASS++))
else
  warn "sshd not running (SSH disabled or no key provided)"
fi

# 7. Session storage
echo "[7/7] Session Storage"
check "/data/sessions writable" test -w /data/sessions
check "/data/exports writable" test -w /data/exports
SESSION_COUNT=$(find /data/sessions -maxdepth 1 -type d 2>/dev/null | wc -l)
echo "       Sessions on disk: $((SESSION_COUNT - 1))"

# Summary
echo ""
echo "=== Results ==="
echo "  Passed: $PASS | Failed: $FAIL | Warnings: $WARN"
if [ "$FAIL" -gt 0 ]; then
  echo "  STATUS: UNHEALTHY"
  exit 1
else
  echo "  STATUS: HEALTHY"
  exit 0
fi
