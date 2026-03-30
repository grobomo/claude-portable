#!/usr/bin/env bash
# ccc-client.sh -- CLI client for the CCC dispatcher API.
#
# Commands:
#   submit <description>   Submit a new task
#   status <task-id>       Check task status
#   poll <task-id>         Block until task completes (or fails/cancels)
#   cancel <task-id>       Cancel a pending/running task
#   workers                Show fleet worker status
#   tasks [state]          List tasks, optionally filtered by state
#
# Environment:
#   CCC_API_URL    Base URL (default: https://16.58.49.156)
#   CCC_API_TOKEN  Bearer token for auth (optional)
#   CCC_POLL_INTERVAL  Seconds between polls (default: 5)
#   CCC_POLL_TIMEOUT   Max seconds to wait (default: 300)

set -euo pipefail

CCC_API_URL="${CCC_API_URL:-https://16.58.49.156}"
CCC_API_TOKEN="${CCC_API_TOKEN:-}"
CCC_POLL_INTERVAL="${CCC_POLL_INTERVAL:-5}"
CCC_POLL_TIMEOUT="${CCC_POLL_TIMEOUT:-300}"

# Strip trailing slash
CCC_API_URL="${CCC_API_URL%/}"

# ── Helpers ────────────────────────────────────────────────────────────────────

die() { echo "error: $*" >&2; exit 1; }

check_deps() {
    command -v curl >/dev/null 2>&1 || die "curl is required"
    command -v jq >/dev/null 2>&1 || die "jq is required (apt install jq)"
}

# Build base curl args into CURL_BASE array (call once at startup)
build_curl_base() {
    CURL_BASE=(-s -S --connect-timeout 10 --max-time 30 -k)
    if [[ -n "$CCC_API_TOKEN" ]]; then
        CURL_BASE+=(-H "Authorization: Bearer $CCC_API_TOKEN")
    fi
    CURL_BASE+=(-H "Content-Type: application/json")
}

# ── Commands ───────────────────────────────────────────────────────────────────

cmd_submit() {
    local description="$1"
    [[ -z "$description" ]] && die "usage: ccc-client.sh submit <description>"

    local payload
    payload=$(jq -n --arg text "$description" '{"text": $text}')

    local resp http_code body
    resp=$(curl "${CURL_BASE[@]}" \
        -X POST -d "$payload" \
        -w "\n%{http_code}" \
        "${CCC_API_URL}/task" 2>&1) || true

    http_code=$(echo "$resp" | tail -1)
    body=$(echo "$resp" | sed '$d')

    case "$http_code" in
        201)
            local task_id state
            task_id=$(echo "$body" | jq -r '.id')
            state=$(echo "$body" | jq -r '.state')
            echo "Task submitted: $task_id"
            echo "  State: $state"
            echo "  Text:  $description"
            ;;
        401) die "unauthorized -- check CCC_API_TOKEN" ;;
        000) die "connection failed -- is dispatcher running at $CCC_API_URL?" ;;
        *)   die "submit failed (HTTP $http_code): $(echo "$body" | head -1)" ;;
    esac
}

cmd_status() {
    local task_id="$1"
    [[ -z "$task_id" ]] && die "usage: ccc-client.sh status <task-id>"

    local resp http_code body
    resp=$(curl "${CURL_BASE[@]}" \
        -w "\n%{http_code}" \
        "${CCC_API_URL}/task/${task_id}" 2>&1) || true

    http_code=$(echo "$resp" | tail -1)
    body=$(echo "$resp" | sed '$d')

    case "$http_code" in
        200)
            echo "$body" | jq -r '
                "Task \(.id):",
                "  State:      \(.state)",
                "  Text:       \(.text // "-")",
                (if .priority then "  Priority:   \(.priority)" else empty end),
                (if .dispatched_at then "  Dispatched: \(.dispatched_at)" else empty end),
                (if .completed_at then "  Completed:  \(.completed_at)" else empty end),
                (if .result then "  Result:     \(.result)" else empty end),
                (if .error then "  Error:      \(.error)" else empty end)
            '
            ;;
        401) die "unauthorized -- check CCC_API_TOKEN" ;;
        404) die "task $task_id not found" ;;
        000) die "connection failed -- is dispatcher running at $CCC_API_URL?" ;;
        *)   die "status check failed (HTTP $http_code)" ;;
    esac
}

