#!/usr/bin/env bash
# fleet-tune.sh -- Calculate optimal fleet node counts and output scaling recommendations.
#
# Reads current fleet state from the dispatcher /health API, applies tunable
# ratios from tune-config.json, and prints add/remove recommendations.
#
# Usage:
#   ./fleet-tune.sh [--json] [--config path/to/tune-config.json]
#
# Options:
#   --json     Output machine-readable JSON instead of human-readable text
#   --config   Path to tune-config.json (default: same directory as this script)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/tune-config.json"
OUTPUT_JSON=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --json)   OUTPUT_JSON=true; shift ;;
    --config) CONFIG_FILE="$2"; shift 2 ;;
    *)        echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# ── Load config ────────────────────────────────────────────────────────────────

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "ERROR: Config file not found: $CONFIG_FILE" >&2
  exit 1
fi

worker_ratio=$(jq -r '.worker_ratio' "$CONFIG_FILE")
worker_minimum=$(jq -r '.worker_minimum' "$CONFIG_FILE")
monitor_ratio=$(jq -r '.monitor_ratio' "$CONFIG_FILE")
monitor_minimum=$(jq -r '.monitor_minimum' "$CONFIG_FILE")
dispatcher_count=$(jq -r '.dispatcher_count' "$CONFIG_FILE")
health_url=$(jq -r '.dispatcher_health_url' "$CONFIG_FILE")
drift_threshold=$(jq -r '.drift_threshold_percent' "$CONFIG_FILE")
critical_threshold=$(jq -r '.critical_threshold_percent' "$CONFIG_FILE")

# ── Fetch fleet state ─────────────────────────────────────────────────────────

health_response=$(curl -sf --connect-timeout 5 --max-time 10 "$health_url" 2>/dev/null) || {
  echo "ERROR: Cannot reach dispatcher at $health_url" >&2
  exit 1
}

pending_tasks=$(echo "$health_response" | jq -r '.pending_tasks // 0')
active_workers=$(echo "$health_response" | jq -r '.active_workers // 0')

# Count monitors and dispatchers from fleet_roster by naming convention
# Workers: names matching worker-*, Monitors: names matching monitor-*, Dispatchers: 1 (self)
actual_workers=$(echo "$health_response" | jq '[.fleet_roster // {} | keys[] | select(startswith("worker"))] | length')
actual_monitors=$(echo "$health_response" | jq '[.fleet_roster // {} | keys[] | select(startswith("monitor"))] | length')
actual_dispatchers=1  # The dispatcher answering /health is always 1

# ── Calculate desired counts ──────────────────────────────────────────────────

# workers = max(pending_tasks * worker_ratio, worker_minimum)
desired_workers=$(( pending_tasks * worker_ratio ))
if (( desired_workers < worker_minimum )); then
  desired_workers=$worker_minimum
fi

# monitors = max(desired_workers / monitor_ratio, monitor_minimum)
desired_monitors=$(( desired_workers / monitor_ratio ))
if (( desired_monitors < monitor_minimum )); then
  desired_monitors=$monitor_minimum
fi

desired_dispatchers=$dispatcher_count

# ── Calculate deltas ──────────────────────────────────────────────────────────

worker_delta=$(( desired_workers - actual_workers ))
monitor_delta=$(( desired_monitors - actual_monitors ))
dispatcher_delta=$(( desired_dispatchers - actual_dispatchers ))

# ── Determine status (green/yellow/red) per node type ─────────────────────────

status_for_delta() {
  local actual=$1 desired=$2 drift_pct=$3 critical_pct=$4
  if (( actual == desired )); then
    echo "matched"
    return
  fi
  local diff=$(( actual - desired ))
  if (( diff < 0 )); then diff=$(( -diff )); fi
  if (( desired == 0 )); then
    echo "critical"
    return
  fi
  local pct=$(( diff * 100 / desired ))
  if (( pct >= critical_pct )); then
    echo "critical"
  elif (( pct >= drift_pct )); then
    echo "drift"
  else
    echo "drift"
  fi
}

worker_status=$(status_for_delta "$actual_workers" "$desired_workers" "$drift_threshold" "$critical_threshold")
monitor_status=$(status_for_delta "$actual_monitors" "$desired_monitors" "$drift_threshold" "$critical_threshold")
dispatcher_status=$(status_for_delta "$actual_dispatchers" "$desired_dispatchers" "$drift_threshold" "$critical_threshold")

# ── Build recommendation strings ──────────────────────────────────────────────

recommend() {
  local name=$1 delta=$2
  if (( delta > 0 )); then
    echo "add $delta $name"
  elif (( delta < 0 )); then
    echo "remove $(( -delta )) $name"
  else
    echo "$name OK"
  fi
}

worker_rec=$(recommend "workers" "$worker_delta")
monitor_rec=$(recommend "monitors" "$monitor_delta")
dispatcher_rec=$(recommend "dispatchers" "$dispatcher_delta")

# ── Output ────────────────────────────────────────────────────────────────────

if $OUTPUT_JSON; then
  cat <<ENDJSON
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "fleet_state": {
    "pending_tasks": $pending_tasks,
    "active_workers": $active_workers
  },
  "actual": {
    "workers": $actual_workers,
    "monitors": $actual_monitors,
    "dispatchers": $actual_dispatchers
  },
  "desired": {
    "workers": $desired_workers,
    "monitors": $desired_monitors,
    "dispatchers": $desired_dispatchers
  },
  "delta": {
    "workers": $worker_delta,
    "monitors": $monitor_delta,
    "dispatchers": $dispatcher_delta
  },
  "status": {
    "workers": "$worker_status",
    "monitors": "$monitor_status",
    "dispatchers": "$dispatcher_status"
  },
  "recommendations": [
    "$worker_rec",
    "$monitor_rec",
    "$dispatcher_rec"
  ]
}
ENDJSON
else
  echo "=== Fleet Tuning Report ==="
  echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo ""
  echo "Fleet State:"
  echo "  Pending tasks:  $pending_tasks"
  echo "  Active workers: $active_workers"
  echo ""
  printf "%-14s %8s %8s %8s %10s\n" "Node Type" "Actual" "Desired" "Delta" "Status"
  printf "%-14s %8s %8s %8s %10s\n" "---------" "------" "-------" "-----" "------"
  printf "%-14s %8d %8d %+8d %10s\n" "Workers" "$actual_workers" "$desired_workers" "$worker_delta" "[$worker_status]"
  printf "%-14s %8d %8d %+8d %10s\n" "Monitors" "$actual_monitors" "$desired_monitors" "$monitor_delta" "[$monitor_status]"
  printf "%-14s %8d %8d %+8d %10s\n" "Dispatchers" "$actual_dispatchers" "$desired_dispatchers" "$dispatcher_delta" "[$dispatcher_status]"
  echo ""
  echo "Recommendations:"
  echo "  * $worker_rec"
  echo "  * $monitor_rec"
  echo "  * $dispatcher_rec"
fi
