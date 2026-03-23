#!/bin/bash
# Sync Claude conversation state to/from S3.
# Makes EC2 instances ephemeral -- any instance can resume any conversation.
#
# Usage:
#   state-sync pull                    Pull all state from S3
#   state-sync push                    Push current state to S3
#   state-sync list                    List available conversations in S3
#   state-sync resume <session-id>     Show resume command for a conversation
#   state-sync auto                    Start background auto-sync (every 60s)
#   state-sync setup                   Create S3 bucket with encryption
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-2}"
ME="${CLAUDE_PORTABLE_ID:-$(hostname)}"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
DATA_DIR="/data"

# Auto-derive bucket from AWS account
get_bucket() {
  if [ -n "${CLAUDE_PORTABLE_STATE_BUCKET:-}" ]; then
    echo "$CLAUDE_PORTABLE_STATE_BUCKET"
    return
  fi
  local ACCT
  ACCT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")
  if [ -z "$ACCT" ]; then
    echo "ERROR: AWS credentials not configured." >&2
    return 1
  fi
  echo "claude-portable-state-$ACCT"
}

BUCKET=$(get_bucket) || exit 1
S3_ROOT="s3://$BUCKET"

# Paths to sync (conversation state only, not plugins/skills/config)
SYNC_PATHS=(
  "projects"        # conversation JSONL + tool results
  "sessions"        # session metadata (PID -> UUID mapping)
  "session-env"     # per-session environment
)

cmd="${1:-help}"
shift || true

case "$cmd" in
  setup)
    echo "=== Setting up state bucket ==="
    # Create bucket if needed
    if ! aws s3 ls "s3://$BUCKET" --region "$REGION" &>/dev/null; then
      aws s3 mb "s3://$BUCKET" --region "$REGION"
      echo "  Created bucket: $BUCKET"
    else
      echo "  Bucket exists: $BUCKET"
    fi

    # Enable default encryption (AES-256 SSE-S3)
    aws s3api put-bucket-encryption \
      --bucket "$BUCKET" \
      --region "$REGION" \
      --server-side-encryption-configuration '{
        "Rules": [{
          "ApplyServerSideEncryptionByDefault": {
            "SSEAlgorithm": "AES256"
          },
          "BucketKeyEnabled": true
        }]
      }'
    echo "  Encryption: AES-256 at rest (SSE-S3), TLS in transit"

    # Enable versioning (recover from accidental overwrites)
    aws s3api put-bucket-versioning \
      --bucket "$BUCKET" \
      --region "$REGION" \
      --versioning-configuration Status=Enabled
    echo "  Versioning: enabled"

    # Block public access
    aws s3api put-public-access-block \
      --bucket "$BUCKET" \
      --region "$REGION" \
      --public-access-block-configuration \
        BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
    echo "  Public access: blocked"

    # Lifecycle: expire old versions after 30 days
    aws s3api put-bucket-lifecycle-configuration \
      --bucket "$BUCKET" \
      --region "$REGION" \
      --lifecycle-configuration '{
        "Rules": [{
          "ID": "expire-old-versions",
          "Status": "Enabled",
          "NoncurrentVersionExpiration": {
            "NoncurrentDays": 30
          },
          "Filter": {"Prefix": ""}
        }]
      }'
    echo "  Lifecycle: old versions expire after 30 days"
    echo "  Done."
    ;;

  pull)
    echo "=== Pulling state from S3 ==="
    for P in "${SYNC_PATHS[@]}"; do
      if aws s3 ls "$S3_ROOT/claude-state/$P/" --region "$REGION" &>/dev/null; then
        aws s3 sync "$S3_ROOT/claude-state/$P/" "$CLAUDE_DIR/$P/" \
          --region "$REGION" --quiet --sse AES256
        COUNT=$(find "$CLAUDE_DIR/$P" -type f 2>/dev/null | wc -l)
        echo "  $P: $COUNT files"
      fi
    done
    # Pull history
    if aws s3 ls "$S3_ROOT/claude-state/history.jsonl" --region "$REGION" &>/dev/null; then
      aws s3 cp "$S3_ROOT/claude-state/history.jsonl" "$CLAUDE_DIR/history.jsonl" \
        --region "$REGION" --quiet --sse AES256
      echo "  history.jsonl: pulled"
    fi
    # Pull session logs
    if aws s3 ls "$S3_ROOT/session-logs/" --region "$REGION" &>/dev/null; then
      aws s3 sync "$S3_ROOT/session-logs/" "$DATA_DIR/sessions/" \
        --region "$REGION" --quiet --sse AES256
      COUNT=$(find "$DATA_DIR/sessions" -type f 2>/dev/null | wc -l)
      echo "  session-logs: $COUNT files"
    fi
    echo "  Done."
    ;;

  push)
    echo "=== Pushing state to S3 ==="
    for P in "${SYNC_PATHS[@]}"; do
      if [ -d "$CLAUDE_DIR/$P" ]; then
        aws s3 sync "$CLAUDE_DIR/$P/" "$S3_ROOT/claude-state/$P/" \
          --region "$REGION" --quiet --sse AES256
        COUNT=$(find "$CLAUDE_DIR/$P" -type f 2>/dev/null | wc -l)
        echo "  $P: $COUNT files"
      fi
    done
    # Push history
    if [ -f "$CLAUDE_DIR/history.jsonl" ]; then
      aws s3 cp "$CLAUDE_DIR/history.jsonl" "$S3_ROOT/claude-state/history.jsonl" \
        --region "$REGION" --quiet --sse AES256
      echo "  history.jsonl: pushed"
    fi
    # Push session logs
    if [ -d "$DATA_DIR/sessions" ]; then
      aws s3 sync "$DATA_DIR/sessions/" "$S3_ROOT/session-logs/" \
        --region "$REGION" --quiet --sse AES256
      COUNT=$(find "$DATA_DIR/sessions" -type f 2>/dev/null | wc -l)
      echo "  session-logs: $COUNT files"
    fi
    # Write instance marker (so we know which instance last synced)
    echo "{\"instance\": \"$ME\", \"synced\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" | \
      aws s3 cp - "$S3_ROOT/claude-state/.last-sync.json" --region "$REGION" --quiet --sse AES256
    echo "  Done."
    ;;

  list)
    echo "=== Conversations in S3 ==="
    echo ""

    # Download conversation files to temp dir for parsing
    TMPDIR=$(mktemp -d)
    aws s3 sync "$S3_ROOT/claude-state/projects/" "$TMPDIR/projects/" \
      --region "$REGION" --quiet --exclude "*" --include "*.jsonl" 2>/dev/null

    # Parse conversations with Python for rich display
    python3 << 'PYEOF'
