#!/usr/bin/env node
"use strict";
// hook-runner PreToolUse — loads all run-modules/PreToolUse/*.js
var fs = require("fs");
var path = require("path");

var input = JSON.parse(fs.readFileSync(0, "utf-8"));

var dir = path.join(__dirname, "run-modules", "PreToolUse");
if (!fs.existsSync(dir)) process.exit(0);

var files = fs.readdirSync(dir).filter(function(f) { return f.endsWith(".js"); }).sort();

for (var i = 0; i < files.length; i++) {
  try {
    var mod = require(path.join(dir, files[i]));
    var result = mod(input);
    if (result && result.decision) {
      process.stdout.write(JSON.stringify({ hookSpecificOutput: result }));
      process.exit(0);
    }
  } catch (e) {
    process.stderr.write("hook-runner PreToolUse " + files[i] + " error: " + e.message + "\n");
  }
}

process.stdout.write(JSON.stringify({ hookSpecificOutput: { decision: "allow" } }));
