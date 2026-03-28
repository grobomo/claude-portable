# TDD Pipeline Area

## What it does
Enforces a multi-stage test-driven development workflow for each task a worker picks up. Quality over speed — scale out workers for parallelism.

## Key files
- `scripts/continuous-claude.sh` — worker task runner: claims tasks, runs pipeline stages, opens PRs
- `tests/test_fleet_monitor.py` — fleet monitor unit tests
- `tests/test_leader_election.py` — leader election unit tests

## Architecture
Each task runs through sequential stages, each a separate `claude -p` invocation:
1. RESEARCH — WebSearch + read existing code
2. PLAN — what to change, what tests to write
3. TESTS FIRST — write failing tests, commit
4. IMPLEMENT — write code until tests pass
5. VERIFY — full test suite + lint + secret scan
6. PR — push, create PR, merge

Gates between stages validate output before proceeding. If a stage fails, retry that stage (not the whole pipeline).

## Gotchas
- Each stage is a separate claude -p invocation with prior stage output as context
- Test framework auto-detected from package.json/pyproject.toml/Makefile
- Stage logs written to /data/task-{N}-stages.json
- Workers must be on main branch before starting each task
- All scripts must use LF line endings (not CRLF)
