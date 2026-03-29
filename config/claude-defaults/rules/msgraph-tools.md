# MS Graph API Tools

## Shared Token Library
All Graph API projects use `/workspace\msgraph-lib\token_manager.py`.
- Token stored at `~/.msgraph/tokens.json` (auto-refreshing)
- TrendMicro tenant, PDHUB app registration, public client (no secret)
- Scopes: Mail, Chat, Calendar, User
- If token expired: `python /workspace/msgraph-lib/token_manager.py`

## Quick Import (from any project)
```python
import sys
sys.path.insert(0, '/workspace/msgraph-lib')
from token_manager import get_token, graph_get, graph_post
```

## Available Tools

### Email (email-manager)
- `/workspace\email-manager\` — read/send/triage email
- Has its own token copy in `.tmp/` (legacy, works independently)

### Teams Chat (teams-chat)
- `python /workspace/teams-chat/teams_chat.py list --topic "keyword"`
- `python /workspace/teams-chat/teams_chat.py members <chat_id>`
- `python /workspace/teams-chat/teams_chat.py read <chat_id>`
- `python /workspace/teams-chat/teams_chat.py send <chat_id> "message"`

### Meeting Scheduler (meeting-scheduler)
- `python /workspace/meeting-scheduler/schedule.py create "Title" "2026-04-01T10:00" 30 "email1,email2"`
- `python /workspace/meeting-scheduler/schedule.py list --days 7`
- `python /workspace/meeting-scheduler/schedule.py cancel <event_id>`
