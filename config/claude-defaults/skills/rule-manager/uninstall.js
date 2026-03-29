#!/usr/bin/env node
/**
 * Rule Manager Uninstall
 *
 * Restores from the most recent backup created by setup.js.
 * Archives (never deletes) any files that setup created.
 *
 * Usage:
 *   node uninstall.js
 */

var fs = require('fs');
var path = require('path');
var os = require('os');

var HOME = os.homedir();
var CLAUDE_DIR = path.join(HOME, '.claude');
var UTILS_PATH = path.join(CLAUDE_DIR, 'super-manager', 'shared', 'setup-utils.js');

// Load shared utilities
var utils;
try {
  utils = require(UTILS_PATH);
} catch (e) {
  console.log('[rule-manager:uninstall] ERROR: Cannot load setup-utils.js');
  console.log('[rule-manager:uninstall] Expected at: ' + UTILS_PATH);
  console.log('[rule-manager:uninstall] ' + e.message);
  process.exit(1);
}

var MANAGER_NAME = 'rule-manager';

// ================================================================
// Main
// ================================================================

function main() {
  console.log('');
  console.log('[rule-manager:uninstall] ============================================');
  console.log('[rule-manager:uninstall] Rule Manager Uninstall');
  console.log('[rule-manager:uninstall] ============================================');
  console.log('');

  // -- Find latest backup --
  var backupDir = utils.findLatestBackup(MANAGER_NAME);
  if (!backupDir) {
    console.log('[rule-manager:uninstall] ERROR: No backups found for ' + MANAGER_NAME);
    console.log('[rule-manager:uninstall] Nothing to restore. Aborting.');
    process.exit(1);
  }

  var manifestPath = path.join(backupDir, 'manifest.json');
  if (!fs.existsSync(manifestPath)) {
    console.log('[rule-manager:uninstall] ERROR: No manifest.json in ' + backupDir);
    process.exit(1);
  }

  var manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  console.log('[rule-manager:uninstall] Backup found: ' + backupDir);
  console.log('[rule-manager:uninstall] Timestamp: ' + manifest.timestamp);
  console.log('[rule-manager:uninstall] Files backed up: ' + manifest.files.length);
  console.log('[rule-manager:uninstall] Files created by setup: ' + (manifest.created ? manifest.created.length : 0));
  console.log('');

  // -- Restore from backup --
  console.log('[rule-manager:uninstall] Restoring...');
  var result = utils.restore(backupDir);

  // Report restored files
  if (result.restored.length > 0) {
    console.log('[rule-manager:uninstall] Restored:');
    for (var i = 0; i < result.restored.length; i++) {
      console.log('[rule-manager:uninstall]   ' + path.relative(CLAUDE_DIR, result.restored[i]));
    }
  }

  // Report archived (removed) files
  if (result.removed.length > 0) {
    console.log('[rule-manager:uninstall] Archived (created by setup):');
    for (var j = 0; j < result.removed.length; j++) {
      console.log('[rule-manager:uninstall]   ' + path.relative(CLAUDE_DIR, result.removed[j]));
    }
  }

  // Report errors
  if (result.errors.length > 0) {
    console.log('[rule-manager:uninstall] Errors:');
    for (var k = 0; k < result.errors.length; k++) {
      console.log('[rule-manager:uninstall]   [!] ' + result.errors[k]);
    }
  }

  // -- Remove from skill-registry.json if present --
  var registryPath = path.join(CLAUDE_DIR, 'hooks', 'skill-registry.json');
  if (fs.existsSync(registryPath)) {
    try {
      var registry = JSON.parse(fs.readFileSync(registryPath, 'utf8'));
      if (registry.skills && Array.isArray(registry.skills)) {
        var before = registry.skills.length;
        registry.skills = registry.skills.filter(function (s) {
          return s.id !== MANAGER_NAME;
        });
        if (registry.skills.length < before) {
          fs.writeFileSync(registryPath, JSON.stringify(registry, null, 2), 'utf8');
          console.log('[rule-manager:uninstall] Removed from skill-registry.json');
        }
      }
    } catch (e) {
      console.log('[rule-manager:uninstall] Warning: Could not update skill-registry.json: ' + e.message);
    }
  }

  // -- Summary --
  console.log('');
  console.log('[rule-manager:uninstall] ============================================');
  console.log('[rule-manager:uninstall] Uninstall Complete');
  console.log('[rule-manager:uninstall] ============================================');
  console.log('[rule-manager:uninstall] Restored: ' + result.restored.length + ' file(s)');
  console.log('[rule-manager:uninstall] Archived: ' + result.removed.length + ' file(s)');
  console.log('[rule-manager:uninstall] Errors: ' + result.errors.length);
  console.log('[rule-manager:uninstall]');
  console.log('[rule-manager:uninstall] SKILL.md preserved - skill is still available.');
  console.log('[rule-manager:uninstall] Re-install: node ~/.claude/skills/rule-manager/setup.js');
  console.log('[rule-manager:uninstall] ============================================');
  console.log('');
}

// ================================================================
// Exports
// ================================================================

module.exports = { main: main };

if (require.main === module) main();
