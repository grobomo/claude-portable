# Teams Integration Area

## What it does
Bridges Microsoft Teams chat with the CCC fleet. Users send @claude in Teams, RONE classifies and relays to CCC, workers process, results posted back.

## Key files
- `scripts/teams-chat-bridge.py` — chatbot-side Teams polling (moved from dispatcher)
- `scripts/teams-dispatch.py` — legacy Teams dispatcher (superseded by git relay)
- `scripts/chatbot-daemon.sh` — container entrypoint for chatbot role
- `scripts/web-chat.js` — WebSocket server for phone/browser access
- `scripts/web-chat.html` — mobile-first chat UI
- `lambda/web-chat/` — Lambda function URL for stable HTTPS endpoint

## Architecture
- RONE (K8s) polls Teams via Graph API, classifies messages, pushes RELAY requests to git
- Dispatcher polls relay repo (ccc-rone-bridge), dispatches to workers
- Workers run claude -p, results written back to relay repo
- RONE picks up completed results, posts to Teams
- Chatbot answers questions directly; submits work as TODO items

## Gotchas
- RONE and CCC communicate via git files, NOT HTTP APIs
- Relay repo is tmemu private (contains unsanitized Teams messages)
- RONE poller runs in K8s namespace `joelg-hackathon-teams-poller`
- Graph API tokens expire in 1 hour — use refresh token flow
