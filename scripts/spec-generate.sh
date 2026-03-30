#!/bin/bash
# spec-generate.sh — Generate production-quality spec-kit artifacts from a task description.
# Called by dispatcher before sending work to a worker.
#
# Usage: spec-generate.sh <task-text> <output-dir> [repo-dir]
# Output: <output-dir>/.specs/<slug>/spec.md, plan.md, tasks.md
#
# Quality approach:
# - Injects full project CLAUDE.md as context (architecture, components, conventions)
# - Provides example spec format so output matches team standards
# - Three-phase: specify → plan → tasks (each phase builds on previous)
# - Graceful fallback: partial specs are still useful

set -euo pipefail

TASK_TEXT="${1:?Usage: spec-generate.sh <task-text> <output-dir> [repo-dir]}"
OUTPUT_DIR="${2:?Usage: spec-generate.sh <task-text> <output-dir> [repo-dir]}"
REPO_DIR="${3:-/workspace/boothapp}"
TIMEOUT="${SPEC_TIMEOUT:-200}"  # per-phase timeout (dispatcher sets via SPEC_TIMEOUT)

# Generate a slug from the task text (first 4 words, lowercase, hyphenated)
SLUG=$(echo "$TASK_TEXT" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9 ]//g' | awk '{for(i=1;i<=4&&i<=NF;i++) printf "%s-",$i}' | sed 's/-$//')
[ -z "$SLUG" ] && SLUG="task"

SPEC_DIR="$OUTPUT_DIR/.specs/$SLUG"
mkdir -p "$SPEC_DIR"

echo "[spec-generate] Task: $TASK_TEXT"
echo "[spec-generate] Output: $SPEC_DIR"
echo "[spec-generate] Timeout: ${TIMEOUT}s per phase"

# ---- Context injection ----
# Read project CLAUDE.md for full architecture context
PROJECT_CONTEXT=""
for ctx_file in "$REPO_DIR/CLAUDE.md" "$REPO_DIR/README.md"; do
  if [ -f "$ctx_file" ]; then
    PROJECT_CONTEXT=$(head -200 "$ctx_file")
    echo "[spec-generate] Context from: $ctx_file ($(wc -l < "$ctx_file") lines)"
    break
  fi
done

# Read existing specs for format examples
EXAMPLE_SPEC=""
for existing in "$REPO_DIR"/.specs/*/spec.md "$OUTPUT_DIR"/.specs/*/spec.md; do
  if [ -f "$existing" ]; then
    EXAMPLE_SPEC=$(head -60 "$existing")
    echo "[spec-generate] Example format from: $existing"
    break
  fi
done

# List repo structure for file-path awareness
REPO_TREE=""
if [ -d "$REPO_DIR" ]; then
  REPO_TREE=$(find "$REPO_DIR" -maxdepth 3 -type f -name "*.js" -o -name "*.py" -o -name "*.sh" -o -name "*.yaml" -o -name "*.json" -o -name "*.html" 2>/dev/null | head -80 | sed "s|$REPO_DIR/||" | sort)
fi

# ---- Build rich prompts using temp files (avoids quoting issues) ----

# Phase 1: Specify
echo "[spec-generate] Phase 1/3: Specify..."
SPECIFY_PROMPT=$(mktemp)
cat > "$SPECIFY_PROMPT" << 'PROMPT_HEADER'
You are a senior software architect writing a detailed technical specification. Your specs are known for:
- Concrete problem statements that explain WHY, not just WHAT
- Multi-tier solutions with clear decision logic (if X then Y, else Z)
- Specific file paths and component names from the codebase
- Enumerated types/categories where applicable
- Success criteria that are testable (exit 0/1, not "verify manually")
- Consideration of failure modes and edge cases

PROMPT_HEADER

if [ -n "$PROJECT_CONTEXT" ]; then
  cat >> "$SPECIFY_PROMPT" << EOF
## Project Context (from CLAUDE.md)
$PROJECT_CONTEXT

EOF
fi

if [ -n "$EXAMPLE_SPEC" ]; then
  cat >> "$SPECIFY_PROMPT" << EOF
## Example Spec Format (match this style)
$EXAMPLE_SPEC

EOF
fi

if [ -n "$REPO_TREE" ]; then
  cat >> "$SPECIFY_PROMPT" << EOF
## Repository File Structure
$REPO_TREE

EOF
fi

cat >> "$SPECIFY_PROMPT" << EOF
## Task Request
$TASK_TEXT

