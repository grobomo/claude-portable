# Plan: Booth Welcome Page

## Technical Approach

### 1. Create `web/booth-welcome.html` (new file)

Single-page static HTML with inline CSS and JS. No build tools, no external dependencies except Google Fonts (Inter).

**Layout (top to bottom, centered):**

| Element | Implementation |
|---------|---------------|
| Company logo | 120x120 rounded div with gradient background, "LOGO" text placeholder |
| Header | `<h1>` at 3.5rem: "Welcome to **BoothApp** Demo", subtitle below |
| Recording indicator | Status card with pulsing red dot (CSS `@keyframes pulse`), text toggles WAITING / RECORDING |
| Session info | Visitor name + elapsed timer, shown only when active |
| QR code | 200x200 dashed-border placeholder div, caption "Scan for follow-up link" |
| Footer | Small muted text |

**Design tokens:**
- Background: `#0d1117` (GitHub dark)
- Text: `#e6edf3`
- Accent: `#58a6ff` (blue), `#f85149` (recording red), `#d29922` (warning amber)
- Card bg: `#161b22`, border: `#30363d`
- Font: Inter 400/600/700, fallback system stack
- All text >= 1.4rem for 3-foot readability; header at 3.5rem

**S3 Polling (JS):**
- Import constants from `infra/config.js` via inline values (pure HTML, no module bundler)
- Hardcode `SESSION_BUCKET` and `AWS_REGION` from config.js with a comment noting the source
- Build S3 URL: `https://{BUCKET}.s3.{REGION}.amazonaws.com/active-session.json`
- `fetch()` every 3 seconds with CORS mode
- States: `idle` (404/403 = no session), `active` (200 + `data.active === true`), `error` (network failure)
- On active: show visitor name from `data.visitor_name`, start elapsed timer from `data.started_at`
- On idle: reset to "WAITING FOR SESSION"
- On error: amber indicator + "CONNECTION ERROR"

**S3 `active-session.json` expected schema:**
```json
{
  "active": true,
  "visitor_name": "Jane Doe",
  "started_at": "2026-08-05T14:32:00Z",
  "session_id": "A726594"
}
```

This file must be publicly readable (S3 bucket policy or pre-signed URL). The welcome page is read-only -- it never writes to S3.

### 2. S3 CORS Configuration (prerequisite)

The S3 bucket `boothapp-sessions-752266476357` needs a CORS rule allowing GET from `file://` and `http://localhost`:

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["GET"],
    "AllowedOrigins": ["*"],
    "ExposeHeaders": [],
    "MaxAgeSeconds": 300
  }
]
```

This is infra config, not part of the HTML file. Document in the PR description.

### 3. No modifications to `infra/config.js`

The config file uses CommonJS (`module.exports`). A plain HTML page cannot `require()` it. Instead, the HTML file duplicates the two needed values (`SESSION_BUCKET`, `AWS_REGION`) with a comment referencing `infra/config.js` as the source of truth. This avoids adding a build step.

## Dependency Order

```
Step 1: Create web/booth-welcome.html          [no dependencies]
Step 2: S3 CORS config on bucket               [no dependencies, can parallel]
Step 3: Create/upload active-session.json       [needs Step 2 for browser testing]
Step 4: Test in browser                         [needs Steps 1-3]
```

Steps 1 and 2 are independent and can be done in parallel.

## Risk Mitigation

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| S3 CORS blocks fetch from `file://` origin | High | Use `AllowedOrigins: ["*"]` or serve via `python3 -m http.server` for local dev |
| `active-session.json` doesn't exist yet | Expected | 404 is handled gracefully -- page shows "WAITING FOR SESSION" |
| Google Fonts CDN unavailable (no internet at booth) | Medium | Font stack falls back to system sans-serif. Page remains fully functional. |
| S3 bucket not publicly readable | High | Document that `active-session.json` needs public-read ACL or a bucket policy allowing anonymous GET on that key only |
| Polling too aggressive (3s interval) | Low | S3 GET is cheap (~$0.0004/1000 requests). 3s = 1200 requests/hour = $0.0005/hour |

## Testing Strategy

### Manual browser test
1. Open `web/booth-welcome.html` in Chrome
2. Verify dark theme renders, all elements visible, text readable from 3 feet
3. Verify "WAITING FOR SESSION" state (no S3 file = 404 handled gracefully)

### Automated test: `scripts/test/test-booth-welcome.sh`

```bash
#!/usr/bin/env bash
# Validates booth-welcome.html structure and content
set -euo pipefail

FILE="web/booth-welcome.html"

echo "=== Booth Welcome Page Tests ==="

# File exists
test -f "$FILE" && echo "PASS: $FILE exists" || { echo "FAIL: $FILE missing"; exit 1; }

# Required content checks
grep -q "Welcome to.*BoothApp.*Demo" "$FILE" && echo "PASS: header text" || { echo "FAIL: header text missing"; exit 1; }
grep -q "QR" "$FILE" && echo "PASS: QR placeholder" || { echo "FAIL: QR placeholder missing"; exit 1; }
grep -q "LOGO" "$FILE" && echo "PASS: logo placeholder" || { echo "FAIL: logo placeholder missing"; exit 1; }
grep -q "pulse" "$FILE" && echo "PASS: pulse animation" || { echo "FAIL: pulse animation missing"; exit 1; }
grep -q "active-session.json" "$FILE" && echo "PASS: S3 polling endpoint" || { echo "FAIL: S3 polling missing"; exit 1; }
grep -q "boothapp-sessions" "$FILE" && echo "PASS: bucket reference" || { echo "FAIL: bucket reference missing"; exit 1; }
grep -q "#0d1117\|0d1117" "$FILE" && echo "PASS: dark theme background" || { echo "FAIL: dark theme missing"; exit 1; }

# No build tool artifacts
! grep -q "import .* from" "$FILE" && echo "PASS: no ES module imports" || { echo "FAIL: has ES module imports (needs build tool)"; exit 1; }
! grep -q "require(" "$FILE" && echo "PASS: no require() calls" || { echo "FAIL: has require() calls (needs Node)"; exit 1; }

# Valid HTML structure
grep -q "<!DOCTYPE html>" "$FILE" && echo "PASS: doctype" || { echo "FAIL: missing doctype"; exit 1; }
grep -q "</html>" "$FILE" && echo "PASS: closing html tag" || { echo "FAIL: missing closing html tag"; exit 1; }

echo ""
echo "All tests passed."
```

### S3 polling integration test (manual)

1. Upload test file: `aws s3 cp - s3://boothapp-sessions-752266476357/active-session.json <<< '{"active":true,"visitor_name":"Test Visitor","started_at":"2026-03-30T10:00:00Z"}'`
2. Open page -- verify RECORDING state with visitor name and timer
3. Delete file: `aws s3 rm s3://boothapp-sessions-752266476357/active-session.json`
4. Wait 3s -- verify page returns to WAITING state
