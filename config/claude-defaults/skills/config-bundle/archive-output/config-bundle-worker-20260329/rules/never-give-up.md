# Never Give Up -- Research First

When something "can't be done" or a tool doesn't work:

1. **WebSearch** for alternatives before declaring it impossible
2. Try at least 3 different approaches
3. Check if there's an Azure/AWS/API feature you didn't know about
4. Only THEN report a blocker -- with what you tried and what you found

Examples of past "impossible" things that were solved by research:
- "Can't screenshot a VM without RDP" → Azure Boot Diagnostics (hypervisor-level screenshots, no login needed)
- "Can't run commands while run-command is locked" → Boot diagnostics, serial console, or SSM (AWS)
- "Can't send email without Graph token" → Renew GPDH secret, or use SMTP relay skill