cmd_poll() {
    local task_id="$1"
    [[ -z "$task_id" ]] && die "usage: ccc-client.sh poll <task-id>"

    local deadline state body http_code resp
    deadline=$((SECONDS + CCC_POLL_TIMEOUT))

    echo "Polling task $task_id (timeout: ${CCC_POLL_TIMEOUT}s, interval: ${CCC_POLL_INTERVAL}s)..."

    state="unknown"
    while [[ $SECONDS -lt $deadline ]]; do
        resp=$(curl "${CURL_BASE[@]}" \
            -w "\n%{http_code}" \
            "${CCC_API_URL}/task/${task_id}" 2>/dev/null) || true

        http_code=$(echo "$resp" | tail -1)
        body=$(echo "$resp" | sed '$d')

        if [[ "$http_code" == "401" ]]; then
            die "unauthorized -- check CCC_API_TOKEN"
        fi
        if [[ "$http_code" == "000" ]]; then
            die "connection failed -- is dispatcher running at $CCC_API_URL?"
        fi
        if [[ "$http_code" != "200" ]]; then
            die "status check failed (HTTP $http_code)"
        fi

        state=$(echo "$body" | jq -r '.state')
        local elapsed=$((SECONDS))
        printf "  [%3ds] state=%s" "$elapsed" "$state"

        local progress
        progress=$(echo "$body" | jq -r '.progress // empty')
        if [[ -n "$progress" ]]; then
            printf "  progress=%s" "$progress"
        fi
        printf "\n"

        case "$state" in
            COMPLETED)
                echo ""
                echo "Task completed."
                echo "$body" | jq -r '
                    "  Result: \(.result // "-")",
                    (if .completed_at then "  Completed: \(.completed_at)" else empty end)
                '
                exit 0
                ;;
            FAILED)
                echo ""
                echo "Task failed."
                echo "$body" | jq -r '
                    "  Error: \(.error // "-")",
                    (if .completed_at then "  Failed at: \(.completed_at)" else empty end)
                '
                exit 1
                ;;
            CANCELLED)
                echo ""
                echo "Task was cancelled."
                exit 1
                ;;
        esac

        sleep "$CCC_POLL_INTERVAL"
    done

    echo ""
    die "timed out after ${CCC_POLL_TIMEOUT}s (last state: $state)"
}

cmd_cancel() {
    local task_id="$1"
    [[ -z "$task_id" ]] && die "usage: ccc-client.sh cancel <task-id>"

    local resp http_code body
    resp=$(curl "${CURL_BASE[@]}" \
        -X DELETE \
        -w "\n%{http_code}" \
        "${CCC_API_URL}/task/${task_id}" 2>&1) || true

    http_code=$(echo "$resp" | tail -1)
    body=$(echo "$resp" | sed '$d')

    case "$http_code" in
        200)
            echo "Task $task_id cancelled."
            ;;
        401) die "unauthorized -- check CCC_API_TOKEN" ;;
        404) die "task $task_id not found" ;;
        409) die "cannot cancel: $(echo "$body" | jq -r '.error // "task in terminal state"')" ;;
        000) die "connection failed -- is dispatcher running at $CCC_API_URL?" ;;
        *)   die "cancel failed (HTTP $http_code)" ;;
    esac
}

