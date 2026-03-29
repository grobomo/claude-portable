/**
 * Collector: settings — settings.json with desktop stripping
 */
const fs = require('fs');
const path = require('path');

// Desktop-only env vars to strip
const DESKTOP_ENV_KEYS = [
  'GOOGLE_GEMINI_BASE_URL',
  'NANO_BANANA_MODEL',
];

// Desktop-only top-level keys to strip
const DESKTOP_TOP_KEYS = [
  'extraKnownMarketplaces',
  'enabledPlugins',
  'autoUpdatesChannel',
  'voiceEnabled',
];

module.exports = function collectSettings(bundlePath, ctx) {
  const name = 'settings';
  const src = path.join(ctx.DEFAULTS_DIR, 'settings.json');
  const dst = path.join(bundlePath, 'settings.json');

  if (!fs.existsSync(src)) {
    return { name, ok: false, reason: 'settings.json not found' };
  }

  const settings = JSON.parse(fs.readFileSync(src, 'utf-8'));

  if (ctx.STRIP_DESKTOP) {
    // Strip desktop-only env vars
    if (settings.env) {
      for (const k of DESKTOP_ENV_KEYS) {
        delete settings.env[k];
      }
    }
    // Strip desktop-only top-level keys
    for (const k of DESKTOP_TOP_KEYS) {
      delete settings[k];
    }
  }

  // Sanitize hook paths to use $HOME (portable across systems)
  const raw = JSON.stringify(settings);
  const sanitized = raw
    .replace(/C:\/Users\/[^"]+\/.claude/gi, '$HOME/.claude')
    .replace(/\/c\/Users\/[^"]+\/.claude/gi, '$HOME/.claude')
    .replace(/C:\\\\Users\\\\[^"]+\\\\.claude/gi, '$HOME/.claude');

  fs.writeFileSync(dst, JSON.stringify(JSON.parse(sanitized), null, 2));

  return { name, ok: true, files: 1 };
};
