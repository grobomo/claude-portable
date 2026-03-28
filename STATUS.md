# Claude Portable — Status as of 2026-03-28 22:00 ET

## What works right now

| Component | Status | Location |
|-----------|--------|----------|
| CCC launcher | Working | Local laptop, `ccc` command |
| Worker auto-start | Working | Workers auto-enable continuous-claude from config |
| Task claiming | Working | Branch-based, no duplicate work across workers |
| Worker-1 | Running | 18.219.224.145, continuous-claude active |
| Workers 2-4 | Running | Auto-started, picking up tasks |
| Worker-5 | Stopped | Stopped to make room for dispatcher |
| 50+ PRs merged | Done | grobomo/claude-portable |
| RONE poller | Running | K8s deployment, polls Teams every 5s, caches messages |
| RONE secrets | Set up | graph-token, relay-api-key in K8s |
| AWS relay API | Code pushed | POST /relay, GET /result/{id}, GET /board endpoints |
| Dispatcher | Launching | Building from base AMI right now |

## What's in progress

1. **Dispatcher deployment** — launching now, will have relay API on port 8080
2. **RONE → AWS wiring** — need to set DISPATCHER_URL configmap on RONE pointing to dispatcher IP
3. **End-to-end test** — @claude in Teams → RONE classifies → relays to AWS → worker → result → Teams

## What's NOT done yet

### Critical (blocks end-to-end)
- [ ] Dispatcher needs fresh Graph token from Secrets Manager with refresh flow
- [ ] RONE `poller-config` configmap with dispatcher URL not created yet
- [ ] RONE deployment needs rollout restart after configmap update
- [ ] Security group: dispatcher port 8080 must be open for RONE outbound

### Important (quality of life)
- [ ] Claude API key for RONE message classification (currently keyword fallback)
- [ ] Conversation context: per-user buffers, group context files
- [ ] Quoted reply detection (PR #26 merged but not tested in RONE flow)
- [ ] Task template enforcement (CI checker)
- [ ] Chatbot auto-fills task template from conversation
- [ ] TDD pipeline with enforcement gates
- [ ] Neural pipeline integration for worker phase tracking
- [ ] WHY phase in worker pipeline
- [ ] Worker pushback flow for blocked tasks
- [ ] Reviewer Claude at each gate
- [ ] Pipeline audit trail committed to PR branches
- [ ] `ccc work` command
- [ ] `ccc board` command
- [ ] Dispatcher self-update mechanism
- [ ] Backup dispatcher with leader election

### Nice to have
- [ ] Build AMI for faster launches (currently ~5 min from base)
- [ ] HTTPS for dispatcher API (currently HTTP)
- [ ] Fleet auto-scaling from dispatcher
- [ ] Worker idle self-report + scale-down
- [ ] Daily digest posted to Teams
- [ ] DR test automation
