# Scheduler Health Check

When `scheduler.py list` or `status` shows any task in `error` or `STOPPED` state, investigate immediately. Don't move on to other work. A stopped task means something broke 3 times and the user may not know.

Check:
1. Read the error message
2. Test the command manually
3. Fix the root cause
4. Re-register if needed
5. Verify with a test run
