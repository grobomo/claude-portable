# Teams Poller — Now a Separate Project

The RONE Teams poller has its own project: `rone-teams-poller` (joel-ginsberg_tmemu/rone-teams-poller).

## Quick access from here
```bash
python C:/Users/joelg/Documents/ProjectsCL1/rone-teams-poller/scripts/read_latest.py --hours 24
python C:/Users/joelg/Documents/ProjectsCL1/rone-teams-poller/scripts/read_latest.py --all
```

## Kubeconfig
Both this project and rone-teams-poller share the same kubeconfig (same RONE namespace).
Download from: RONE portal -> org 216 -> hackathon-teams-poller -> Actions -> Download kubeconfig (8h)
Save to: `config/*.kubeconfig` in either project (gitignored in both).
