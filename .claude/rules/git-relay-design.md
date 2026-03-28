# Git Relay Design (RONE ↔ CCC)

RONE and CCC communicate via files in a shared git repo (not HTTP APIs).

Repo: `joel-ginsberg_tmemu/ccc-rone-bridge` (PRIVATE, tmemu)
Both RONE and CCC environments have tmemu GitHub tokens for push/pull access.
Relay files contain real Teams chat messages (unsanitized) — workers need
actual context to produce useful responses.

## Data flow

- RONE caches ALL messages locally on PVC (never leaves RONE)
- RONE classifies each message: RELAY / REPLY / IGNORE
- ONLY messages classified as RELAY get written to the relay git repo
- Relay files include the message + last 25 messages as conversation context
- Regular chat (IGNORE/REPLY) stays on RONE PVC, never touches git

## Relay repo structure

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

## Poll cycle

- RONE poller: classifies messages, git push RELAY requests to pending/
- git-dispatch.py: git pull every 30s, sees pending/, dispatches, moves to dispatched/
- Worker: writes result, dispatcher moves to completed/
- RONE poller: git pull every 30s, sees completed/, posts result to Teams

## Security

- Relay repo: joel-ginsberg_tmemu/ccc-rone-bridge (PRIVATE)
- In transit: HTTPS (git push/pull)
- At rest: GitHub's default encryption
- Messages are NOT sanitized — workers see real chat for context
