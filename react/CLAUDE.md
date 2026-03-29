# Neural Pipeline

Worker pipeline monitoring and phase enforcement system for CCC fleet.

## What This Is

The Neural Pipeline tracks each worker's task through TDD phases (WHY -> RESEARCH -> REVIEW -> PLAN -> TESTS -> IMPLEMENT -> VERIFY -> PR), enforces gates between stages, and exposes status via HTTP API. The dispatcher aggregates pipeline state from all workers into a live dashboard.

## Key Files

| File | Purpose |
|------|---------|
| `scripts/worker-pipeline.py` | Phase state tracker CLI — called by continuous-claude.sh at each transition |
| `scripts/worker-health.py` | HTTP API (port 8081) — GET /health, POST /interrupt, POST /pull, heartbeats |
| `scripts/continuous-claude.sh` | Worker task runner — runs pipeline stages, calls worker-pipeline.py |
| `tests/test_worker_pipeline.py` | Pipeline tracker unit tests |
| `tests/test_pipeline_http.py` | HTTP API tests |
| `tests/test_worker_heartbeat.py` | Heartbeat polling tests |
| `tests/test_phase_change.py` | Phase transition event tests |
| `tests/test_phase_transition.py` | Phase transition integration tests |
| `tests/test_board_aggregation.py` | Dispatcher board aggregation tests |
| `tests/test_board.py` | Board command tests |

## Architecture

```
Worker (EC2 instance)
  continuous-claude.sh
    |-- calls worker-pipeline.py at each phase transition
    |-- worker-pipeline.py writes /data/pipeline-state.json
    |-- worker-pipeline.py POSTs phase-change events to dispatcher
  worker-health.py (HTTP server, port 8081)
    |-- reads pipeline-state.json for GET /health
    |-- POSTs heartbeat with pipeline state to dispatcher every 30s
    |-- POST /interrupt sets flag, continuous-claude.sh checks it

Dispatcher
  |-- receives heartbeats from all workers
  |-- aggregates into /data/board.json
  |-- GET /board returns fleet-wide pipeline status
  |-- ccc board reads /board and renders TUI status bar
```

## Development Rules

- All pipeline code lives in the main claude-portable repo (not a separate repo)
- Tests go in `tests/` using Python unittest
- Scripts go in `scripts/`
- Run tests: `python -m pytest tests/ -v`
- All scripts must use LF line endings
- No personal paths, no secrets, no hardcoded IPs