## Instructions
Write a spec.md for this task. Include these sections:
1. **Problem** — What's broken or missing, and why it matters
2. **Solution** — Detailed technical approach with subsections for each component
3. **Key Decisions** — Tradeoffs considered, with rationale for chosen approach
4. **Success Criteria** — Numbered, each testable with a script or command

Reference specific files, directories, and components from the codebase.
Use markdown headers, bullet lists, and code blocks for clarity.
Write ONLY the spec.md content. No preamble, no "here's the spec" intro.
EOF

timeout "$TIMEOUT" claude -p "$(cat "$SPECIFY_PROMPT")" --dangerously-skip-permissions --output-format text 2>/dev/null > "$SPEC_DIR/spec.md" || {
  echo "[spec-generate] WARNING: Specify phase failed, writing minimal spec"
  cat > "$SPEC_DIR/spec.md" << EOF
# Spec: $TASK_TEXT

## Problem
$TASK_TEXT

## Success Criteria
- [ ] Task completed as described
- [ ] Tests pass
- [ ] PR created with clear description
EOF
}
rm -f "$SPECIFY_PROMPT"

# Phase 2: Plan
echo "[spec-generate] Phase 2/3: Plan..."
SPEC_CONTENT=$(cat "$SPEC_DIR/spec.md")
PLAN_PROMPT=$(mktemp)
cat > "$PLAN_PROMPT" << EOF
You are creating a technical implementation plan for a software specification. The plan must be actionable — a developer should be able to follow it step by step.

## Specification
$SPEC_CONTENT

## Repository Files
$REPO_TREE

## Instructions
Write a plan.md with:
1. **Technical Approach** — specific files to create/modify, with the exact changes described
2. **Dependency Order** — which steps must complete before others can start
3. **Risk Mitigation** — what could go wrong and how to handle it
4. **Testing Strategy** — how to verify each component works (scripts in scripts/test/)

Be specific about file paths. Reference existing code where modifications are needed.
Write ONLY the plan.md content. No preamble.
EOF

timeout "$TIMEOUT" claude -p "$(cat "$PLAN_PROMPT")" --dangerously-skip-permissions --output-format text 2>/dev/null > "$SPEC_DIR/plan.md" || {
  echo "[spec-generate] WARNING: Plan phase failed, writing minimal plan"
  echo -e "# Plan\n\nImplement the specification in spec.md. See spec.md for details." > "$SPEC_DIR/plan.md"
}
rm -f "$PLAN_PROMPT"

# Phase 3: Tasks
echo "[spec-generate] Phase 3/3: Tasks..."
PLAN_CONTENT=$(cat "$SPEC_DIR/plan.md")
TASKS_PROMPT=$(mktemp)
cat > "$TASKS_PROMPT" << EOF
You are breaking down a technical plan into actionable tasks for a GSD (Get Stuff Done) workflow.

## Specification
$SPEC_CONTENT

## Implementation Plan
$PLAN_CONTENT

## Instructions
Write a tasks.md with:
- Tasks grouped into phases (## Phase N: Name)
- Each task as a checkbox: - [ ] TNNN: Description
- Sub-steps indented under each task
- Each phase ends with a **Checkpoint** that references a test script:
  \`\`\`
  **Checkpoint:** \`bash scripts/test/test-<feature>.sh\` — description of what it validates
  \`\`\`
- Tasks ordered by dependency (earlier tasks don't depend on later ones)
- Each task is small enough for one PR (< 300 lines of code changes)

The checkpoint test scripts must:
- Exit 0 on pass, non-zero on fail
- Be idempotent (safe to re-run)
- Test real behavior, not mocks

Write ONLY the tasks.md content. No preamble.
EOF

timeout "$TIMEOUT" claude -p "$(cat "$TASKS_PROMPT")" --dangerously-skip-permissions --output-format text 2>/dev/null > "$SPEC_DIR/tasks.md" || {
  echo "[spec-generate] WARNING: Tasks phase failed, writing minimal tasks"
  echo -e "# Tasks\n\n- [ ] T001: Implement spec as described in spec.md\n\n**Checkpoint:** Manual verification" > "$SPEC_DIR/tasks.md"
}
rm -f "$TASKS_PROMPT"

# Create GSD planning scaffold
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

echo "[spec-generate] Done. Files:"
ls -la "$SPEC_DIR/"
echo "[spec-generate] GSD config at: $GSD_DIR/config.json"
