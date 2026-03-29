# Development Workflow

All feature dev happens on CCC workers in AWS, not this laptop.

1. Submit work via relay repo (`scripts/relay-submit.py` or manual git push)
2. Dispatcher assigns to idle worker
3. Worker branches, codes, PRs against `altarr/boothapp`
4. Check `rone-boothapp-bridge/requests/completed/` for results

See also: `submitting-work.md`, `relay-request-format.md`, `no-local-feature-code.md`
