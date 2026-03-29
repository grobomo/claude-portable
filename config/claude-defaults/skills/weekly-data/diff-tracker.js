#!/usr/bin/env node
/**
 * diff-tracker.js — Detects user edits to the weekly update report.
 * Compares current report against last generated version, classifies changes,
 * and writes corrections back to source files and corrections/ folder.
 *
 * Usage:
 *   node diff-tracker.js                        # Auto-detect report, diff, apply
 *   node diff-tracker.js --report <path>        # Specific report file
 *   node diff-tracker.js --dry-run              # Show diffs, don't write corrections
 *
 * Called by: weekly-update skill before generating a new report.
 * Also useful manually after editing the report.
 */

const fs = require('fs');
const path = require('path');

const SKILL_DIR = __dirname;
const CONFIG_FILE = path.join(SKILL_DIR, 'config.json');

function loadConfig() {
  if (!fs.existsSync(CONFIG_FILE)) return null;
  return JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf-8'));
}

function getWeekDir(root) {
  const now = new Date();
  const day = now.getDay();
  const fri = new Date(now);
  fri.setDate(now.getDate() + (5 - (day === 0 ? 7 : day)));
  return path.join(root, 'reports', 'weekly-data', fri.toISOString().slice(0, 10));
}

// ─── Diff Engine ──────────────────────────────────────────────────

function findReport(projectRoot) {
  const reportsDir = path.join(projectRoot, 'reports');
  const files = fs.readdirSync(reportsDir)
    .filter(f => f.startsWith('weekly-update--') && f.endsWith('.md'))
    .sort()
    .reverse();
  return files.length ? path.join(reportsDir, files[0]) : null;
}

