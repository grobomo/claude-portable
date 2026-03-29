#!/usr/bin/env node
/**
 * bundle.js — Single entry point for building a portable Claude Code environment bundle.
 *
 * Collects hooks, settings, skills, rules, CLAUDE.md, and project context into
 * a single folder, then zips it for SCP deployment to CCC workers or teammates.
 *
 * Environment:
 *   BUNDLE_OUTPUT     Output directory (default: ./output)
 *   BUNDLE_TARGET     "worker" | "teammate" | "full" (default: worker)
 *   HACKATHON_DIR     Path to hackathon26 project (auto-detected)
 *   PORTABLE_DIR      Path to claude-portable project (auto-detected)
 *   STRIP_DESKTOP     "1" to strip desktop-only settings (default: 1)
 *
 * Usage:
 *   node bundle.js                          # worker bundle (default)
 *   BUNDLE_TARGET=teammate node bundle.js   # teammate bundle (includes more skills)
 *   BUNDLE_TARGET=full node bundle.js       # everything
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// ── Config ────────────────────────────────────────────────────────────────────
const HOME = process.env.HOME || process.env.USERPROFILE;
const TARGET = process.env.BUNDLE_TARGET || 'worker';
const STRIP_DESKTOP = process.env.STRIP_DESKTOP !== '0';

// Auto-detect project paths
const SCRIPT_DIR = __dirname;
const PORTABLE_DIR = process.env.PORTABLE_DIR || findProjectDir('claude-portable');
const HACKATHON_DIR = process.env.HACKATHON_DIR || findProjectDir('hackathon26');
const DEFAULTS_DIR = PORTABLE_DIR ? path.join(PORTABLE_DIR, 'config', 'claude-defaults') : null;

const OUTPUT_DIR = process.env.BUNDLE_OUTPUT || path.join(SCRIPT_DIR, 'output');
const TIMESTAMP = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '').slice(0, 8);
const BUNDLE_NAME = `config-bundle-${TARGET}-${TIMESTAMP}`;
const BUNDLE_PATH = path.join(OUTPUT_DIR, BUNDLE_NAME);

// ── Helpers ───────────────────────────────────────────────────────────────────
function findProjectDir(name) {
  // Walk up from this script to find ProjectsCL1, then look for the project
  const candidates = [
    path.join(HOME, 'Documents', 'ProjectsCL1', name),
    path.join('/workspace', name),
    path.join(SCRIPT_DIR, '..', '..', '..', '..', '..', name),
  ];
  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  return null;
}

function log(msg) { console.log(`[bundle] ${msg}`); }
function ok(msg) { console.log(`  [OK] ${msg}`); }
function skip(msg) { console.log(`  [--] ${msg}`); }
function warn(msg) { console.log(`  [!!] ${msg}`); }
function fail(msg) { console.log(`  [XX] ${msg}`); }

function copyFile(src, dst) {
  if (!fs.existsSync(src)) return false;
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  fs.copyFileSync(src, dst);
  return true;
}

function copyDir(src, dst) {
  if (!fs.existsSync(src)) return false;
  fs.mkdirSync(dst, { recursive: true });
  fs.cpSync(src, dst, { recursive: true });
  return true;
}

function countFiles(dir) {
  if (!fs.existsSync(dir)) return 0;
  let count = 0;
  const walk = (d) => {
    for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
      if (entry.isDirectory()) walk(path.join(d, entry.name));
      else count++;
    }
  };
  walk(dir);
  return count;
}

// ── Collectors ────────────────────────────────────────────────────────────────
// Each collector is a function(bundlePath, target) that returns {name, ok, files, skipped}

const collectors = [];
function registerCollector(fn) { collectors.push(fn); }

// Load all collectors from ./collectors/
const collectorsDir = path.join(SCRIPT_DIR, 'collectors');
if (fs.existsSync(collectorsDir)) {
  for (const file of fs.readdirSync(collectorsDir).sort()) {
    if (file.endsWith('.js')) {
      const collector = require(path.join(collectorsDir, file));
      if (typeof collector === 'function') {
        registerCollector(collector);
      }
    }
  }
}

// ── Main ──────────────────────────────────────────────────────────────────────
function main() {
  log(`Building ${TARGET} bundle...`);
  log(`Defaults: ${DEFAULTS_DIR || 'NOT FOUND'}`);
  log(`Hackathon: ${HACKATHON_DIR || 'NOT FOUND'}`);
  log(`Output: ${BUNDLE_PATH}`);
  console.log('');

  if (!DEFAULTS_DIR || !fs.existsSync(DEFAULTS_DIR)) {
    fail('claude-portable/config/claude-defaults not found. Set PORTABLE_DIR.');
    process.exit(1);
  }

  // Clean and create
  if (fs.existsSync(BUNDLE_PATH)) {
    fs.rmSync(BUNDLE_PATH, { recursive: true });
  }
  fs.mkdirSync(BUNDLE_PATH, { recursive: true });

  // Run all collectors
  const results = [];
  const ctx = { DEFAULTS_DIR, HACKATHON_DIR, PORTABLE_DIR, HOME, TARGET, STRIP_DESKTOP };

  for (const collector of collectors) {
    try {
      const result = collector(BUNDLE_PATH, ctx);
      results.push(result);
      if (result.ok) {
        ok(`${result.name}: ${result.files || 0} files`);
      } else if (result.skipped) {
        skip(`${result.name}: ${result.reason || 'skipped'}`);
      } else {
        warn(`${result.name}: ${result.reason || 'failed'}`);
      }
    } catch (e) {
      fail(`Collector error: ${e.message}`);
      results.push({ name: 'unknown', ok: false, reason: e.message });
    }
  }

  // Write manifest
  const manifest = {
    built_at: new Date().toISOString(),
    target: TARGET,
    source_host: require('os').hostname(),
    strip_desktop: STRIP_DESKTOP,
    files: countFiles(BUNDLE_PATH),
    collectors: results.map(r => ({ name: r.name, ok: r.ok, files: r.files || 0 })),
    install: 'node install.js [bundle-dir]',
  };
  fs.writeFileSync(path.join(BUNDLE_PATH, 'manifest.json'), JSON.stringify(manifest, null, 2));

  // Copy installer into bundle
  const installerSrc = path.join(SCRIPT_DIR, 'install.js');
  if (fs.existsSync(installerSrc)) {
    fs.copyFileSync(installerSrc, path.join(BUNDLE_PATH, 'install.js'));
  }

  // Create zip/tar.gz
  console.log('');
  log('Packaging...');
  let archivePath = null;
  const tarPath = `${BUNDLE_PATH}.tar.gz`;
  const zipPath = `${BUNDLE_PATH}.zip`;

  // Try multiple archivers — Windows ships tar.exe since Win10
  // Windows bsdtar lives at C:\Windows\System32\tar.exe
  const winTar = 'C:\\Windows\\System32\\tar.exe';
  const archivers = [
    { cmd: `"${winTar}" -czf "${tarPath}" -C "${OUTPUT_DIR}" "${BUNDLE_NAME}"`, out: tarPath, shell: true },
    { cmd: `tar czf "${tarPath}" -C "${OUTPUT_DIR}" "${BUNDLE_NAME}"`, out: tarPath },
    { cmd: `powershell -NoProfile -Command "Compress-Archive -Path '${BUNDLE_PATH}' -DestinationPath '${zipPath}' -Force"`, out: zipPath },
  ];
  for (const { cmd, out, shell } of archivers) {
    try {
      execSync(cmd, { stdio: 'pipe', timeout: 60000, shell: shell ? 'cmd.exe' : undefined });
      if (fs.existsSync(out)) {
        archivePath = out;
        ok(`${path.basename(out)} (${getSize(out)})`);
        break;
      }
    } catch { /* try next */ }
  }
  if (!archivePath) {
    warn('No archiver available — bundle dir left in place');
  }

  // Summary
  console.log('');
  log('=== Bundle Complete ===');
  log(`Target: ${TARGET}`);
  log(`Files: ${manifest.files}`);
  log(`Collectors: ${results.filter(r => r.ok).length}/${results.length} succeeded`);
  if (archivePath) {
    log(`Archive: ${archivePath}`);
    const ext = archivePath.endsWith('.tar.gz') ? 'tar.gz' : 'zip';
    const extractCmd = ext === 'tar.gz'
      ? `tar xzf /tmp/${path.basename(archivePath)} -C /tmp/`
      : `cd /tmp && unzip -qo ${path.basename(archivePath)}`;
    log(`Deploy: scp ${path.basename(archivePath)} ubuntu@<host>:/tmp/ && ssh ubuntu@<host> "docker cp /tmp/${path.basename(archivePath)} claude-portable:/tmp/ && docker exec claude-portable bash -c '${extractCmd} && node /tmp/${BUNDLE_NAME}/install.js /tmp/${BUNDLE_NAME}'"`);
  } else {
    log(`Bundle dir: ${BUNDLE_PATH}`);
  }

  // Cleanup staging dir (keep the archive)
  if (archivePath && fs.existsSync(archivePath)) {
    fs.rmSync(BUNDLE_PATH, { recursive: true });
  }
}

function getSize(filepath) {
  const stats = fs.statSync(filepath);
  if (stats.size < 1024) return `${stats.size}B`;
  if (stats.size < 1024 * 1024) return `${(stats.size / 1024).toFixed(1)}KB`;
  return `${(stats.size / (1024 * 1024)).toFixed(1)}MB`;
}

main();
