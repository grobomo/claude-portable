/**
 * Collector: skills — selected skills based on target
 */
const fs = require('fs');
const path = require('path');

// Skills relevant for CCC workers
const WORKER_SKILLS = [
  'auto-gsd',
  'code-review',
  'config-bundle',
];

// Additional skills for teammates
const TEAMMATE_SKILLS = [
  'auto-gsd',
  'code-review',
  'config-bundle',
  'hook-manager',
  'rule-manager',
  'skill-manager',
  'project-maker',
];

// Full = everything
const selectSkills = (target, available) => {
  if (target === 'full') return available;
  const wanted = target === 'teammate' ? TEAMMATE_SKILLS : WORKER_SKILLS;
  return available.filter(s => wanted.includes(s));
};

module.exports = function collectSkills(bundlePath, ctx) {
  const name = 'skills';
  const src = path.join(ctx.DEFAULTS_DIR, 'skills');
  const dst = path.join(bundlePath, 'skills');
  let files = 0;

  if (!fs.existsSync(src)) {
    return { name, ok: false, reason: 'skills dir not found' };
  }

  const available = fs.readdirSync(src).filter(d =>
    fs.statSync(path.join(src, d)).isDirectory()
  );
  const selected = selectSkills(ctx.TARGET, available);

  fs.mkdirSync(dst, { recursive: true });

  for (const skill of selected) {
    // Skip self to avoid recursive copy when bundling from inside config-bundle
    if (skill === 'config-bundle') {
      // Copy only SKILL.md and install.js (not the output/ dir or collectors)
      const selfSrc = path.join(src, skill);
      const selfDst = path.join(dst, skill);
      fs.mkdirSync(selfDst, { recursive: true });
      for (const f of ['SKILL.md', 'install.js', 'bundle.js', 'health-check.js']) {
        const s = path.join(selfSrc, f);
        if (fs.existsSync(s)) fs.copyFileSync(s, path.join(selfDst, f));
      }
      // Copy collectors
      const collSrc = path.join(selfSrc, 'collectors');
      if (fs.existsSync(collSrc)) {
        fs.cpSync(collSrc, path.join(selfDst, 'collectors'), { recursive: true });
      }
      files++;
      continue;
    }
    const skillSrc = path.join(src, skill);
    const skillDst = path.join(dst, skill);
    if (fs.existsSync(skillSrc)) {
      fs.cpSync(skillSrc, skillDst, { recursive: true });
      files++;
    }
  }

  return { name, ok: files > 0, files, skipped: available.length - selected.length };
};
