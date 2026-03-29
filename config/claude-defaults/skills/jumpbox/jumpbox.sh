#!/bin/bash
# jumpbox -- manage Windows EC2 jumpbox (config-driven, no hardcoded IDs)
# Usage: jumpbox [connect|start|stop|status|password|ip|setup|list]
set -euo pipefail

CONFIG_DIR="${HOME}/.jumpbox"
# Resolve to native path for Python compatibility
NATIVE_CONFIG_DIR=$(cd "$CONFIG_DIR" 2>/dev/null && pwd -W 2>/dev/null || echo "$CONFIG_DIR")
ACTIVE_CONFIG="$CONFIG_DIR/active"

# ── Config loading ───────────────────────────────────────────────────────────

get_config_file() {
  local NAME="${1:-}"
  if [ -n "$NAME" ]; then
    echo "$CONFIG_DIR/${NAME}.json"
  elif [ -L "$ACTIVE_CONFIG" ] || [ -f "$ACTIVE_CONFIG" ]; then
    readlink -f "$ACTIVE_CONFIG" 2>/dev/null || cat "$ACTIVE_CONFIG"
  else
    # Auto-detect: use the only config, or the most recent
    local CONFIGS=("$CONFIG_DIR"/*.json)
    if [ ${#CONFIGS[@]} -eq 0 ] || [ ! -f "${CONFIGS[0]}" ]; then
      echo ""
      return
    elif [ ${#CONFIGS[@]} -eq 1 ]; then
      echo "${CONFIGS[0]}"
    else
      ls -t "$CONFIG_DIR"/*.json 2>/dev/null | head -1
    fi
  fi
}

load_config() {
  local CFG_FILE
  CFG_FILE=$(get_config_file "${1:-}")
  if [ -z "$CFG_FILE" ] || [ ! -f "$CFG_FILE" ]; then
    echo "No jumpbox configured. Run: jumpbox setup"
    exit 1
  fi
  # Resolve config path for Python (handles Git Bash /c/ vs C:\ paths)
  local PY_CFG
  PY_CFG=$(cd "$(dirname "$CFG_FILE")" && pwd -W 2>/dev/null || pwd)/$(basename "$CFG_FILE")
  eval "$(python3 -c "
import json, os
cfg = json.load(open(r'''$PY_CFG'''))
print(f'INSTANCE_ID={cfg[\"instance_id\"]}')
print(f'REGION={cfg[\"region\"]}')
kp = cfg['key_path'].replace('~', os.path.expanduser('~'))
print(f'KEY_PATH={kp}')
print(f'NAME={cfg[\"name\"]}')
")"
}

# ── AWS helpers ──────────────────────────────────────────────────────────────

get_state() {
  aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --region "$REGION" \
    --query "Reservations[0].Instances[0].State.Name" --output text 2>/dev/null
}

get_ip() {
  aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --region "$REGION" \
    --query "Reservations[0].Instances[0].PublicIpAddress" --output text 2>/dev/null
}

get_password() {
  aws ec2 get-password-data --instance-id "$INSTANCE_ID" --region "$REGION" \
    --priv-launch-key "$KEY_PATH" --query PasswordData --output text 2>/dev/null
}

ensure_running() {
  local STATE
  STATE=$(get_state)
  if [ "$STATE" = "stopped" ]; then
    echo "Starting jumpbox ($NAME)..."
    aws ec2 start-instances --instance-ids "$INSTANCE_ID" --region "$REGION" > /dev/null
    aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"
    echo "Running. Waiting for RDP..."
    local IP
    IP=$(get_ip)
    for i in $(seq 1 30); do
      if timeout 3 bash -c "echo >/dev/tcp/$IP/3389" 2>/dev/null; then
        break
      fi
      sleep 5
    done
  elif [ "$STATE" = "running" ]; then
    true
  elif [ "$STATE" = "pending" ]; then
    echo "Instance starting..."
    aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"
  else
    echo "Instance is $STATE. Cannot connect."
    exit 1
  fi
}

# ── Commands ─────────────────────────────────────────────────────────────────

cmd="${1:-connect}"
shift || true

case "$cmd" in
  setup)
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
    # Check for setup.sh next to this script, or in the skill dir
    for D in "$SCRIPT_DIR" "$HOME/.claude/skills/jumpbox"; do
      if [ -f "$D/setup.sh" ]; then
        exec bash "$D/setup.sh" "$@"
      fi
    done
    echo "setup.sh not found"
    exit 1
    ;;

  connect|rdp)
    load_config "$@"
    ensure_running
    IP=$(get_ip)
    PW=$(get_password)

    echo "Jumpbox: $IP ($NAME)"
    echo "User:    Administrator"
    echo "Pass:    $PW"

    if command -v mstsc.exe &>/dev/null; then
      # Store creds in Windows Credential Manager (must use powershell, not cmdkey from Git Bash)
      powershell.exe -Command "cmdkey /delete:TERMSRV/$IP 2>\$null; cmdkey /generic:TERMSRV/$IP /user:Administrator /pass:'$PW'" > /dev/null 2>&1

      # Trust the RDP server's self-signed cert
      CERT_FILE="${TMPDIR:-/tmp}/jumpbox-rdp-${NAME}.cer"
      timeout 5 bash -c "echo | openssl s_client -connect '$IP:3389' 2>/dev/null \
        | openssl x509 -outform DER -out '$CERT_FILE' 2>/dev/null" 2>/dev/null || true
      if [ -s "$CERT_FILE" ]; then
        certutil.exe -user -addstore "Root" "$(cygpath -w "$CERT_FILE")" > /dev/null 2>&1 || true
      fi

      # Write .rdp file
      RDP_FILE="$HOME/${NAME}.rdp"
      WIN_RDP=$(cygpath -w "$RDP_FILE" 2>/dev/null || echo "$RDP_FILE")
      cat > "$RDP_FILE" << EOF
full address:s:$IP
username:s:Administrator
prompt for credentials:i:0
authentication level:i:2
enablecredsspsupport:i:1
EOF
      mstsc.exe "$WIN_RDP" &

      # Auto-dismiss "publisher can't be identified" warning via pywinauto
      python3 -c "
import time
try:
    from pywinauto import Application
    for i in range(10):
        time.sleep(1)
        try:
            app = Application(backend='uia').connect(path='mstsc.exe', timeout=1)
            dlg = app.window(title_re='.*security warning.*', timeout=1)
            cb = dlg.child_window(title_re='.*Don.t ask.*', control_type='CheckBox')
            if not cb.get_toggle_state(): cb.toggle()
            dlg.child_window(title='Connect', control_type='Button').click()
            break
        except: pass
except ImportError:
    pass  # pywinauto not installed, user clicks manually
" &>/dev/null &
      echo ""
      echo "RDP launched."

    elif command -v open &>/dev/null && [ "$(uname)" = "Darwin" ]; then
      open "rdp://full%20address=s:$IP&username=s:Administrator" 2>/dev/null || true
      echo ""
      echo "RDP launched. Password: $PW"
    else
      echo ""
      echo "Connect: rdesktop -u Administrator -p '$PW' $IP"
    fi
    ;;

  start)
    load_config "$@"
    ensure_running
    echo "Jumpbox running ($NAME): $(get_ip)"
    ;;

  stop)
    load_config "$@"
    echo "Stopping jumpbox ($NAME)..."
    aws ec2 stop-instances --instance-ids "$INSTANCE_ID" --region "$REGION" > /dev/null
    echo "Stopped. \$0/hr until next start."
    ;;

  status)
    load_config "$@"
    STATE=$(get_state)
    echo "Name:  $NAME"
    echo "State: $STATE"
    echo "ID:    $INSTANCE_ID"
    if [ "$STATE" = "running" ]; then
      echo "IP:    $(get_ip)"
    fi
    ;;

  ip)
    load_config "$@"
    get_ip
    ;;

  password|pw)
    load_config "$@"
    get_password
    ;;

  list)
    echo "Jumpboxes:"
    for CFG in "$CONFIG_DIR"/*.json; do
      [ -f "$CFG" ] || continue
      PY_CFG=$(cd "$(dirname "$CFG")" && pwd -W 2>/dev/null || pwd)/$(basename "$CFG")
      eval "$(python3 -c "
import json
cfg = json.load(open(r'''$PY_CFG'''))
print(f'_N={cfg[\"name\"]}')
print(f'_I={cfg[\"instance_id\"]}')
print(f'_R={cfg[\"region\"]}')
")"
      S=$(aws ec2 describe-instances --instance-ids "$_I" --region "$_R" \
        --query "Reservations[0].Instances[0].State.Name" --output text 2>/dev/null || echo "unknown")
      printf "  %-15s %-22s %s\n" "$_N" "$_I" "$S"
    done
    ;;

  run)
    # Run a PowerShell command on the jumpbox via SSM
    load_config
    COMMAND="$*"
    if [ -z "$COMMAND" ]; then
      echo "Usage: jumpbox run <powershell command>"
      exit 1
    fi
    CMD_ID=$(aws ssm send-command --region "$REGION" \
      --instance-ids "$INSTANCE_ID" \
      --document-name "AWS-RunPowerShellScript" \
      --parameters "commands=[\"$COMMAND\"]" \
      --query "Command.CommandId" --output text)
    for i in $(seq 1 30); do
      S=$(aws ssm get-command-invocation --region "$REGION" \
        --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" \
        --query "Status" --output text 2>/dev/null || echo "Pending")
      if [ "$S" = "Success" ] || [ "$S" = "Failed" ]; then break; fi
      sleep 2
    done
    aws ssm get-command-invocation --region "$REGION" \
      --command-id "$CMD_ID" --instance-id "$INSTANCE_ID" \
      --query "StandardOutputContent" --output text 2>/dev/null
    ;;

  snapshot)
    load_config "$@"
    VOL_ID=$(aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" \
      --query "Reservations[0].Instances[0].BlockDeviceMappings[0].Ebs.VolumeId" --output text)
    echo "Creating snapshot of $NAME ($VOL_ID)..."
    SNAP_ID=$(aws ec2 create-snapshot --region "$REGION" \
      --volume-id "$VOL_ID" \
      --description "${NAME}-snapshot-$(date +%Y%m%d)" \
      --tag-specifications "[{\"ResourceType\":\"snapshot\",\"Tags\":[{\"Key\":\"Name\",\"Value\":\"${NAME}-snapshot\"},{\"Key\":\"Project\",\"Value\":\"jumpbox\"}]}]" \
      --query "SnapshotId" --output text)
    echo "Snapshot: $SNAP_ID (creating in background)"
    ;;

  *)
    cat << 'HELPEOF'
jumpbox -- Windows EC2 test jumpbox manager

  jumpbox              Connect (starts if stopped, auto-RDP)
  jumpbox stop         Stop instance ($0/hr)
  jumpbox start        Start instance
  jumpbox status       Show state + IP
  jumpbox ip           Print current IP
  jumpbox password     Print admin password
  jumpbox list         List all jumpboxes
  jumpbox setup        Create a new jumpbox from scratch
  jumpbox run <cmd>    Run PowerShell command via SSM
  jumpbox snapshot     Create EBS snapshot
HELPEOF
    ;;
esac
