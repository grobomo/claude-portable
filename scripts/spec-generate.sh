#!/bin/bash
# spec-generate.sh — Generate spec-kit artifacts from a raw task description.
# Called by dispatcher before sending work to a worker.
#
# Usage: spec-generate.sh <task-text> <output-dir> [repo-dir]
# Output: <output-dir>/.specs/<slug>/spec.md, plan.md, tasks.md
#
# Uses claude -p to run each spec-kit phase. Falls back gracefully if any
# phase fails — partial specs are still useful.

set -euo pipefail

TASK_TEXT="${1:?Usage: spec-generate.sh <task-text> <output-dir> [repo-dir]}"
OUTPUT_DIR="${2:?Usage: spec-generate.sh <task-text> <output-dir> [repo-dir]}"
REPO_DIR="${3:-/workspace/boothapp}"
TIMEOUT="${SPEC_TIMEOUT:-200}"  # per-step timeout (3 steps fit in 600s outer limit)

# Generate a slug from the task text (first 4 words, lowercase, hyphenated)
SLUG=$(echo "$TASK_TEXT" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9 ]//g' | awk '{for(i=1;i<=4&&i<=NF;i++) printf "%s-",$i}' | sed 's/-$//')
[ -z "$SLUG" ] && SLUG="task"

SPEC_DIR="$OUTPUT_DIR/.specs/$SLUG"
mkdir -p "$SPEC_DIR"

echo "[spec-generate] Task: $TASK_TEXT"
echo "[spec-generate] Output: $SPEC_DIR"
echo "[spec-generate] Timeout: ${TIMEOUT}s per phase"

# Phase 1: Specify — generate the specification
echo "[spec-generate] Phase 1/3: Specify..."
timeout "$TIMEOUT" claude -p "You are creating a software specification. Given this task request, write a structured spec.md with: Problem Statement, Solution, Components, Success Criteria, and Out of Scope sections.

The codebase is a trade show demo capture app (boothapp). Key components: Chrome extension (click tracking, screenshots), audio recorder, S3 session storage, analysis pipeline (transcription + Claude analysis), session orchestrator Lambda.

Task request: $TASK_TEXT

Write ONLY the spec.md content, no preamble." --output-format text 2>/dev/null > "$SPEC_DIR/spec.md" || {
  echo "[spec-generate] WARNING: Specify phase failed, writing minimal spec"
  cat > "$SPEC_DIR/spec.md" << EOF
# Spec: $TASK_TEXT

## Problem Statement
$TASK_TEXT

## Success Criteria
- [ ] Task completed as described
- [ ] Tests pass
- [ ] PR created with clear description
EOF
}

# Phase 2: Plan — generate implementation plan from spec
echo "[spec-generate] Phase 2/3: Plan..."
SPEC_CONTENT=$(cat "$SPEC_DIR/spec.md")
timeout "$TIMEOUT" claude -p "Given this specification, create a technical implementation plan (plan.md). Include: Technical Approach (with specific files to change), Dependency Order, and Risk Mitigation. Be specific about file paths relative to the boothapp repo.

Specification:
$SPEC_CONTENT

Write ONLY the plan.md content, no preamble." --output-format text 2>/dev/null > "$SPEC_DIR/plan.md" || {
  echo "[spec-generate] WARNING: Plan phase failed, skipping"
  echo "# Plan\n\nImplement the specification above. See spec.md for details." > "$SPEC_DIR/plan.md"
}

# Phase 3: Tasks — break into actionable tasks
echo "[spec-generate] Phase 3/3: Tasks..."
PLAN_CONTENT=$(cat "$SPEC_DIR/plan.md")
timeout "$TIMEOUT" claude -p "Given this spec and plan, create a tasks.md with numbered, actionable implementation tasks. Each task should have checkboxes for sub-steps. Order tasks by dependency.

Specification:
$SPEC_CONTENT

Plan:
$PLAN_CONTENT

Write ONLY the tasks.md content, no preamble." --output-format text 2>/dev/null > "$SPEC_DIR/tasks.md" || {
  echo "[spec-generate] WARNING: Tasks phase failed, skipping"
  echo "# Tasks\n\n- [ ] Implement spec as described in spec.md" > "$SPEC_DIR/tasks.md"
}

# Also create the GSD planning scaffold
GSD_DIR="$OUTPUT_DIR/.planning"
mkdir -p "$GSD_DIR/quick"
cat > "$GSD_DIR/config.json" << EOF
{
  "mode": "yolo",
  "depth": "quick",
  "auto_initialized": true,
  "workflow": {
    "verifier": true
  },
  "spec_dir": ".specs/$SLUG"
}
EOF

echo "[spec-generate] Done. Spec at: $SPEC_DIR"
echo "[spec-generate] GSD config at: $GSD_DIR/config.json"
ls -la "$SPEC_DIR/"
