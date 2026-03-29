/**
 * Collector: hackathon-context — project notes, specs, rules, and TODO from hackathon26.
 *
 * This gives workers (and teammates) full project context so they understand
 * the architecture, what's been built, what's left, and how components connect.
 *
 * Syncs from GitHub if HACKATHON_SYNC=1 (pull latest before bundling).
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Files/dirs to include from hackathon26
const INCLUDE = [
  { src: 'CLAUDE.md', dst: 'project-context/hackathon26/CLAUDE.md' },
  { src: 'TODO.md', dst: 'project-context/hackathon26/TODO.md' },
  { src: 'DEMO-RUNBOOK.md', dst: 'project-context/hackathon26/DEMO-RUNBOOK.md' },
  { src: '.claude/rules', dst: 'project-context/hackathon26/rules', dir: true },
  { src: '.claude/commands', dst: 'project-context/hackathon26/commands', dir: true },
  { src: '.specs', dst: 'project-context/hackathon26/specs', dir: true },
  { src: 'specs', dst: 'project-context/hackathon26/specs-wip', dir: true },
];

module.exports = function collectHackathonContext(bundlePath, ctx) {
  const name = 'hackathon-context';

  if (!ctx.HACKATHON_DIR || !fs.existsSync(ctx.HACKATHON_DIR)) {
    return { name, ok: false, skipped: true, reason: 'hackathon26 dir not found' };
  }

  // Optionally sync from GitHub first
  if (process.env.HACKATHON_SYNC === '1') {
    try {
      execSync('git pull --rebase origin main', {
        cwd: ctx.HACKATHON_DIR,
        stdio: 'pipe',
        timeout: 30000,
      });
    } catch (e) {
      // Non-fatal — use whatever's on disk
    }
  }

  let files = 0;

  for (const item of INCLUDE) {
    const srcPath = path.join(ctx.HACKATHON_DIR, item.src);
    const dstPath = path.join(bundlePath, item.dst);

    if (!fs.existsSync(srcPath)) continue;

    if (item.dir) {
      fs.mkdirSync(dstPath, { recursive: true });
      fs.cpSync(srcPath, dstPath, { recursive: true });
    } else {
      fs.mkdirSync(path.dirname(dstPath), { recursive: true });
      fs.copyFileSync(srcPath, dstPath);
    }
    files++;
  }

  // Generate a context summary that workers can read quickly
  const summary = generateContextSummary(ctx.HACKATHON_DIR);
  if (summary) {
    const summaryPath = path.join(bundlePath, 'project-context', 'CONTEXT-SUMMARY.md');
    fs.mkdirSync(path.dirname(summaryPath), { recursive: true });
    fs.writeFileSync(summaryPath, summary);
    files++;
  }

  return { name, ok: files > 0, files };
};

function generateContextSummary(hackathonDir) {
  const claudeMd = safeRead(path.join(hackathonDir, 'CLAUDE.md'));
  const todoMd = safeRead(path.join(hackathonDir, 'TODO.md'));

  if (!claudeMd) return null;

  // Extract key sections from CLAUDE.md
  const deadline = claudeMd.match(/\*\*(.+April.+2026)\*\*/)?.[1] || 'April 1, 2026';

  // Count remaining TODO items
  const remaining = (todoMd || '').match(/- \[ \]/g)?.length || 0;
  const completed = (todoMd || '').match(/- \[x\]/gi)?.length || 0;

  return `# Hackathon Project Context

**Deadline:** ${deadline}
**Progress:** ${completed} tasks done, ${remaining} remaining

## What You Need to Know

This bundle includes full project context from hackathon26 (the coordination workspace).
Read these files in order:

1. \`hackathon26/CLAUDE.md\` — Architecture, component map, data flow, team info
2. \`hackathon26/TODO.md\` — Current status, what's done, what's left
3. \`hackathon26/rules/\` — Operational rules (git creds, deployment, messaging)
4. \`hackathon26/specs/\` — Spec-kit artifacts for current features
5. \`hackathon26/commands/\` — Spec-kit slash commands

## Key Architecture Facts

- **BoothApp** = AI trade show demo capture (badge OCR -> session -> analysis -> follow-up)
- **CCC Fleet** = 1 dispatcher + 2 workers on AWS EC2 (Docker containers)
- **RONE** = Internal K8s running Teams chat poller
- **Bridge** = Git repo shuttling tasks between RONE and AWS CCC
- Workers code against \`altarr/boothapp\` repo using \`grobomo\` GitHub account
- Dispatcher uses \`tmemu\` account for bridge repo access

## How Workers Should Use This Context

When you receive a task:
1. Read the spec in \`.specs/\` (if provided)
2. Reference \`hackathon26/CLAUDE.md\` for architecture decisions
3. Check \`hackathon26/TODO.md\` to understand where your task fits
4. Follow GSD: create PLAN.md before implementation
5. Verify against spec success criteria before PR

Generated: ${new Date().toISOString()}
`;
}

function safeRead(filepath) {
  try { return fs.readFileSync(filepath, 'utf-8'); }
  catch { return null; }
}
