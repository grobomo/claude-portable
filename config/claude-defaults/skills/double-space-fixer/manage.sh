#!/bin/bash
# Double-Space Fixer Management Script

PROJECT_DIR="/home/claude\OneDrive - TrendMicro\Documents\ProjectsCL\double-space-fixer\python"

status() {
    echo "=== Double-Space Fixer Status ==="
    wmic process where "name='pythonw.exe'" get ProcessId,CommandLine 2>/dev/null | grep -E "(main\.py|ProcessId)" || echo "Not running"
}

start() {
    echo "Starting double-space fixer..."
    cd "$PROJECT_DIR"
    pythonw main.py &
    sleep 1
    status
}

stop() {
    PID=$(wmic process where "name='pythonw.exe'" get ProcessId,CommandLine 2>/dev/null | grep "main\.py" | awk '{print $NF}')
    if [ -n "$PID" ]; then
        echo "Stopping PID $PID..."
        taskkill //PID $PID //F
    else
        echo "Not running"
    fi
}

restart() {
    stop
    sleep 1
    start
}

case "${1:-status}" in
    start)   start ;;
    stop)    stop ;;
    restart) restart ;;
    status)  status ;;
    *)       echo "Usage: $0 {start|stop|restart|status}" ;;
esac
