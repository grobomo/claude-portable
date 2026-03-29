// Rule hygiene: validates rule files are granular and path-scoped
var fs = require("fs");
var path = require("path");

module.exports = function(input) {
  var filePath = (input.tool_input || {}).file_path || "";
  var normalized = filePath.replace(/\\/g, "/");

  // Only check files in rules directories
  if (!normalized.includes("/rules/") || !normalized.endsWith(".md")) return null;

  var warnings = [];
  var fileName = path.basename(normalized, ".md");

  // Check filename
  var badNames = ["session-", "gotchas", "misc", "notes", "todo", "temp"];
  for (var i = 0; i < badNames.length; i++) {
    if (fileName.toLowerCase().indexOf(badNames[i]) === 0 || fileName.toLowerCase() === badNames[i]) {
      warnings.push('Bad rule filename "' + fileName + '.md" - use a descriptive topic name');
      break;
    }
  }

  // Check file content if it exists
  if (fs.existsSync(filePath)) {
    var content = fs.readFileSync(filePath, "utf8");
    var lines = content.split("\n");

    if (lines.length > 25) {
      warnings.push("Rule file is " + lines.length + " lines - keep under 20. Split into multiple files.");
    }

    var h2Count = 0;
    for (var j = 0; j < lines.length; j++) {
      if (lines[j].indexOf("## ") === 0) h2Count++;
    }
    if (h2Count > 2) {
      warnings.push("Rule file has " + h2Count + " sections - likely covers multiple topics. One topic per file.");
    }
  }

  // Check if project-specific rule is in global rules
  var home = (process.env.HOME || "").replace(/\\/g, "/");
  if (home && normalized.indexOf(home + "/.claude/rules/") >= 0) {
    var projectKeywords = ["dispatcher", "bootstrap", "worker", "rone", "teams", "poller", "ccc"];
    for (var k = 0; k < projectKeywords.length; k++) {
      if (fileName.toLowerCase().indexOf(projectKeywords[k]) >= 0) {
        warnings.push('"' + fileName + '.md" looks project-specific but is in global rules. Move to project .claude/rules/');
        break;
      }
    }
  }

  if (warnings.length > 0) {
    return {
      decision: "block",
      reason: "Rule hygiene:\n" + warnings.map(function(w) { return "- " + w; }).join("\n")
    };
  }

  return null;
};
