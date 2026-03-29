#!/usr/bin/env node
/**
 * install.js — Install a config-bundle onto the current machine.
 *
 * Reads manifest.json from the bundle directory, copies files to ~/.claude/,
 * expands $HOME in paths, and reports success/failure for each component.
 *
 * Usage:
 *   node install.js <bundle-dir>
 *   node install.js /tmp/config-bundle-worker-20260329
 */
const fs = require('fs');
const path = require('path');

const HOME = process.env.HOME || process.env.USERPROFILE;
const CLAUDE_DIR = path.join(HOME, '.claude');

function log(msg) { console.log(`[install] ${msg}`); }
function ok(msg) { console.log(`  [OK] ${msg}`); }
function fail(msg) { console.log(`  [XX] ${msg}`); }

function expandHome(str) {
  return str.replace(/\$HOME/g, HOME).replace(/\$\{HOME\}/g, HOME);
}

function copyDir(src, dst) {
  fs.mkdirSync(dst, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name);
    const d = path.join(dst, entry.name);
    if (entry.isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  }
}

function main() {
  const bundleDir = process.argv[2];
  if (!bundleDir || !fs.existsSync(bundleDir)) {
    log('Usage: node install.js <bundle-dir>');
    process.exit(1);
  }

  const manifestPath = path.join(bundleDir, 'manifest.json');
  if (!fs.existsSync(manifestPath)) {
    fail('manifest.json not found in bundle');
    process.exit(1);
  }

  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
  log(`Installing ${manifest.target} bundle (built ${manifest.built_at})`);
  log(`Target: ${CLAUDE_DIR}`);
  console.log('');

  fs.mkdirSync(CLAUDE_DIR, { recursive: true });
  let pass = 0, failed = 0;

  // 1. Hooks
  const hooksDir = path.join(bundleDir, 'hooks');
  if (fs.existsSync(hooksDir)) {
    try {
      copyDir(hooksDir, path.join(CLAUDE_DIR, 'hooks'));
      ok('hooks');
      pass++;
    } catch (e) { fail(`hooks: ${e.message}`); failed++; }
  }

  // 2. Settings
  const settingsFile = path.join(bundleDir, 'settings.json');
  if (fs.existsSync(settingsFile)) {
    try {
      let content = fs.readFileSync(settingsFile, 'utf-8');
      content = expandHome(content);
      // Merge with existing settings if present
      const existingPath = path.join(CLAUDE_DIR, 'settings.json');
      if (fs.existsSync(existingPath)) {
        const existing = JSON.parse(fs.readFileSync(existingPath, 'utf-8'));
        const incoming = JSON.parse(content);
        // Merge: incoming overwrites, but preserve existing env vars not in incoming
        if (existing.env && incoming.env) {
          incoming.env = { ...existing.env, ...incoming.env };
        }
        // Hooks: replace entirely with incoming
        content = JSON.stringify(incoming, null, 2);
      }
      fs.writeFileSync(path.join(CLAUDE_DIR, 'settings.json'), content);
      ok('settings.json');
      pass++;
    } catch (e) { fail(`settings.json: ${e.message}`); failed++; }
  }

  // 3. CLAUDE.md
  const claudeMd = path.join(bundleDir, 'CLAUDE.md');
  if (fs.existsSync(claudeMd)) {
    try {
      fs.copyFileSync(claudeMd, path.join(CLAUDE_DIR, 'CLAUDE.md'));
      ok('CLAUDE.md');
      pass++;
    } catch (e) { fail(`CLAUDE.md: ${e.message}`); failed++; }
  }

  // 4. Rules
  const rulesDir = path.join(bundleDir, 'rules');
  if (fs.existsSync(rulesDir)) {
    try {
      copyDir(rulesDir, path.join(CLAUDE_DIR, 'rules'));
      ok('rules');
      pass++;
    } catch (e) { fail(`rules: ${e.message}`); failed++; }
  }

  // 5. Skills
  const skillsDir = path.join(bundleDir, 'skills');
  if (fs.existsSync(skillsDir)) {
    try {
      copyDir(skillsDir, path.join(CLAUDE_DIR, 'skills'));
      ok('skills');
      pass++;
    } catch (e) { fail(`skills: ${e.message}`); failed++; }
  }

  // 6. Commands (speckit etc)
  const commandsDir = path.join(bundleDir, 'commands');
  if (fs.existsSync(commandsDir)) {
    try {
      copyDir(commandsDir, path.join(CLAUDE_DIR, 'commands'));
      ok('commands');
      pass++;
    } catch (e) { fail(`commands: ${e.message}`); failed++; }
  }

  // 7. Project context (hackathon notes)
  const contextDir = path.join(bundleDir, 'project-context');
  if (fs.existsSync(contextDir)) {
    try {
      // Install to ~/.claude/project-context/ so claude can reference it
      copyDir(contextDir, path.join(CLAUDE_DIR, 'project-context'));

      // Also create a rule pointing to it
      const ruleContent = `# Hackathon Project Context

Full project context is available at ~/.claude/project-context/hackathon26/.
Read CONTEXT-SUMMARY.md first, then CLAUDE.md for architecture details.
Reference TODO.md to understand where your current task fits in the bigger picture.
`;
      fs.mkdirSync(path.join(CLAUDE_DIR, 'rules'), { recursive: true });
      fs.writeFileSync(
        path.join(CLAUDE_DIR, 'rules', 'hackathon-project-context.md'),
        ruleContent
      );
      ok('project-context (hackathon26)');
      pass++;
    } catch (e) { fail(`project-context: ${e.message}`); failed++; }
  }

  // 8. Scripts/binaries
  const scriptsDir = path.join(bundleDir, 'scripts');
  if (fs.existsSync(scriptsDir)) {
    try {
      const target = '/opt/claude-portable/scripts';
      if (fs.existsSync(path.dirname(target))) {
        copyDir(scriptsDir, target);
        // Make executable
        for (const f of fs.readdirSync(target)) {
          try { fs.chmodSync(path.join(target, f), 0o755); } catch {}
        }
      } else {
        // Fallback: put in ~/.claude/scripts/
        copyDir(scriptsDir, path.join(CLAUDE_DIR, 'scripts'));
      }
      ok('scripts');
      pass++;
    } catch (e) { fail(`scripts: ${e.message}`); failed++; }
  }

  // Summary
  console.log('');
  log(`=== Install Complete: ${pass} passed, ${failed} failed ===`);

  if (failed > 0) process.exit(1);
}

main();
