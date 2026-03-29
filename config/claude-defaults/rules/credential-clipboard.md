# Credential Manager: Clipboard Contamination Risk

The `method=clipboard` store mode reads from the OS clipboard. If ANY other process writes to the clipboard between the user copying the secret and the store operation, the wrong value gets saved silently. This has caused corrupted GPDH secrets (clipboard contained Claude Code output instead of the actual secret).

Mitigation: after storing via clipboard, always verify the stored value is plausible (correct length, no newlines, no prose text). For API secrets, test the credential immediately after storing.
