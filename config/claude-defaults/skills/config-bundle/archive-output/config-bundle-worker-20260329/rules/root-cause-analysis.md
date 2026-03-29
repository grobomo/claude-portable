# Root Cause Analysis -- Always

When something breaks or loops or behaves unexpectedly:

1. **Find the root cause** -- don't just merge/close/retry/workaround
2. **Fix the root cause** -- change the code/config/prompt that caused it
3. **Add a safety net only AFTER fixing the root cause** -- defensive checks are OK as a second layer, not as a substitute

Examples:
- PR loop: Root cause = LLM skipping merge step → Fix the prompt to make merge mandatory. Safety net = loop merges leftovers.
- Script fails: Root cause = wrong variable → Fix the variable. Don't catch the error and retry.
- API returns wrong data: Root cause = wrong endpoint → Fix the endpoint. Don't filter bad results.
