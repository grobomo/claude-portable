# RONE Integration

- RONE poller runs in K8s namespace `joelg-hackathon-teams-poller` (not `joelg-helper`).
- Kubeconfig scoped to that namespace only. Expires 8h.
- PVC: `teams-poller-data`. Secret: `teams-poller-graph-token`.
- Direction: RONE → AWS only. RONE polls dispatcher, never the reverse.
- Result polling: every 30s via GET /result/{id}.
- RONE configmap `poller-config` has `dispatcher-url` key.
