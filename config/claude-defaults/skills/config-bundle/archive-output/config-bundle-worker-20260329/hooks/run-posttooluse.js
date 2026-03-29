#!/usr/bin/env node
"use strict";
// hook-runner PostToolUse — loads all run-modules/PostToolUse/*.js
var fs = require("fs");
var path = require("path");

var input = JSON.parse(fs.readFileSync(0, "utf-8"));

var dir = path.join(__dirname, "run-modules", "PostToolUse");
if (!fs.existsSync(dir)) process.exit(0);

var files = fs.readdirSync(dir).filter(function(f) { return f.endsWith(".js"); }).sort();

for (var i = 0; i < files.length; i++) {
  try {
    var mod = require(path.join(dir, files[i]));
    var result = mod(input);
    if (result && result.decision) {
      process.stdout.write(JSON.stringify(result));
      process.exit(0);
    }
  } catch (e) {
    process.stderr.write("hook-runner PostToolUse " + files[i] + " error: " + e.message + "\n");
  }
}
