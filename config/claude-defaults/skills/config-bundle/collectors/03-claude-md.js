/**
 * Collector: claude-md — CLAUDE.md worker instructions
 */
const fs = require('fs');
const path = require('path');

module.exports = function collectClaudeMd(bundlePath, ctx) {
  const name = 'claude-md';
  const src = path.join(ctx.DEFAULTS_DIR, 'CLAUDE.md');
  const dst = path.join(bundlePath, 'CLAUDE.md');

  if (!fs.existsSync(src)) {
    return { name, ok: false, reason: 'CLAUDE.md not found' };
  }

  fs.copyFileSync(src, dst);
  return { name, ok: true, files: 1 };
};