import json, glob, os, sys
from datetime import datetime

tmpdir = os.environ.get("TMPDIR", "/tmp")
files = sorted(glob.glob(f"{tmpdir}/projects/*/*.jsonl"))
if not files:
    print("  No conversations found.")
    sys.exit(0)

convos = []
for f in files:
    sid = os.path.basename(f).replace(".jsonl", "")
    size = os.path.getsize(f)
    lines = open(f).readlines()

    user_msgs = []
    first_ts = None
    last_ts = None
    session_name = None
    instance = None

    for line in lines:
        try:
            d = json.loads(line)
            ts = d.get("timestamp", "")
            if ts:
                if not first_ts: first_ts = ts
                last_ts = ts

            if d.get("type") == "user":
                msg = d.get("message", {})
                content = msg.get("content", "") if isinstance(msg, dict) else ""
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text" and c["text"].strip():
                            user_msgs.append(c["text"].strip()[:100])
                            break
                elif isinstance(content, str) and content.strip():
                    user_msgs.append(content.strip()[:100])
        except:
            pass

    convos.append({
        "id": sid,
        "short_id": sid[:8],
        "size_kb": size // 1024,
        "messages": len(user_msgs),
        "first_ts": first_ts or "?",
        "last_ts": last_ts or "?",
        "topics": user_msgs[:3],
        "first_msg": user_msgs[0] if user_msgs else "(empty session)",
    })

# Sort by last timestamp, newest first
convos.sort(key=lambda c: c["last_ts"], reverse=True)

for i, c in enumerate(convos):
    ts_display = c["last_ts"][:16].replace("T", " ") if c["last_ts"] != "?" else "?"
    print(f"  [{i+1}] {c['id']}")
    print(f"      Last active: {ts_display}  |  {c['messages']} messages  |  {c['size_kb']}KB")
    for j, topic in enumerate(c["topics"]):
        prefix = ">" if j == 0 else " "
        print(f"      {prefix} {topic}")
    print()

