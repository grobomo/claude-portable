#!/usr/bin/env node
/**
 * export-workflow.js - Export current Claude Code workflow to portable bundle
 * 
 * Exports: hooks, registries, settings config, GSD skills
 * Output: workflow-export-YYYYMMDD.zip
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const HOME = process.env.HOME || process.env.USERPROFILE;
const BUNDLE_DIR = path.join(HOME, '.claude', 'skills', 'workflow-bundle');
const HOOKS_DIR = path.join(HOME, '.claude', 'hooks');
const SKILLS_DIR = path.join(HOME, '.claude', 'skills');

// Hooks to export (core workflow hooks)
const CORE_HOOKS = [
  'skill-mcp-claudemd-injector.js',
  'auto-gsd.js',
  'hook-logger.js',
  'preference-learner.js',
  'gsd-check-update.js',
  'gsd-gate.js',
  'gsd-intel-session.js',
  'gsd-statusline.js'
];

// Skills to export
const CORE_SKILLS = [
  'injector-manager',
  'gsd'  // GSD commands
];

function log(msg) { console.log(`[export] ${msg}`); }
function logOK(msg) { console.log(`  [OK] ${msg}`); }
function logWarn(msg) { console.log(`  [!!] ${msg}`); }

async function main() {
  const timestamp = new Date().toISOString().slice(0, 10).replace(/-/g, '');
  const exportDir = path.join(BUNDLE_DIR, `export-${timestamp}`);
  
  log(`Exporting workflow to ${exportDir}`);
  
  // Create export directories
  fs.mkdirSync(path.join(exportDir, 'hooks'), { recursive: true });
  fs.mkdirSync(path.join(exportDir, 'registries'), { recursive: true });
  fs.mkdirSync(path.join(exportDir, 'config'), { recursive: true });
  fs.mkdirSync(path.join(exportDir, 'skills'), { recursive: true });
  
  // Export hooks
  log('Exporting hooks...');
  for (const hook of CORE_HOOKS) {
    const src = path.join(HOOKS_DIR, hook);
    const dst = path.join(exportDir, 'hooks', hook);
    if (fs.existsSync(src)) {
      fs.copyFileSync(src, dst);
      logOK(hook);
    } else {
      logWarn(`${hook} not found`);
    }
  }
  
  // Export skill registry
  log('Exporting registries...');
  const registrySrc = path.join(HOOKS_DIR, 'skill-registry.json');
  if (fs.existsSync(registrySrc)) {
    // Sanitize paths to be relative
    const registry = JSON.parse(fs.readFileSync(registrySrc, 'utf-8'));
    for (const skill of registry.skills || []) {
      if (skill.skillPath) {
        // Convert to relative path placeholder
        skill.skillPath = skill.skillPath
          .replace(/C:\/Users\/[^/]+/gi, '${HOME}')
          .replace(/\/c\/Users\/[^/]+/gi, '${HOME}');
      }
    }
    fs.writeFileSync(
      path.join(exportDir, 'registries', 'skill-registry.json'),
      JSON.stringify(registry, null, 2)
    );
    logOK('skill-registry.json (paths sanitized)');
  }
  
  // Export hooks config from settings.json
  log('Exporting config...');
  const settingsPath = path.join(HOME, '.claude', 'settings.json');
  if (fs.existsSync(settingsPath)) {
    const settings = JSON.parse(fs.readFileSync(settingsPath, 'utf-8'));
    const hooksConfig = { hooks: settings.hooks || {} };
    
    // Sanitize paths
    const sanitized = JSON.stringify(hooksConfig)
      .replace(/C:\/Users\/[^"]+\/.claude/gi, '${HOME}/.claude')
      .replace(/\/c\/Users\/[^"]+\/.claude/gi, '${HOME}/.claude');
    
    fs.writeFileSync(
      path.join(exportDir, 'config', 'hooks-config.json'),
      JSON.stringify(JSON.parse(sanitized), null, 2)
    );
    logOK('hooks-config.json (paths sanitized)');
  }
  
  // Export GSD skills if present
  log('Exporting GSD skills...');
  const gsdDir = path.join(SKILLS_DIR, 'gsd');
  if (fs.existsSync(gsdDir)) {
    execSync(`cp -r "${gsdDir}" "${path.join(exportDir, 'skills', 'gsd')}"`, { stdio: 'inherit' });
    logOK('gsd/ skill folder');
  } else {
    logWarn('GSD skills not found');
  }
  
  // Export injector-manager
  const injectorDir = path.join(SKILLS_DIR, 'injector-manager');
  if (fs.existsSync(injectorDir)) {
    execSync(`cp -r "${injectorDir}" "${path.join(exportDir, 'skills', 'injector-manager')}"`, { stdio: 'inherit' });
    logOK('injector-manager/ skill folder');
  }
  
  // Create manifest
  const manifest = {
    version: '1.0.0',
    exported: new Date().toISOString(),
    components: {
      hooks: CORE_HOOKS.filter(h => fs.existsSync(path.join(exportDir, 'hooks', h))),
      registries: ['skill-registry.json'],
      config: ['hooks-config.json'],
      skills: fs.readdirSync(path.join(exportDir, 'skills'))
    }
  };
  fs.writeFileSync(
    path.join(exportDir, 'manifest.json'),
    JSON.stringify(manifest, null, 2)
  );
  logOK('manifest.json');
  
  // Create zip
  log('Creating zip archive...');
  const zipName = `workflow-export-${timestamp}.zip`;
  try {
    execSync(`cd "${BUNDLE_DIR}" && zip -r "${zipName}" "export-${timestamp}"`, { stdio: 'pipe' });
    logOK(zipName);
    
    // Cleanup temp dir
    execSync(`rm -rf "${exportDir}"`, { stdio: 'pipe' });
    
    console.log(`\n=== Export Complete ===`);
    console.log(`Bundle: ${path.join(BUNDLE_DIR, zipName)}`);
    console.log(`\nTo install on fresh system:`);
    console.log(`  node install-workflow.js ${zipName}`);
  } catch (e) {
    console.log(`\nExport dir: ${exportDir}`);
    console.log('(zip not available, directory left in place)');
  }
}

main().catch(e => { console.error(e); process.exit(1); });
