# Messaging Safety — HARD RULES

## NEVER send messages to anyone without EXPLICIT permission

- **NEVER** send Teams messages to any person or chat unless the user explicitly says to
- **NEVER** send emails to anyone unless the user explicitly says to
- **NEVER** create meeting invites for anyone unless the user explicitly says to
- **The hackathon team chat "Smells Like Machine Learning" is the ONLY exception** — the user granted permission for that specific chat for hackathon-related messages
- **Even for the hackathon chat:** NEVER send test messages. Only send real operational messages (task acknowledgments, status updates)
- **Testing:** Test message formatting locally (print to console, validate JSON). NEVER send test messages to any real chat or person.
- If you need to test sending, ASK the user which chat to use. Do not guess.
- If a send fails, STOP. Do not try alternative recipients.

## Authorized messaging targets (explicit permission granted)
- Teams chat: "Smells Like Machine Learning" (19:cf504fc638964747bff028e4ba785869@thread.v2) — hackathon operational messages only
- No other chats, no 1:1 messages, no emails, no meeting invites unless explicitly told
