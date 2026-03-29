// Enforcement gate: git repo, clean tree, TODO.md required before Edit/Write
var fs = require("fs");
var path = require("path");
var child_process = require("child_process");

module.exports = function(input) {
  var tool = input.tool_name;
  var toolInput = input.tool_input || {};

  // Only gate Edit and Write
  if (tool !== "Edit" && tool !== "Write") return null;

  var targetFile = toolInput.file_path || "";

  // Allow writing TODO.md (bootstrap)
  if (path.basename(targetFile) === "TODO.md") return null;

  // Find project dir
  var projectDir = process.env.CLAUDE_PROJECT_DIR || "";
  if (targetFile) projectDir = path.dirname(targetFile);
  if (!projectDir) return null;

  // Find git root
  var gitRoot = null;
  var checkDir = projectDir;
  for (var i = 0; i < 20; i++) {
    if (fs.existsSync(path.join(checkDir, ".git"))) {
      gitRoot = checkDir;
      break;
    }
    var parent = path.dirname(checkDir);
    if (parent === checkDir) break;
    checkDir = parent;
  }

  // CHECK 1: No git repo
  if (!gitRoot) {
    return {
      decision: "deny",
      reason: "No git repo at " + projectDir + ". Run: git init && git add -A && git commit -m 'Initial commit'. Every project must be tracked in git."
    };
  }

  // CHECK 2: Dirty working tree
  try {
    var status = child_process.execSync("git status --porcelain", {
      cwd: gitRoot, encoding: "utf-8", timeout: 5000
    }).trim();
    if (status.length > 0) {
      return {
        decision: "deny",
        reason: "Dirty working tree in " + gitRoot + ". Commit before making new changes. Run: git add <files> && git commit -m 'description'"
      };
    }
  } catch (e) {
    // git status failed, skip check
  }

  // CHECK 3: No TODO.md
  if (!fs.existsSync(path.join(gitRoot, "TODO.md"))) {
    return {
      decision: "deny",
      reason: "No TODO.md in " + gitRoot + ". Write a plan to TODO.md before making code changes. Document what you're doing and why."
    };
  }

  return null; // all checks pass
};
