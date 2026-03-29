---



name: open-notepad
description: Opens files in Notepad++ text editor. Use when user asks to open, view, show, or edit a file in an editor, notepad, npp, or text editor.
triggers:
  - open in notepad
  - open in editor
  - show in notepad
  - open npp
  - view in editor
  - edit in notepad
keywords:
  - notepad
  - editor
  - npp


---

# Open File in Notepad++

When the user asks to open a file in Notepad++, an editor, or npp, run this bash command:

```bash
"/c/Program Files/Notepad++/notepad++.exe" "<filepath>" &
```

Replace `<filepath>` with the actual file path. Use the full path when possible.

## Example triggers

- "open it in notepad"
- "show me in editor"
- "open this file npp"
- "view in notepad++"
- "edit in text editor"

## Notes

- Always run in background with `&` so Claude continues
- Use the most recently discussed file if user says "it" or "this"
- Prefer absolute paths over relative paths
