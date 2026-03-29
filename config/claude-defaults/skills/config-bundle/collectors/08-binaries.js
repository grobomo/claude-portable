/**
 * Collector: binaries — scripts and executables needed by workers
 * Copies key scripts from claude-portable that workers need at runtime.
 */
const fs = require('fs');
const path = require('path');

// Scripts workers need (relative to claude-portable/)
const WORKER_SCRIPTS = [
  'scripts/continuous-claude.sh',
  'scripts/spec-generate.sh',
];

// Scripts the dispatcher needs
const DISPATCHER_SCRIPTS = [
  'scripts/git-dispatch.py',
  'scripts/continuous-claude.sh',
  'scripts/spec-generate.sh',
];

module.exports = function collectBinaries(bundlePath, ctx) {
  const name = 'binaries';
  let files = 0;

  if (!ctx.PORTABLE_DIR) {
    return { name, ok: false, reason: 'claude-portable dir not found' };
  }

  const scripts = ctx.TARGET === 'worker' ? WORKER_SCRIPTS :
                  ctx.TARGET === 'dispatcher' ? DISPATCHER_SCRIPTS :
                  [...new Set([...WORKER_SCRIPTS, ...DISPATCHER_SCRIPTS])];

  const dst = path.join(bundlePath, 'scripts');
  fs.mkdirSync(dst, { recursive: true });

  for (const script of scripts) {
    const src = path.join(ctx.PORTABLE_DIR, script);
    if (fs.existsSync(src)) {
      const dstFile = path.join(dst, path.basename(script));
      fs.copyFileSync(src, dstFile);
      files++;
    }
  }

  return { name, ok: files > 0, files };
};