print(f"  Resume: claude --resume <session-id>")
print(f"  Resume interactive: claude --resume")
print(f"  Tip: use 'claude -n \"project-name\"' to name sessions for easy identification")
PYEOF

    rm -rf "$TMPDIR"

    echo ""
    LAST=$(aws s3 cp "$S3_ROOT/claude-state/.last-sync.json" - --region "$REGION" 2>/dev/null || echo "")
    if [ -n "$LAST" ]; then
      INST=$(echo "$LAST" | python3 -c "import json,sys; print(json.load(sys.stdin).get('instance','?'))" 2>/dev/null || echo "?")
      WHEN=$(echo "$LAST" | python3 -c "import json,sys; print(json.load(sys.stdin).get('synced','?'))" 2>/dev/null || echo "?")
      echo "  Last synced by: $INST at $WHEN"
    fi
    ;;

  resume)
    SESSION="${1:-}"
    # Pull latest state first
    echo "Pulling latest state from S3..."
    for P in "${SYNC_PATHS[@]}"; do
      if aws s3 ls "$S3_ROOT/claude-state/$P/" --region "$REGION" &>/dev/null; then
        aws s3 sync "$S3_ROOT/claude-state/$P/" "$CLAUDE_DIR/$P/" \
          --region "$REGION" --quiet --sse AES256
      fi
    done
    [ -f "$CLAUDE_DIR/history.jsonl" ] || \
      aws s3 cp "$S3_ROOT/claude-state/history.jsonl" "$CLAUDE_DIR/history.jsonl" \
        --region "$REGION" --quiet --sse AES256 2>/dev/null || true
    echo "  State pulled."
    echo ""

    if [ -z "$SESSION" ]; then
      # Open interactive resume picker
      echo "Opening interactive session picker..."
      exec claude --resume
    else
      echo "Resuming session: $SESSION"
      exec claude --resume "$SESSION"
    fi
    ;;

  auto)
    INTERVAL="${1:-60}"
    echo "Starting auto-sync every ${INTERVAL}s (Ctrl+C to stop)..."
    echo "  Bucket: $BUCKET"
    echo "  Instance: $ME"
    while true; do
      # Silent push
      for P in "${SYNC_PATHS[@]}"; do
        [ -d "$CLAUDE_DIR/$P" ] && \
          aws s3 sync "$CLAUDE_DIR/$P/" "$S3_ROOT/claude-state/$P/" \
            --region "$REGION" --quiet --sse AES256 2>/dev/null || true
      done
      [ -f "$CLAUDE_DIR/history.jsonl" ] && \
        aws s3 cp "$CLAUDE_DIR/history.jsonl" "$S3_ROOT/claude-state/history.jsonl" \
          --region "$REGION" --quiet --sse AES256 2>/dev/null || true
      [ -d "$DATA_DIR/sessions" ] && \
        aws s3 sync "$DATA_DIR/sessions/" "$S3_ROOT/session-logs/" \
          --region "$REGION" --quiet --sse AES256 2>/dev/null || true
      echo "{\"instance\": \"$ME\", \"synced\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" | \
        aws s3 cp - "$S3_ROOT/claude-state/.last-sync.json" --region "$REGION" --quiet --sse AES256 2>/dev/null || true
      sleep "$INTERVAL"
    done
    ;;

  help|*)
    cat <<'EOF'
state-sync -- Persistent conversation state across ephemeral EC2 instances

Commands:
  state-sync setup                 Create encrypted S3 bucket (one-time)
  state-sync pull                  Pull all conversation state from S3
  state-sync push                  Push current state to S3
  state-sync list                  List conversations stored in S3
  state-sync resume <session-id>   Show how to resume a conversation
  state-sync auto [interval]       Background auto-sync (default: 60s)

Architecture:
  S3 is the permanent store. EC2 instances are ephemeral.
  - On startup: state-sync pull (get previous conversations)
  - While running: state-sync auto (continuous backup)
  - To resume: spin up any instance, pull, claude --resume

Encryption:
  - At rest: AES-256 (SSE-S3) on every object
  - In transit: TLS (HTTPS) -- S3 default
  - Versioning: enabled (30-day retention for old versions)

Environment:
  CLAUDE_PORTABLE_STATE_BUCKET    Override bucket name
  AWS_DEFAULT_REGION              Override region (default: us-east-2)
EOF
    ;;
esac
