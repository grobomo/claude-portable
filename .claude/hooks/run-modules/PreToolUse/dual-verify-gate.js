// dual-verify-gate.js -- PreToolUse hook module
// Blocks "gh pr merge" unless BOTH worker test AND manager review markers exist.
//
// Marker files checked (relative to repo root):
//   .test-results/T<NNN>.worker-passed
//   .test-results/T<NNN>.manager-reviewed
//
// The task number is extracted from the PR branch name (task-<NNN>-*) or
// from the gh pr merge command arguments (--subject, PR number lookup).
//
// Contract:
//   stdin  = JSON { tool_name, tool_input }
//   stdout = JSON { decision: "allow"|"block", reason }
//   exit 0 = allow, exit 2 = block

var fs = require("fs");
var path = require("path");

function main() {
  var raw = fs.readFileSync(0, "utf-8");
  var input;
  try {
    input = JSON.parse(raw);
  } catch (e) {
    // Can't parse -- allow by default
    process.stdout.write(JSON.stringify({ decision: "allow", reason: "unparseable input" }));
    process.exit(0);
  }

  var toolName = input.tool_name || "";
  var toolInput = input.tool_input || {};
  var command = toolInput.command || "";

  // Only gate "gh pr merge" commands
  if (toolName !== "Bash") {
    process.exit(0);
  }

  if (!command.match(/gh\s+pr\s+merge/)) {
    process.exit(0);
  }

  // Extract task number from multiple sources
  var taskNum = extractTaskNumber(command);

  if (!taskNum) {
    // Try from current branch name
    taskNum = extractTaskFromBranch();
  }

  if (!taskNum) {
    process.stdout.write(JSON.stringify({
      decision: "block",
      reason: "Cannot determine task number for dual-verify gate. " +
              "Ensure branch follows task-<NNN>-* pattern or pass --task <NNN>."
    }));
    process.exit(2);
  }

  // Check for both marker files
  var repoRoot = findRepoRoot();
  var workerMarker = path.join(repoRoot, ".test-results", "T" + taskNum + ".worker-passed");
  var managerMarker = path.join(repoRoot, ".test-results", "T" + taskNum + ".manager-reviewed");

  var workerPassed = fs.existsSync(workerMarker);
  var managerReviewed = fs.existsSync(managerMarker);

  if (workerPassed && managerReviewed) {
    process.stdout.write(JSON.stringify({
      decision: "allow",
      reason: "Dual verification passed for T" + taskNum +
              ": worker-passed + manager-reviewed"
    }));
    process.exit(0);
  }

  var missing = [];
  if (!workerPassed) missing.push("worker-passed");
  if (!managerReviewed) missing.push("manager-reviewed");

  process.stdout.write(JSON.stringify({
    decision: "block",
    reason: "Dual-verify gate: missing markers for T" + taskNum + ": " +
            missing.join(", ") + ". " +
            "Run worker-verify.sh and manager-review.sh before merging."
  }));
  process.exit(2);
}

function extractTaskNumber(command) {
  // Pattern 1: explicit --task NNN in the command
  var taskFlag = command.match(/--task\s+(\d+)/);
  if (taskFlag) return taskFlag[1];

  // Pattern 2: branch name in the command (task-NNN-*)
  var branchMatch = command.match(/task-(\d+)/);
  if (branchMatch) return branchMatch[1];

  // Pattern 3: PR number -- we can't resolve this without gh, skip
  return null;
}

function extractTaskFromBranch() {
  try {
    var branch = require("child_process")
      .execSync("git rev-parse --abbrev-ref HEAD 2>/dev/null", { encoding: "utf-8" })
      .trim();
    var match = branch.match(/task-(\d+)/);
    if (match) return match[1];
  } catch (e) {
    // Not in a git repo or git not available
  }
  return null;
}

function findRepoRoot() {
  try {
    return require("child_process")
      .execSync("git rev-parse --show-toplevel 2>/dev/null", { encoding: "utf-8" })
      .trim();
  } catch (e) {
    return process.cwd();
  }
}

main();
