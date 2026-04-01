# Fleet Node Tuning System

## Goal
Build a fleet node tuning system that reads dispatcher /health, calculates optimal node counts via tunable ratios, and outputs scaling recommendations. Add a /fleet-tune dashboard endpoint with color-coded current vs desired state.

## Success Criteria
1. `scripts/fleet/fleet-tune.sh` reads /health API and outputs scaling recommendations
2. `scripts/fleet/tune-config.json` contains editable tuning parameters
3. Tuning formula: workers = max(pending_tasks * 2, 10), monitors = max(workers / 20, 1), dispatchers = 1
4. Script compares actual vs desired counts and outputs add/remove N recommendations
5. `/fleet-tune` endpoint on central-server.js shows current vs desired with color coding (green=matched, yellow=drift, red=critical)
6. All components tested and working

## Tasks
1. Create `scripts/fleet/tune-config.json` with tunable params
2. Create `scripts/fleet/fleet-tune.sh` -- reads /health, calculates, compares, recommends
3. Create `monitoring-dashboard/central-server.js` with /fleet-tune endpoint
4. Test all components
