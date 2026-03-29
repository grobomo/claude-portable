/**
 * Collector: hooks — hook runners + modules
 * Copies run-pretooluse.js, run-posttooluse.js, run-stop.js and their modules.
 */
const fs = require('fs');
const path = require('path');

module.exports = function collectHooks(bundlePath, ctx) {
  const name = 'hooks';
  const src = path.join(ctx.DEFAULTS_DIR, 'hooks');
  const dst = path.join(bundlePath, 'hooks');
  let files = 0;

  if (!fs.existsSync(src)) {
    return { name, ok: false, reason: 'hooks dir not found' };
  }

  fs.mkdirSync(dst, { recursive: true });

  // Copy hook runners
  for (const runner of ['run-pretooluse.js', 'run-posttooluse.js', 'run-stop.js']) {
    const s = path.join(src, runner);
    if (fs.existsSync(s)) {
      fs.copyFileSync(s, path.join(dst, runner));
      files++;
    }
  }

  // Copy hook modules (preserving directory structure)
  const modulesDir = path.join(src, 'run-modules');
  if (fs.existsSync(modulesDir)) {
    for (const event of fs.readdirSync(modulesDir)) {
      const eventDir = path.join(modulesDir, event);
      if (!fs.statSync(eventDir).isDirectory()) continue;
      const dstEventDir = path.join(dst, 'run-modules', event);
      fs.mkdirSync(dstEventDir, { recursive: true });
      for (const mod of fs.readdirSync(eventDir)) {
        if (mod.endsWith('.js')) {
          fs.copyFileSync(path.join(eventDir, mod), path.join(dstEventDir, mod));
          files++;
        }
      }
    }
  }

  return { name, ok: files > 0, files };
};
