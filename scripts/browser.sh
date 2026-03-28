#!/bin/bash
# Manage headed browser session with VNC access.
#
# Usage:
#   browser start          Start Xvfb + VNC + Chrome
#   browser stop           Stop Chrome + VNC + Xvfb
#   browser status         Show what's running
#   browser restart        Stop + start
#   browser url <URL>      Open URL in running Chrome
#   browser sync-push      Push Chrome profile to S3
#   browser sync-pull      Pull Chrome profile from S3
set -euo pipefail

DISPLAY_NUM="${CLAUDE_PORTABLE_DISPLAY:-99}"
export DISPLAY=":${DISPLAY_NUM}"
CHROME_PROFILE="/data/chrome-profile"
VNC_PORT="${CLAUDE_PORTABLE_VNC_PORT:-5900}"
CHROME_DEBUG_PORT="${CLAUDE_PORTABLE_CHROME_DEBUG_PORT:-9222}"
REGION="${AWS_DEFAULT_REGION:-us-east-2}"

cmd="${1:-help}"
shift || true

get_bucket() {
  local ACCT
  ACCT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")
  [ -n "$ACCT" ] && echo "claude-portable-state-$ACCT" || echo ""
}

case "$cmd" in
  start)
    echo "=== Starting Browser Session ==="

    # Start Xvfb if not running
    if ! pgrep -f "Xvfb :${DISPLAY_NUM}" &>/dev/null; then
      echo "  Starting Xvfb on :${DISPLAY_NUM}..."
      nohup Xvfb ":${DISPLAY_NUM}" -screen 0 1920x1080x24 &>/dev/null &
      sleep 2
      if ! pgrep -f "Xvfb :${DISPLAY_NUM}" &>/dev/null; then
        echo "  ERROR: Xvfb failed to start"
        return 1
      fi
    else
      echo "  Xvfb already running on :${DISPLAY_NUM}"
    fi

    # Start VNC server if not running
    if ! pgrep -f "x11vnc.*${VNC_PORT}" &>/dev/null; then
      echo "  Starting VNC on port ${VNC_PORT}..."
      nohup x11vnc -display ":${DISPLAY_NUM}" -forever -nopw -rfbport "${VNC_PORT}" \
        -shared -q &>/dev/null &
      sleep 1
      if ! pgrep -f "x11vnc.*${VNC_PORT}" &>/dev/null; then
        echo "  ERROR: VNC failed to start"
        return 1
      fi
    else
      echo "  VNC already running on port ${VNC_PORT}"
    fi

    # Start Chrome if not running
    if ! pgrep -f "chrome.*${CHROME_DEBUG_PORT}" &>/dev/null; then
      echo "  Starting Chrome..."
      # Pull profile from S3 if empty
      if [ ! -f "$CHROME_PROFILE/Default/Preferences" ]; then
        BUCKET=$(get_bucket)
        if [ -n "$BUCKET" ]; then
          aws s3 sync "s3://$BUCKET/chrome-profile/" "$CHROME_PROFILE/" \
            --region "$REGION" --quiet --sse AES256 2>/dev/null || true
        fi
      fi

      # Build Chrome flags
      CHROME_FLAGS=(
        --no-sandbox --disable-gpu --no-first-run --disable-sync
        --disable-background-networking
        --remote-debugging-port="${CHROME_DEBUG_PORT}"
        --window-size=1920,1080
        --user-data-dir="$CHROME_PROFILE"
      )

      # Load blueprint-extra Chrome extension if available
      EXTENSION_DIR="/opt/mcp/blueprint-extra-mcp/extensions"
      if [ -d "$EXTENSION_DIR" ]; then
        # Collect all subdirectories as comma-separated extension paths
        EXT_PATHS=""
        for ext in "$EXTENSION_DIR"/*/; do
          [ -d "$ext" ] || continue
          [ -n "$EXT_PATHS" ] && EXT_PATHS="$EXT_PATHS,"
          EXT_PATHS="$EXT_PATHS${ext%/}"
        done
        if [ -n "$EXT_PATHS" ]; then
          CHROME_FLAGS+=(--load-extension="$EXT_PATHS")
          echo "  Loading extensions from: $EXTENSION_DIR"
        fi
      fi

      nohup google-chrome-stable "${CHROME_FLAGS[@]}" &>/dev/null &
      sleep 3
      echo "  Chrome running (profile: $CHROME_PROFILE)"
    else
      echo "  Chrome already running"
    fi

    echo ""
    echo "  Connect via SSH tunnel from local machine:"
    echo "    ccc vnc"
    echo "  Then open RealVNC -> localhost:${VNC_PORT}"
    echo "  Chrome DevTools -> http://localhost:${CHROME_DEBUG_PORT}"
    ;;

  stop)
    echo "Stopping browser session..."
    # Push profile to S3 before stopping
    BUCKET=$(get_bucket)
    if [ -n "$BUCKET" ] && [ -d "$CHROME_PROFILE/Default" ]; then
      echo "  Syncing Chrome profile to S3..."
      aws s3 sync "$CHROME_PROFILE/" "s3://$BUCKET/chrome-profile/" \
        --region "$REGION" --quiet --sse AES256 \
        --exclude "*.log" --exclude "CacheStorage/*" --exclude "Cache/*" \
        --exclude "Code Cache/*" --exclude "GPUCache/*" --exclude "Service Worker/*" \
        2>/dev/null || true
    fi
    pkill -f "chrome.*${CHROME_DEBUG_PORT}" 2>/dev/null || true
    pkill -f "x11vnc.*${VNC_PORT}" 2>/dev/null || true
    pkill -f "Xvfb :${DISPLAY_NUM}" 2>/dev/null || true
    echo "  Done."
    ;;

  restart)
    $0 stop
    sleep 1
    $0 start
    ;;

  status)
    echo "=== Browser Session Status ==="
    printf "  %-12s %s\n" "Xvfb:" "$(pgrep -f "Xvfb :${DISPLAY_NUM}" &>/dev/null && echo "running (display :${DISPLAY_NUM})" || echo "stopped")"
    printf "  %-12s %s\n" "VNC:" "$(pgrep -f "x11vnc.*${VNC_PORT}" &>/dev/null && echo "running (port ${VNC_PORT})" || echo "stopped")"
    printf "  %-12s %s\n" "Chrome:" "$(pgrep -f "chrome.*${CHROME_DEBUG_PORT}" &>/dev/null && echo "running (debug port ${CHROME_DEBUG_PORT})" || echo "stopped")"
    printf "  %-12s %s\n" "Profile:" "$CHROME_PROFILE"
    if [ -d "$CHROME_PROFILE/Default" ]; then
      PROFILE_SIZE=$(du -sh "$CHROME_PROFILE" 2>/dev/null | cut -f1)
      printf "  %-12s %s\n" "Size:" "$PROFILE_SIZE"
    fi
    ;;

  url)
    URL="${1:-about:blank}"
    if ! pgrep -f "chrome.*${CHROME_DEBUG_PORT}" &>/dev/null; then
      echo "Chrome not running. Start with: browser start"
      exit 1
    fi
    # Use Chrome DevTools protocol to open URL
    curl -s "http://localhost:${CHROME_DEBUG_PORT}/json/new?${URL}" &>/dev/null
    echo "Opened: $URL"
    ;;

  sync-push)
    BUCKET=$(get_bucket)
    if [ -z "$BUCKET" ]; then echo "No S3 bucket available."; exit 1; fi
    echo "Pushing Chrome profile to S3..."
    aws s3 sync "$CHROME_PROFILE/" "s3://$BUCKET/chrome-profile/" \
      --region "$REGION" --quiet --sse AES256 \
      --exclude "*.log" --exclude "CacheStorage/*" --exclude "Cache/*" \
      --exclude "Code Cache/*" --exclude "GPUCache/*" --exclude "Service Worker/*"
    echo "Done."
    ;;

  sync-pull)
    BUCKET=$(get_bucket)
    if [ -z "$BUCKET" ]; then echo "No S3 bucket available."; exit 1; fi
    echo "Pulling Chrome profile from S3..."
    aws s3 sync "s3://$BUCKET/chrome-profile/" "$CHROME_PROFILE/" \
      --region "$REGION" --quiet --sse AES256
    echo "Done."
    ;;

  help|*)
    cat <<'EOF'
browser -- Manage headed Chrome browser session with VNC

Commands:
  browser start          Start Xvfb + VNC + Chrome (pulls profile from S3)
  browser stop           Stop all + push profile to S3
  browser restart        Stop + start
  browser status         Show what's running
  browser url <URL>      Open URL in Chrome
  browser sync-push      Push Chrome profile to S3
  browser sync-pull      Pull Chrome profile from S3

Profile persistence:
  Chrome profile stored at /data/chrome-profile/ (Docker volume)
  Synced to S3 on stop/push -- survives instance termination
  Cookies, bookmarks, extensions, logins all persist

Connect:
  From local: ccc vnc
  RealVNC -> localhost:5900
  Chrome DevTools -> http://localhost:9222
EOF
    ;;
esac
