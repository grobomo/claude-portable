# Tasks: Spec Kit + GSD Integration

## Task 1: Add uv + Spec Kit to Dockerfile
- [ ] Add `uv` install to `claude-portable/Dockerfile`
- [ ] Add `specify-cli` install via uv
- [ ] Verify PATH includes uv tools bin
- [ ] Test: `docker build` succeeds, `specify --help` works inside container

## Task 2: Create GSD Hook Bundle
- [ ] Create `claude-portable/gsd/gsd-gate.js` (adapt from Windows version for Linux)
- [ ] Create `claude-portable/gsd/gsd-config.json` (default planning config)
- [ ] Add GSD hook registration to worker settings.json template
- [ ] Test: hook blocks `Bash` when no PLAN.md exists, allows after PLAN.md created

## Task 3: Build Spec Generator Script
- [ ] Create `claude-portable/scripts/spec-generate.sh`
- [ ] Extract speckit prompt templates into reusable text files
- [ ] Implement 3-step pipeline: specify -> plan -> tasks
- [ ] Add timeout (5 min) and fallback to raw dispatch
- [ ] Test: given raw task text, produces valid .specs/ directory

## Task 4: Integrate Spec Generation into Dispatcher
- [ ] Modify `git-dispatch.py` `dispatch_task()` to call spec-generate.sh
- [ ] Add SCP of .specs/ to worker before claude session
- [ ] Modify worker prompt template to reference spec
- [ ] Add fallback: if spec generation fails, dispatch raw task (don't block)
- [ ] Test: end-to-end bridge task -> spec -> worker dispatch

## Task 5: Update Worker CLAUDE.md Template
- [ ] Add spec-driven workflow instructions to `config/CLAUDE-worker.md`
- [ ] Document GSD enforcement expectations
- [ ] Include spec reading instructions

## Task 6: Deploy and Test
- [ ] Build updated Docker image
- [ ] Deploy to dispatcher + workers
- [ ] Submit test task via bridge
- [ ] Verify: spec generated, worker creates PLAN.md, PR follows spec criteria
