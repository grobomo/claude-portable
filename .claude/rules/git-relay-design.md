# Git Relay Design (RONE ↔ CCC)

RONE and CCC communicate via files in a shared git repo (not HTTP APIs).

Repo: `joel-ginsberg_tmemu/claude-relay` (private, tmemu)

```
requests/
  pending/    # RONE writes here
    {id}.json  → {sender, text, context[], timestamp, chat_id}
  dispatched/ # dispatcher moves here when worker picks up
    {id}.json  → adds {worker, dispatched_at}
  completed/  # worker moves here when done
    {id}.json  → adds {result, completed_at, pr_url}
  failed/     # on error
    {id}.json  → adds {error}
```

- RONE poller: git push to pending/
- git-dispatch.py: git pull, sees pending/, dispatches, moves to dispatched/
- Worker: writes result, moves to completed/
- RONE poller: git pull, sees completed/, posts to Teams
- Both sides poll git every 30s
