/**
 * Collector: rules — Claude instruction rules, filtered for target
 */
const fs = require('fs');
const path = require('path');

// Rules that only make sense on desktop (not for workers/teammates on Linux containers)
const DESKTOP_ONLY_RULES = [
  'blueprint-auto-enable.md',
  'blueprint-mcp.md',
  'build-output-paths.md',
  'claude-config.md',
  'credential-clipboard.md',
  'idle-timeout-source.md',
  'messaging-safety.md',
  'msgraph-tools.md',
  'scheduler-health-check.md',
];

module.exports = function collectRules(bundlePath, ctx) {
  const name = 'rules';
  const src = path.join(ctx.DEFAULTS_DIR, 'rules');
  const dst = path.join(bundlePath, 'rules');
  let files = 0;
  let skipped = 0;

  if (!fs.existsSync(src)) {
    return { name, ok: false, reason: 'rules dir not found' };
  }

  fs.mkdirSync(dst, { recursive: true });

  // Copy files, optionally filtering desktop-only
  const entries = fs.readdirSync(src, { withFileTypes: true });
  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const dstPath = path.join(dst, entry.name);

    if (entry.isDirectory()) {
      // Copy subdirectories (e.g., Stop/)
      fs.cpSync(srcPath, dstPath, { recursive: true });
      files++;
      continue;
    }

    if (ctx.STRIP_DESKTOP && DESKTOP_ONLY_RULES.includes(entry.name)) {
      skipped++;
      continue;
    }

    fs.copyFileSync(srcPath, dstPath);
    files++;
  }

  return { name, ok: files > 0, files, skipped };
};
