/**
 * Collector: speckit-commands — spec-kit slash commands for workers
 * These go into the bundle's commands/ dir so workers can use /speckit.* commands.
 */
const fs = require('fs');
const path = require('path');

module.exports = function collectSpeckitCommands(bundlePath, ctx) {
  const name = 'speckit-commands';
  let files = 0;

  // Try hackathon26 commands first, fall back to DEFAULTS_DIR
  const sources = [
    ctx.HACKATHON_DIR ? path.join(ctx.HACKATHON_DIR, '.claude', 'commands') : null,
    path.join(ctx.DEFAULTS_DIR, 'commands'),
  ].filter(Boolean);

  const dst = path.join(bundlePath, 'commands');
  fs.mkdirSync(dst, { recursive: true });

  for (const src of sources) {
    if (!fs.existsSync(src)) continue;
    for (const file of fs.readdirSync(src)) {
      if (file.startsWith('speckit.') && file.endsWith('.md')) {
        const dstFile = path.join(dst, file);
        if (!fs.existsSync(dstFile)) { // don't overwrite if already copied
          fs.copyFileSync(path.join(src, file), dstFile);
          files++;
        }
      }
    }
  }

  return { name, ok: files > 0, files, skipped: files === 0 };
};
