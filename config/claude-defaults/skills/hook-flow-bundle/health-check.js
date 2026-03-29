#!/usr/bin/env node
/**
 * health-check.js - Verify workflow bundle installation
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const HOME = process.env.HOME || process.env.USERPROFILE;
const HOOKS_DIR = path.join(HOME, '.claude', 'hooks');
const SETTINGS_PATH = path.join(HOME, '.claude', 'settings.json');

const REQUIRED_HOOKS = [
  'skill-mcp-claudemd-injector.js',
  'hook-logger.js'
];

const OPTIONAL_HOOKS = [
  'auto-gsd.js',
  'preference-learner.js',
  'gsd-check-update.js'
];

let passed = 0, failed = 0, warnings = 0;

function check(name, condition, fix) {
  if (condition) {
    console.log(`[OK] ${name}`);
    passed++;
  } else {
    console.log(`[XX] ${name}`);
    if (fix) console.log(`     Fix: ${fix}`);
    failed++;
  }
}

function warn(name, condition, note) {
  if (condition) {
    console.log(`[OK] ${name}`);
    passed++;
  } else {
    console.log(`[!!] ${name}`);
    if (note) console.log(`     ${note}`);
    warnings++;
  }
}

console.log('=== Workflow Bundle Health Check ===\n');

// Check required hooks
console.log('--- Required Hooks ---');
for (const hook of REQUIRED_HOOKS) {
  check(hook, fs.existsSync(path.join(HOOKS_DIR, hook)), `Run install-workflow.js`);
}

// Check optional hooks
console.log('\n--- Optional Hooks ---');
for (const hook of OPTIONAL_HOOKS) {
  warn(hook, fs.existsSync(path.join(HOOKS_DIR, hook)), 'Optional - GSD integration');
}

// Check skill registry
console.log('\n--- Registries ---');
const registryPath = path.join(HOOKS_DIR, 'skill-registry.json');
check('skill-registry.json exists', fs.existsSync(registryPath));
if (fs.existsSync(registryPath)) {
  try {
    const reg = JSON.parse(fs.readFileSync(registryPath, 'utf-8'));
    const enabled = (reg.skills || []).filter(s => s.enabled).length;
    console.log(`     ${enabled} skills enabled`);
  } catch (e) {
    console.log(`     [!!] Invalid JSON`);
  }
}

// Check settings.json has hooks
console.log('\n--- Settings ---');
if (fs.existsSync(SETTINGS_PATH)) {
  try {
    const settings = JSON.parse(fs.readFileSync(SETTINGS_PATH, 'utf-8'));
    const hasInjector = JSON.stringify(settings.hooks || {}).includes('skill-mcp-claudemd-injector');
    check('Injector hook in settings.json', hasInjector, 'Run install-workflow.js');
  } catch (e) {
    check('settings.json valid JSON', false, 'Restore from backup');
  }
} else {
  check('settings.json exists', false, 'Create ~/.claude/settings.json');
}

// Test hook execution
console.log('\n--- Hook Execution Test ---');
try {
  const result = execSync(
    `echo '{"prompt":"test"}' | node "${path.join(HOOKS_DIR, 'skill-mcp-claudemd-injector.js')}"`,
    { encoding: 'utf-8', timeout: 5000 }
  );
  check('Injector hook executes', result.includes('system-reminder') || result.includes('SKILL'));
} catch (e) {
  check('Injector hook executes', false, e.message);
}

// Summary
console.log('\n=== Summary ===');
console.log(`Passed: ${passed}  Failed: ${failed}  Warnings: ${warnings}`);
if (failed === 0) {
  console.log('\nWorkflow bundle is healthy!');
} else {
  console.log('\nRun install-workflow.js to fix issues.');
}
