#!/bin/bash
# Claude Portable inter-instance messaging via S3
# Usage:
#   msg send <target> <message>   Send a message to another instance
#   msg inbox                     List unread messages
#   msg read <id>                 Read a specific message
#   msg history                   Show all messages (sent + received)
#   msg who                       Show your identity and known peers
set -euo pipefail

BUCKET="${CLAUDE_PORTABLE_MSG_BUCKET:-}"
REGION="${AWS_DEFAULT_REGION:-us-east-2}"

if [ -z "$BUCKET" ]; then
  # Auto-derive bucket from AWS account ID
  ACCT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")
  if [ -z "$ACCT" ]; then
    echo "ERROR: Set CLAUDE_PORTABLE_MSG_BUCKET or configure AWS credentials."
    exit 1
  fi
  BUCKET="claude-portable-msg-$ACCT"
  # Create bucket if it doesn't exist
  aws s3 ls "s3://$BUCKET" --region "$REGION" &>/dev/null || \
    aws s3 mb "s3://$BUCKET" --region "$REGION" &>/dev/null
fi
ME="${CLAUDE_PORTABLE_ID:-$(hostname)}"

cmd="${1:-help}"
shift || true

case "$cmd" in
  send)
    TARGET="${1:?Usage: msg send <target> <message>}"
    shift
    MESSAGE="$*"
    if [ -z "$MESSAGE" ]; then
      echo "Usage: msg send <target> <message>"
      exit 1
    fi
    TS=$(date -u +%Y%m%d-%H%M%S)
    ID="${TS}-$(head -c 4 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    PAYLOAD=$(cat <<ENDJSON
{
  "id": "$ID",
  "from": "$ME",
  "to": "$TARGET",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "message": $(printf '%s' "$MESSAGE" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')
}
ENDJSON
)
    echo "$PAYLOAD" | aws s3 cp - "s3://$BUCKET/$TARGET/inbox/$ID.json" --region "$REGION" --quiet
    echo "Sent to $TARGET: $MESSAGE"
    # Also save to own outbox for history
    echo "$PAYLOAD" | aws s3 cp - "s3://$BUCKET/$ME/outbox/$ID.json" --region "$REGION" --quiet
    ;;

  inbox)
    echo "=== Inbox for $ME ==="
    FILES=$(aws s3 ls "s3://$BUCKET/$ME/inbox/" --region "$REGION" 2>/dev/null | awk '{print $4}' || true)
    if [ -z "$FILES" ]; then
      echo "  No messages."
      exit 0
    fi
    for F in $FILES; do
      CONTENT=$(aws s3 cp "s3://$BUCKET/$ME/inbox/$F" - --region "$REGION" 2>/dev/null)
      FROM=$(echo "$CONTENT" | python3 -c "import json,sys; print(json.load(sys.stdin)['from'])" 2>/dev/null)
      TS=$(echo "$CONTENT" | python3 -c "import json,sys; print(json.load(sys.stdin)['timestamp'])" 2>/dev/null)
      MSG=$(echo "$CONTENT" | python3 -c "import json,sys; print(json.load(sys.stdin)['message'])" 2>/dev/null)
      ID=$(echo "$F" | sed 's/.json$//')
      echo ""
      echo "  [$TS] from $FROM"
      echo "  $MSG"
      echo "  (id: $ID)"
    done
    ;;

  read)
    ID="${1:?Usage: msg read <id>}"
    CONTENT=$(aws s3 cp "s3://$BUCKET/$ME/inbox/$ID.json" - --region "$REGION" 2>/dev/null || \
              aws s3 cp "s3://$BUCKET/$ME/outbox/$ID.json" - --region "$REGION" 2>/dev/null || \
              echo "")
    if [ -z "$CONTENT" ]; then
      echo "Message $ID not found."
      exit 1
    fi
    echo "$CONTENT" | python3 -m json.tool
    ;;

  ack)
    ID="${1:?Usage: msg ack <id>}"
    # Move from inbox to archive
    aws s3 mv "s3://$BUCKET/$ME/inbox/$ID.json" "s3://$BUCKET/$ME/archive/$ID.json" --region "$REGION" --quiet 2>/dev/null && \
      echo "Acknowledged $ID" || echo "Message $ID not found in inbox."
    ;;

  history)
    echo "=== Message History for $ME ==="
    echo ""
    echo "--- Received ---"
    for DIR in inbox archive; do
      FILES=$(aws s3 ls "s3://$BUCKET/$ME/$DIR/" --region "$REGION" 2>/dev/null | awk '{print $4}' || true)
      for F in $FILES; do
        CONTENT=$(aws s3 cp "s3://$BUCKET/$ME/$DIR/$F" - --region "$REGION" 2>/dev/null)
        FROM=$(echo "$CONTENT" | python3 -c "import json,sys; print(json.load(sys.stdin)['from'])" 2>/dev/null)
        TS=$(echo "$CONTENT" | python3 -c "import json,sys; print(json.load(sys.stdin)['timestamp'])" 2>/dev/null)
        MSG=$(echo "$CONTENT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['message'][:80])" 2>/dev/null)
        echo "  [$TS] from $FROM: $MSG"
      done
    done
    echo ""
    echo "--- Sent ---"
    FILES=$(aws s3 ls "s3://$BUCKET/$ME/outbox/" --region "$REGION" 2>/dev/null | awk '{print $4}' || true)
    for F in $FILES; do
      CONTENT=$(aws s3 cp "s3://$BUCKET/$ME/outbox/$F" - --region "$REGION" 2>/dev/null)
      TO=$(echo "$CONTENT" | python3 -c "import json,sys; print(json.load(sys.stdin)['to'])" 2>/dev/null)
      TS=$(echo "$CONTENT" | python3 -c "import json,sys; print(json.load(sys.stdin)['timestamp'])" 2>/dev/null)
      MSG=$(echo "$CONTENT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['message'][:80])" 2>/dev/null)
      echo "  [$TS] to $TO: $MSG"
    done
    ;;

  who)
    echo "I am: $ME"
    echo "Known peers:"
    aws s3 ls "s3://$BUCKET/" --region "$REGION" 2>/dev/null | awk '{print "  " $2}' | sed 's|/||' | grep -v "^  $ME$" || echo "  (none yet)"
    ;;

  help|*)
    cat <<'EOF'
msg - Inter-instance messaging for Claude Portable

Commands:
  msg send <target> <message>   Send a message to another instance
  msg inbox                     List incoming messages
  msg read <id>                 Read a specific message
  msg ack <id>                  Archive a message (mark read)
  msg history                   Show all sent + received
  msg who                       Show your ID and known peers

Environment:
  CLAUDE_PORTABLE_ID    Your instance identity (default: hostname)
EOF
    ;;
esac