cmd_workers() {
    local body
    body=$(curl "${CURL_BASE[@]}" "${CCC_API_URL}/api/workers" 2>&1) || true

    if [[ -z "$body" ]] || [[ "$body" == "null" ]] || ! echo "$body" | jq empty 2>/dev/null; then
        die "connection failed -- is dispatcher running at $CCC_API_URL?"
    fi

    local count
    count=$(echo "$body" | jq 'length')

    if [[ "$count" == "0" ]]; then
        echo "No workers registered."
        return
    fi

    printf "%-20s %-10s %-8s %-8s %-22s %s\n" \
        "WORKER" "STATUS" "DONE" "FAILED" "REGISTERED" "CURRENT_TASK"
    printf "%s\n" "$(printf '%.0s-' {1..90})"

    echo "$body" | jq -r '
        to_entries[] |
        [
            .key,
            (.value.status // "unknown"),
            (.value.tasks_completed // 0 | tostring),
            (.value.tasks_failed // 0 | tostring),
            (.value.registered_at // "-"),
            (.value.current_task_id // "-")
        ] | @tsv
    ' | while IFS=$'\t' read -r name status done failed registered task; do
        printf "%-20s %-10s %-8s %-8s %-22s %s\n" \
            "$name" "$status" "$done" "$failed" "$registered" "$task"
    done

    echo ""
    echo "$count worker(s)"
}

cmd_tasks() {
    local state_filter="${1:-}"
    local path="/tasks"
    if [[ -n "$state_filter" ]]; then
        path="/tasks?status=${state_filter}"
    fi

    local resp http_code body
    resp=$(curl "${CURL_BASE[@]}" \
        -w "\n%{http_code}" \
        "${CCC_API_URL}${path}" 2>&1) || true

    http_code=$(echo "$resp" | tail -1)
    body=$(echo "$resp" | sed '$d')

    case "$http_code" in
        200) ;;
        401) die "unauthorized -- check CCC_API_TOKEN" ;;
        000) die "connection failed -- is dispatcher running at $CCC_API_URL?" ;;
        *)   die "list failed (HTTP $http_code)" ;;
    esac

    local count
    count=$(echo "$body" | jq '.count')

    if [[ "$count" == "0" ]]; then
        local label=""
        [[ -n "$state_filter" ]] && label=" with state=$state_filter"
        echo "No tasks found${label}."
        return
    fi

    printf "%-38s %-12s %-22s %s\n" "ID" "STATE" "CREATED" "TEXT"
    printf "%s\n" "$(printf '%.0s-' {1..100})"

    echo "$body" | jq -r '
        .tasks[] |
        [
            .id,
            (.state // "unknown"),
            (.created_at // "-"),
            (.text // "-")[:40]
        ] | @tsv
    ' | while IFS=$'\t' read -r id state created text; do
        printf "%-38s %-12s %-22s %s\n" "$id" "$state" "$created" "$text"
    done

    echo ""
    echo "$count task(s)"
}

# ── Usage ──────────────────────────────────────────────────────────────────────

usage() {
    cat <<'USAGE'
ccc-client.sh -- CLI client for the CCC dispatcher API

Usage:
    ccc-client.sh submit <description>     Submit a new task
    ccc-client.sh status <task-id>         Check task status
    ccc-client.sh poll <task-id>           Block until task completes
    ccc-client.sh cancel <task-id>         Cancel a task
    ccc-client.sh workers                  Show fleet workers
    ccc-client.sh tasks [state]            List tasks (optional: pending/running/completed/failed)

Environment:
    CCC_API_URL         API base URL (default: https://16.58.49.156)
    CCC_API_TOKEN       Bearer token for auth
    CCC_POLL_INTERVAL   Poll interval in seconds (default: 5)
    CCC_POLL_TIMEOUT    Poll timeout in seconds (default: 300)
USAGE
    exit 1
}

# ── Main ───────────────────────────────────────────────────────────────────────

main() {
    check_deps
    build_curl_base

    local cmd="${1:-}"
    shift || true

    case "$cmd" in
        submit)  cmd_submit "${1:-}" ;;
        status)  cmd_status "${1:-}" ;;
        poll)    cmd_poll "${1:-}" ;;
        cancel)  cmd_cancel "${1:-}" ;;
        workers) cmd_workers ;;
        tasks)   cmd_tasks "${1:-}" ;;
        help|-h|--help) usage ;;
        *)       usage ;;
    esac
}

# Global array for curl options (populated by build_curl_base)
declare -a CURL_BASE

main "$@"
