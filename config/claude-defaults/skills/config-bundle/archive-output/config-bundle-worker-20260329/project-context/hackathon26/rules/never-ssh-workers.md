# NEVER SSH to Workers

- NEVER use SSH or `docker exec` on CCC workers unless explicitly in maintenance mode
- ALL interaction goes through relay-submit.py — diagnostics, tests, config changes, everything
- SSH disrupts running Claude sessions, bypasses task tracking, can corrupt in-progress work
- Only exception: user explicitly says "SSH to the worker" or worker is in maintenance mode
