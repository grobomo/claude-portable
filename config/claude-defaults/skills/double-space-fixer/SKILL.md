---



name: double-space-fixer
description: Fix double-space text expansion issues from mobile typing
keywords:
  - typing
  - iphone
  - expander
  - keyboard
  - period
  - double-space
  - text


---

# Double-Space Fixer

iPhone-style text expander: converts "  " (double-space) to ". " (period-space).

## Quick Install

```bash
cd "/workspace\double-space-fixer\python"
pip install pynput
python main.py
```

## Auto-Start (Windows)

```bash
# Copy startup script to Windows startup folder
cp startup.pyw "$APPDATA/Microsoft/Windows/Start Menu/Programs/Startup/double-space-fixer.pyw"
```

## Manage Running Instance

```bash
# Check if running
wmic process where "name='pythonw.exe'" get ProcessId,CommandLine | grep main.py

# Restart (kill old + start new)
PID=$(wmic process where "name='pythonw.exe'" get ProcessId,CommandLine 2>/dev/null | grep main.py | awk '{print $NF}')
[ -n "$PID" ] && taskkill //PID $PID //F
cd "/workspace\double-space-fixer\python"
pythonw main.py &
```

## How It Works

- Listens for keyboard events via pynput
- Tracks timestamp of last space press
- If second space within 500ms: sends `backspace backspace . space`
- Non-space keys reset the timestamp

## Configuration

Edit `python/main.py`:

```python
DEBUG = True                    # Print debug output (set False for silent)
DOUBLE_SPACE_WINDOW_MS = 500    # Max ms between spaces (increase if too sensitive)
```

## Files

```
ProjectsCL1/double-space-fixer/python/
+-- main.py              # Main fixer (timestamp-based)
+-- main_interception.py # Low-level driver version
+-- tray_monitor.py      # System tray process monitor
+-- startup.pyw          # Windows startup launcher
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Not triggering | Check process is running |
| Triggers on single space | Update to latest (timestamp-based) |
| Too slow | Try `main_interception.py` (requires driver) |
