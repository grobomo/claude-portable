# Relay Request JSON Format

File goes in `rone-boothapp-bridge/requests/pending/{timestamp}-{hex}.json`:

```json
{
  "sender": "Joel Ginsberg (local)",
  "text": "the task description for the worker",
  "context": [],
  "timestamp": "2026-03-28T18:00:00Z",
  "chat_id": "local"
}
```

Dispatcher reads `sender`, `text`, `context` (last 25 messages). Worker gets `claude -p` with the prompt.