function parseReportSections(content) {
  // Parse the report into structured sections
  const sections = {};
  let currentQ = null;

  for (const line of content.split('\n')) {
    if (line.match(/^## 1\./)) { currentQ = 'q1'; sections.q1 = []; continue; }
    if (line.match(/^## 2\./)) { currentQ = 'q2'; sections.q2 = []; continue; }
    if (line.match(/^## 3\./)) { currentQ = 'q3'; sections.q3 = []; continue; }
    if (currentQ && line.trim()) sections[currentQ]?.push(line);
  }

  return sections;
}

function extractCustomerBullets(lines) {
  // Extract "- **Customer** — content" bullets
  const bullets = {};
  for (const line of lines) {
    const m = line.match(/^- \*\*(.+?)\*\*\s*[—–-]\s*(.+)/);
    if (m) bullets[m[1].trim()] = m[2].trim();
  }
  return bullets;
}

function diffReports(generated, current) {
  const genSections = parseReportSections(generated);
  const curSections = parseReportSections(current);
  const diffs = [];

  // Q1: Compare customer bullets
  const genQ1 = extractCustomerBullets(genSections.q1 || []);
  const curQ1 = extractCustomerBullets(curSections.q1 || []);

  // Customers removed by user
  for (const [cust, text] of Object.entries(genQ1)) {
    if (!curQ1[cust]) {
      diffs.push({
        type: 'removed_customer',
        section: 'q1',
        customer: cust,
        generated: text,
        reason: 'User removed — likely not significant enough for weekly update'
      });
    }
  }

  // Customers modified by user
  for (const [cust, text] of Object.entries(curQ1)) {
    if (genQ1[cust] && genQ1[cust] !== text) {
      diffs.push({
        type: 'modified_customer',
        section: 'q1',
        customer: cust,
        generated: genQ1[cust],
        edited: text,
        reason: 'User corrected description'
      });
    }
  }

  // Customers added by user
  for (const [cust, text] of Object.entries(curQ1)) {
    if (!genQ1[cust]) {
      diffs.push({
        type: 'added_customer',
        section: 'q1',
        customer: cust,
        edited: text,
        reason: 'User added — AI missed this activity'
      });
    }
  }

  // Q2: Compare raw text (structural changes)
  const genQ2 = (genSections.q2 || []).join('\n').trim();
  const curQ2 = (curSections.q2 || []).join('\n').trim();
  if (genQ2 !== curQ2) {
    diffs.push({
      type: 'modified_section',
      section: 'q2',
      generated: genQ2.slice(0, 500),
      edited: curQ2.slice(0, 500),
      reason: 'User restructured next week plan'
    });
  }

  // Q3: Compare raw text
  const genQ3 = (genSections.q3 || []).join('\n').trim();
  const curQ3 = (curSections.q3 || []).join('\n').trim();
  if (genQ3 !== curQ3) {
    diffs.push({
      type: 'modified_section',
      section: 'q3',
      generated: genQ3.slice(0, 500),
      edited: curQ3.slice(0, 500),
      reason: 'User restructured demos/projects section'
    });
  }

  return diffs;
}

// ─── Correction Writer ────────────────────────────────────────────

function applyCorrections(diffs, weekDir, dryRun) {
  const correctionsDir = path.join(weekDir, 'corrections');
  const customersFile = path.join(correctionsDir, 'customers.md');
  const styleFile = path.join(correctionsDir, 'style.md');

  let customersContent = fs.existsSync(customersFile) ? fs.readFileSync(customersFile, 'utf-8') : '';
  let styleContent = fs.existsSync(styleFile) ? fs.readFileSync(styleFile, 'utf-8') : '';

  const timestamp = new Date().toISOString().slice(0, 19);

  for (const diff of diffs) {
    if (diff.type === 'removed_customer') {
      const rule = `\n## ${diff.customer} (removed ${timestamp})\n- Not significant enough for Q1 this week. Had: "${diff.generated.slice(0, 100)}"\n- Rule: omit from Q1 unless meeting, case escalation, or significant deliverable.\n`;
      styleContent += rule;
      console.log(`  [style] ${diff.customer}: removed from Q1`);
    }

    if (diff.type === 'modified_customer') {
      const rule = `\n## ${diff.customer} (corrected ${timestamp})\n- AI wrote: "${diff.generated.slice(0, 150)}"\n- User corrected to: "${diff.edited.slice(0, 150)}"\n`;
      customersContent += rule;

      // Also update the per-customer .md if it exists
      const custFile = path.join(weekDir, `${diff.customer.toLowerCase().replace(/\s+/g, '-')}.md`);
      if (fs.existsSync(custFile)) {
        let custContent = fs.readFileSync(custFile, 'utf-8');
        if (!custContent.includes('## Corrections Applied')) {
          custContent += '\n## Corrections Applied\n';
        }
        custContent += `- [${timestamp}] User changed Q1 bullet: "${diff.edited.slice(0, 150)}"\n`;
        if (!dryRun) fs.writeFileSync(custFile, custContent);
      }

      console.log(`  [customer] ${diff.customer}: Q1 description corrected`);
    }

    if (diff.type === 'added_customer') {
      const rule = `\n## ${diff.customer} (added by user ${timestamp})\n- AI missed this. User added: "${diff.edited.slice(0, 150)}"\n- Check if a source was not polled or a detail was in bodyPreview only.\n`;
      customersContent += rule;
      console.log(`  [customer] ${diff.customer}: added by user (AI missed)`);
    }

    if (diff.type === 'modified_section') {
      const rule = `\n## ${diff.section} restructured (${timestamp})\n- User preferred different format/content for ${diff.section}.\n`;
      styleContent += rule;
      console.log(`  [style] ${diff.section}: restructured by user`);
    }
  }

  if (!dryRun) {
    fs.writeFileSync(customersFile, customersContent);
    fs.writeFileSync(styleFile, styleContent);
  }
}

// ─── Main ─────────────────────────────────────────────────────────

const args = process.argv.slice(2);
const dryRun = args.includes('--dry-run');
const reportOverride = args.includes('--report') ? args[args.indexOf('--report') + 1] : null;

const config = loadConfig();
if (!config) { console.log('No config. Run setup.js first.'); process.exit(1); }

const weekDir = getWeekDir(config.projectRoot);
const generatedFile = path.join(weekDir, '.last-generated-report.md');

// Find the current report
const reportPath = reportOverride || findReport(config.projectRoot);
if (!reportPath || !fs.existsSync(reportPath)) {
  console.log('No weekly update report found.');
  process.exit(0);
}

// Check if we have a generated version to diff against
if (!fs.existsSync(generatedFile)) {
  console.log('No previous generated version to diff against.');
  console.log(`Saving current report as baseline: ${generatedFile}`);
  if (!dryRun) fs.copyFileSync(reportPath, generatedFile);
  process.exit(0);
}

const generated = fs.readFileSync(generatedFile, 'utf-8');
const current = fs.readFileSync(reportPath, 'utf-8');

if (generated === current) {
  console.log('No changes detected. Report matches generated version.');
  process.exit(0);
}

console.log(`[diff-tracker] Comparing ${path.basename(reportPath)} against generated version...`);
const diffs = diffReports(generated, current);

if (diffs.length === 0) {
  console.log('Changes detected but no structured diffs parsed. May be whitespace/formatting only.');
  process.exit(0);
}

console.log(`\n[diff-tracker] ${diffs.length} changes found:\n`);
for (const d of diffs) {
  console.log(`  ${d.type}: ${d.customer || d.section} — ${d.reason}`);
}

if (dryRun) {
  console.log('\n[dry-run] No corrections written.');
} else {
  console.log('\n[diff-tracker] Writing corrections...\n');
  applyCorrections(diffs, weekDir, dryRun);
  console.log('\n[done] Corrections applied to:');
  console.log(`  ${path.join(weekDir, 'corrections', 'customers.md')}`);
  console.log(`  ${path.join(weekDir, 'corrections', 'style.md')}`);
}
