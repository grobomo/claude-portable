# Dispatcher Architecture

- Workers built `git-dispatch.py` (watches TODO.md via git). I built relay API on `teams-dispatch.py`.
- These need to be merged. The relay API endpoints (/relay, /result, /board) should be added to whatever script the dispatcher daemon actually runs.
- Check `dispatcher-daemon.sh` entrypoint to see which script it starts.
- Dispatcher needs the repo cloned at `/workspace/claude-portable` on boot.
