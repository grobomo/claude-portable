// GSD gate: blocks execution tools until PLAN.md exists in .planning/quick/
// Works with spec-kit: worker reads .specs/ then creates PLAN.md from it
var fs = require("fs");
var path = require("path");

module.exports = function(input) {
  var tool = input.tool_name || "";
  var cwd = input.cwd || process.cwd();

  // Only gate execution tools — read-only allowed for research
  var GATED = ["Bash", "Write", "Edit", "Task", "WebFetch"];
  if (GATED.indexOf(tool) === -1) return null;

  // Check for GSD project marker
  var configPath = path.join(cwd, ".planning", "config.json");
  if (!fs.existsSync(configPath)) return null; // not a GSD project

  var config;
  try {
    config = JSON.parse(fs.readFileSync(configPath, "utf8"));
  } catch (e) {
    return null;
  }

  if (!config.auto_initialized) return null;

  // Allow writing PLAN.md itself and .planning/ files (bootstrap)
  var toolInput = input.tool_input || {};
  var targetFile = toolInput.file_path || toolInput.command || "";
  if (typeof targetFile === "string") {
    if (targetFile.indexOf("PLAN.md") !== -1) return null;
    if (targetFile.indexOf(".planning") !== -1) return null;
    if (targetFile.indexOf("TODO.md") !== -1) return null;
  }

  // Find latest task dir
  var quickDir = path.join(cwd, ".planning", "quick");
  if (!fs.existsSync(quickDir)) {
    return {
      decision: "deny",
      reason: "GSD ENFORCED: Create a plan before executing.\n" +
        "1. mkdir -p .planning/quick/001-task-slug/\n" +
        "2. Write 001-PLAN.md with Goal + Success Criteria\n" +
        "3. Then execute\n" +
        "Read .specs/ first if a spec was provided."
    };
  }

  var taskDirs;
  try {
    taskDirs = fs.readdirSync(quickDir)
      .filter(function(d) { return /^\d{3}-/.test(d); })
      .sort()
      .reverse();
  } catch (e) {
    return null;
  }

  if (taskDirs.length === 0) {
    return {
      decision: "deny",
      reason: "GSD ENFORCED: No task directory in .planning/quick/.\n" +
        "Create .planning/quick/001-<slug>/ and write 001-PLAN.md first."
    };
  }

  // Check latest task for PLAN.md
  var latest = taskDirs[0];
  var num = latest.match(/^(\d{3})/)[1];
  var planPath = path.join(quickDir, latest, num + "-PLAN.md");

  if (!fs.existsSync(planPath)) {
    return {
      decision: "deny",
      reason: "GSD ENFORCED: No " + num + "-PLAN.md in .planning/quick/" + latest + "/.\n" +
        "Write your plan with Goal + Success Criteria before implementing."
    };
  }

  return null; // PLAN.md exists, allow
};
