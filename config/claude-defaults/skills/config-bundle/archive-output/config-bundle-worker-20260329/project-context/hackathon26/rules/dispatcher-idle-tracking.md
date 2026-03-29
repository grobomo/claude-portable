# Dispatcher Worker Idle Tracking Bug

- Dispatcher marks workers busy when dispatching but doesn't always mark them idle after completion
- Symptom: no idle worker available even when all workers are idle
- Workaround: re-register workers with POST /worker/register to reset their state
- Root cause: SSH check matches persistent web-chat.js process, making workers appear busy
- Fix needed in claude-portable/scripts/git-dispatch.py: refine the idle check
