#!/usr/bin/env node
/**
 * Code Review Setup
 * Installs routing instruction for the code-review skill.
 * Checks for credential-manager dependency and optionally registers
 * security MCP servers (gitleaks, semgrep, nuclei) in mcpm.
 *
 * Usage:
 *   node setup.js            # Install
 *   node setup.js --uninstall # Restore from backup
 */

var utils = require('../../super-manager/shared/setup-utils');
var fs = require('fs');
var path = require('path');
var os = require('os');

var MANAGER_NAME = 'code-review';

function main() {
  console.log('[' + MANAGER_NAME + ':setup] Starting...');
  console.log('');

  // Check dependencies
  var warnings = [];
  var credInstalled = utils.checkDependency('credential-manager').installed;
  var secScanInstalled = utils.checkDependency('security-scan').installed;

  if (!credInstalled) {
    warnings.push('credential-manager not installed. Secret scanning will detect but cannot cross-reference keyring.');
    warnings.push('Install credential-manager for full secret->keyring integration.');
  }
  if (!secScanInstalled) {
    warnings.push('security-scan skill not found. OWASP/vuln fallback scanning unavailable.');
  }

  // Backup
  var filesToBackup = [
    path.join(utils.INSTRUCTIONS_DIR, 'UserPromptSubmit', 'code-review-routing.md')
  ];
  var backupResult = utils.backup(MANAGER_NAME, filesToBackup);
  console.log('[' + MANAGER_NAME + ':setup] Backup: ' + backupResult.backupDir);

  // Install routing instruction
  var instructions = [];
  var routing = utils.ensureRoutingInstruction({
    toolName: 'code-review',
    toolType: 'skill',
    keywords: ['review', 'audit', 'consistency', 'stale', 'phantom', 'secrets', 'drift', 'dead references'],
    description: 'Automated config consistency, secret scanning, and security review',
    whenToUse: 'prompt involves reviewing config, finding stale references, auditing secrets, or security scanning',
    neverUse: 'manual grep across config files',
    whyNot: 'code-review automates all checks with structured output and credential-manager integration',
    howToUse: 'Skill tool: code-review [path] [--secrets-only] [--config-only]'
  });
  instructions.push(routing);
  if (routing.method !== 'skipped') {
    utils.trackCreatedFile(backupResult.backupDir, routing.path);
  }

  // Print summary
  utils.printSummary({
    manager: MANAGER_NAME,
    backup: backupResult,
    instructions: instructions,
    hooks: [],
    warnings: warnings
  });

  return { backup: backupResult, instructions: instructions, warnings: warnings };
}

function uninstall() {
  console.log('[' + MANAGER_NAME + ':uninstall] Starting...');
  var latestBackup = utils.findLatestBackup(MANAGER_NAME);
  if (!latestBackup) {
    console.log('[' + MANAGER_NAME + ':uninstall] No backup found. Nothing to restore.');
    return;
  }
  var result = utils.restore(latestBackup);
  console.log('[' + MANAGER_NAME + ':uninstall] Restored ' + result.restored.length + ' files');
  console.log('[' + MANAGER_NAME + ':uninstall] Removed ' + result.removed.length + ' created files');
  if (result.errors.length > 0) {
    console.log('[' + MANAGER_NAME + ':uninstall] Errors: ' + result.errors.join(', '));
  }
}

module.exports = { main: main, uninstall: uninstall };
if (require.main === module) {
  if (process.argv.indexOf('--uninstall') !== -1) {
    uninstall();
  } else {
    main();
  }
}
