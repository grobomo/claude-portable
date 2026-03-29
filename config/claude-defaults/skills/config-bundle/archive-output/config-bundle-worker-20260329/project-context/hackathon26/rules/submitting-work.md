# Submitting Work to CCC Fleet

Use the bridge client library. NEVER ad-hoc git commands against the bridge repo.

```bash
# Submit a task
python C:/Users/joelg/Documents/ProjectsCL1/rone-boothapp-bridge/bridge.py submit "build the click tracker"

# Check all states / wait for task / find by ID
python C:/Users/joelg/Documents/ProjectsCL1/rone-boothapp-bridge/bridge.py status
python C:/Users/joelg/Documents/ProjectsCL1/rone-boothapp-bridge/bridge.py wait <ID> --timeout 300
python C:/Users/joelg/Documents/ProjectsCL1/rone-boothapp-bridge/bridge.py find <ID>
```
