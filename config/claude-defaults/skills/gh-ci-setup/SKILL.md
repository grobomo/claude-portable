---

name: gh-ci-setup
description: Set up GitHub Actions CI with tests, screenshots, Claude auto-fix on failure, and email notification. Use when user says "ci setup", "github actions", "test pipeline", "auto fix ci", or "self healing tests".
keywords:
  - github
  - pipeline
  - auto
  - ci
  - failure
  - setup
  - actions
  - continuous
  - integration
  - automated
  - tests
  - cd
  - self
  - healing
  - workflow
  - regression
  - screenshot
enabled: true
---

# GitHub CI Setup

Sets up a complete CI pipeline with GitHub Actions including:
- Automated tests (functional + screenshot)
- Claude Code auto-fix on test failure
- Email notification when auto-fix fails
- Self-hosted runner registration
- Credential management via credential-manager

## What It Creates

| File | Purpose |
|------|---------|
| `.github/workflows/test-and-fix.yml` | GitHub Actions workflow with test -> fix -> notify |
| `scripts/run-tests.sh` | Test orchestrator (runs both tiers) |
| `scripts/setup-ci.sh` | One-time setup (credentials, secrets, runner) |
| `tests/functional/test-all.sh` | Functional test suite (customized per project) |
| `tests/screenshots/playwright-screenshots.py` | Screenshot tests for web UIs |
| `test-results/.gitkeep` | Results directory |

## Usage

```
/gh-ci-setup
```

When invoked, Claude will:
1. Detect project type (Docker container, Node.js, Python, etc.)
2. Generate project-appropriate test scripts from templates
3. Generate the GitHub Actions workflow with test -> claude-fix -> email pattern
4. Generate `scripts/setup-ci.sh` with credential-manager integration
5. Optionally run `setup-ci.sh` interactively to collect and push secrets
6. Verify runner is registered and workflow is ready

## Prerequisites

- `gh` CLI authenticated (`gh auth login`)
- Docker installed and running
- GitHub repository initialized
- For screenshot tests: `mcr.microsoft.com/playwright/python:latest` image pulled

## Workflow Pattern

```
Push to main
  |
  v
Run tests
  |
  +--> PASS: commit test results + screenshots
  |
  +--> FAIL: Claude auto-fix attempt
         |
         +--> Fix works: commit fix + results
         |
         +--> Fix fails: email notification + upload artifacts
```

## Templates

Templates in `templates/` are customized per project:

- `workflow-test-and-fix.yml` -- GitHub Actions workflow with placeholders
- `setup-ci.sh` -- Setup script with credential-manager integration
- `test-docker-container.sh` -- Functional tests for Docker container projects
- `playwright-screenshots.py` -- Screenshot tests for web applications
- `run-tests.sh` -- Test orchestrator

## Credential Management

Uses credential-manager skill to store API keys in the OS credential store
(Windows Credential Manager / macOS Keychain). Keys are read from the
credential store and pushed to GitHub Secrets during setup.

Required secrets:
- `ANTHROPIC_API_KEY` -- Claude Code CLI for auto-fix
- `NOTIFY_EMAIL` -- Failure notification recipient
- `SMTP_SERVER`, `SMTP_USERNAME`, `SMTP_PASSWORD` -- Optional, for email delivery
