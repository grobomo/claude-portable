#!/usr/bin/env node
/**
 * Verifies injector hook is properly configured
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const HOME = process.env.HOME || process.env.USERPROFILE;
const HOOK_FILE = path.join(HOME, '.claude', 'hooks', 'skill-mcp-claudemd-injector.js');
const SETTINGS_FILE = path.join(HOME, '.claude', 'settings.json');
const SKILL_REGISTRY = path.join(HOME, '.claude', 'hooks', 'skill-registry.json');

const checks = [];

// Check 1: Hook file exists
if (fs.existsSync(HOOK_FILE)) {
  checks.push({ name: 'Hook file exists', status: 'OK' });
} else {
  checks.push({ name: 'Hook file exists', status: 'FAIL', fix: 'Run /injector-setup to install' });
}

// Check 2: Hook in settings.json
try {
  const settings = JSON.parse(fs.readFileSync(SETTINGS_FILE, 'utf-8'));
  const hooks = settings.hooks?.UserPromptSubmit?.[0]?.hooks || [];
  const hasHook = hooks.some(h => (h.command || '').includes('skill-mcp-claudemd-injector'));
  checks.push({ 
    name: 'Hook in settings.json', 
    status: hasHook ? 'OK' : 'FAIL',
    fix: hasHook ? null : 'Add hook to settings.json UserPromptSubmit'
  });
} catch (e) {
  checks.push({ name: 'Hook in settings.json', status: 'FAIL', fix: 'settings.json parse error' });
}

// Check 3: Skill registry exists
if (fs.existsSync(SKILL_REGISTRY)) {
  try {
    const reg = JSON.parse(fs.readFileSync(SKILL_REGISTRY, 'utf-8'));
    const count = (reg.skills || []).filter(s => s.enabled).length;
    checks.push({ name: 'Skill registry', status: 'OK', info: `${count} skills enabled` });
  } catch (e) {
    checks.push({ name: 'Skill registry', status: 'WARN', fix: 'Invalid JSON' });
  }
} else {
  checks.push({ name: 'Skill registry', status: 'WARN', fix: 'No skill-registry.json (skills wont inject)' });
}

// Check 4: Test hook execution
try {
  const result = execSync(`echo '{"prompt":"test"}' | node "${HOOK_FILE}"`, { encoding: 'utf-8', timeout: 5000 });
  checks.push({ name: 'Hook executes', status: 'OK' });
} catch (e) {
  checks.push({ name: 'Hook executes', status: 'FAIL', fix: e.message });
}

// Output results
console.log('\n=== Injector Health Check ===\n');
for (const c of checks) {
  const icon = c.status === 'OK' ? '[OK]' : c.status === 'WARN' ? '[!!]' : '[XX]';
  console.log(`${icon} ${c.name}`);
  if (c.info) console.log(`    ${c.info}`);
  if (c.fix) console.log(`    Fix: ${c.fix}`);
}
console.log('');
