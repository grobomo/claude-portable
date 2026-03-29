#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

const HOME = process.env.HOME || process.env.USERPROFILE;
const CLAUDE_DIR = path.join(HOME, '.claude');
const HOOKS_DIR = path.join(CLAUDE_DIR, 'hooks');
const SKILLS_DIR = path.join(CLAUDE_DIR, 'skills');
const SETTINGS_PATH = path.join(CLAUDE_DIR, 'settings.json');

function log(msg) { console.log('[install] ' + msg); }
function logOK(msg) { console.log('  [OK] ' + msg); }
function logErr(msg) { console.log('  [XX] ' + msg); }

function expandPath(p) {
  var result = p.replace(/\$\{HOME\}/g, HOME);
  var bs = String.fromCharCode(92);
  return result.split(bs).join('/');
}

async function main() {
  const bundlePath = process.argv[2];
  if (!bundlePath) { log('Usage: node install-workflow.js <bundle-dir>'); process.exit(1); }
  
  const sourceDir = bundlePath;
  if (!fs.existsSync(sourceDir)) { logErr('Bundle not found: ' + sourceDir); process.exit(1); }
  
  const manifestPath = path.join(sourceDir, 'manifest.json');
  if (!fs.existsSync(manifestPath)) { logErr('manifest.json not found'); process.exit(1); }
  
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'));
  log('Installing bundle: ' + manifest.exported_at);
  
  fs.mkdirSync(HOOKS_DIR, { recursive: true });
  fs.mkdirSync(SKILLS_DIR, { recursive: true });
  
  const hooksSource = path.join(sourceDir, 'hooks');
  if (fs.existsSync(hooksSource)) {
    for (const file of fs.readdirSync(hooksSource)) {
      fs.copyFileSync(path.join(hooksSource, file), path.join(HOOKS_DIR, file));
      logOK('Installed hook: ' + file);
    }
  }
  
  const registrySource = path.join(sourceDir, 'registries', 'skill-registry.json');
  if (fs.existsSync(registrySource)) {
    fs.copyFileSync(registrySource, path.join(HOOKS_DIR, 'skill-registry.json'));
    logOK('Installed skill-registry.json');
  }
  
  const skillsSource = path.join(sourceDir, 'skills');
  if (fs.existsSync(skillsSource)) {
    for (const skill of fs.readdirSync(skillsSource)) {
      fs.cpSync(path.join(skillsSource, skill), path.join(SKILLS_DIR, skill), { recursive: true });
      logOK('Installed skill: ' + skill);
    }
  }
  
  const configSource = path.join(sourceDir, 'config', 'hooks-config.json');
  if (fs.existsSync(configSource)) {
    const hooksConfig = JSON.parse(fs.readFileSync(configSource, 'utf-8'));
    let settings = fs.existsSync(SETTINGS_PATH) ? JSON.parse(fs.readFileSync(SETTINGS_PATH, 'utf-8')) : {};
    
    if (hooksConfig.hooks) {
      settings.hooks = settings.hooks || {};
      for (const [event, eventHooks] of Object.entries(hooksConfig.hooks)) {
        settings.hooks[event] = eventHooks.map(hook => ({
          ...hook,
          hooks: hook.hooks.map(h => ({ ...h, command: expandPath(h.command) }))
        }));
      }
    }
    
    fs.writeFileSync(SETTINGS_PATH, JSON.stringify(settings, null, 2));
    logOK('Installed hooks config');
  }
  
  log('Installation complete!');
}

main().catch(e => { logErr(e.message); process.exit(1); });
