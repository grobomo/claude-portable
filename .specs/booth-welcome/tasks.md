# Tasks: Booth Welcome Page

## Phase 1: Page Structure and Dark Theme

- [x] T001: Create `web/booth-welcome.html` with HTML5 boilerplate
  - DOCTYPE, charset, viewport meta
  - Dark theme body (`#0d1117` background, `#e6edf3` text)
  - Inter font from Google Fonts
  - Centered flex layout

- [x] T002: Add static content sections
  - Company logo placeholder (SVG circle + "LOGO" text)
  - "Welcome to BoothApp Demo" header (3rem+ font)
  - QR code placeholder box with "Scan for follow-up" label
  - All text readable from 3 feet (1.4rem+ body text)

**Checkpoint:** `bash scripts/test/test-booth-welcome.sh` -- validates file exists, header text, logo/QR placeholders, dark theme colors, font sizes, valid HTML structure

## Phase 2: Recording Indicator and Session State

- [x] T003: Add animated recording indicator
  - Pulsing red dot with `@keyframes pulse` animation
  - "RECORDING" label next to indicator
  - Visitor name display element
  - Elapsed time counter
  - Hidden by default, shown when session active

- [x] T004: Add S3 session polling logic
  - Poll `active-session.json` from `boothapp-sessions` S3 bucket
  - Use `infra/config.js` values for bucket/region
  - Toggle recording indicator based on session status
  - Update visitor name and elapsed timer from session data
  - Pure JS -- no ES module imports, no require() calls

**Checkpoint:** `bash scripts/test/test-booth-welcome.sh` -- validates pulse animation, S3 polling endpoint, bucket reference, recording state, visitor name element, elapsed timer, no build tool artifacts

## Phase 3: PR and Cleanup

- [x] T005: Create PR from feature branch
  - Branch from main
  - Stage `web/booth-welcome.html` and test script
  - Push and open PR with clear description
  - Verify all 20 test checks pass

**Checkpoint:** `bash scripts/test/test-booth-welcome.sh` -- full 20/20 pass confirms page is complete
