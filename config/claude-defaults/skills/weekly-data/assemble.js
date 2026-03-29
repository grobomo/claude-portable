#!/usr/bin/env node
/**
 * assemble.js — Reads corrections + sources + customer files in the right order.
 * Outputs structured JSON that Claude uses to write reports.
 *
 * This is the ONLY way to read weekly data. Claude should run this script
 * instead of reading source files individually. This ensures corrections
 * are always applied and user edits are always respected.
 *
 * Usage:
 *   node assemble.js                    # Full assembly, JSON to stdout
 *   node assemble.js --customer ep      # One customer only
 *   node assemble.js --section emails   # One source only
 *   node assemble.js --summary          # Compact summary (no raw data)
 */

const fs = require('fs');
const path = require('path');

const SKILL_DIR = __dirname;
const CONFIG_FILE = path.join(SKILL_DIR, 'config.json');

function loadConfig() {
  if (!fs.existsSync(CONFIG_FILE)) {
    console.error(JSON.stringify({ error: 'No config.json. Run: node setup.js' }));
    process.exit(1);
  }
  return JSON.parse(fs.readFileSync(CONFIG_FILE, 'utf-8'));
}

function getWeekDir(root) {
  const now = new Date();
  const day = now.getDay();
  const fri = new Date(now);
  fri.setDate(now.getDate() + (5 - (day === 0 ? 7 : day)));
  return path.join(root, 'reports', 'weekly-data', fri.toISOString().slice(0, 10));
}

function readIfExists(filePath) {
  return fs.existsSync(filePath) ? fs.readFileSync(filePath, 'utf-8') : null;
}

// ─── Parse source files ───────────────────────────────────────────

function parseEmails(content) {
  if (!content) return [];
  const entries = [];
  const sections = content.split(/^## /m).slice(1);
  for (const s of sections) {
    const lines = s.split('\n');
    const heading = lines[0].trim();
    const dateMatch = heading.match(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})/);
    const to = (s.match(/\*\*To:\*\*\s*(.+)/)||[])[1]||'';
    const preview = (s.match(/\*\*Preview:\*\*\s*(.+)/)||[])[1]||'';
    const myRead = (s.match(/\*\*My read:\*\*\s*(.+?)(?=\n(?:\*\*|---|##|$))/s)||[])[1]||'';
    entries.push({
      date: dateMatch ? dateMatch[1] : '',
      subject: heading.replace(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}\s*—\s*/, ''),
      to: to.trim(),
      preview: preview.trim(),
      userNote: myRead.trim()  // User's correction — takes priority
    });
  }
  return entries;
}

function parseCases(content) {
  if (!content) return [];
  const entries = [];
  const sections = content.split(/^## /m).slice(1);
  for (const s of sections) {
    const heading = s.split('\n')[0].trim();
    const subject = (s.match(/\*\*Subject:\*\*\s*(.+)/)||[])[1]||'';
    const from = (s.match(/\*\*From:\*\*\s*(.+)/)||[])[1]||'';
    const myRead = (s.match(/\*\*My read:\*\*\s*(.+?)(?=\n(?:\*\*|---|##|$))/s)||[])[1]||'';
    const caseMatch = heading.match(/TM-\d+/);
    entries.push({
      heading: heading.trim(),
      caseNumber: caseMatch ? caseMatch[0] : '',
      subject: subject.trim(),
      from: from.trim(),
      userNote: myRead.trim()
    });
  }
  return entries;
}

function parseCalendar(content) {
  if (!content) return { allDay: [], meetings: {} };
  const result = { allDay: [], meetings: {} };

  // All-day events
  const allDayMatch = content.match(/## All-Day Events\n\n([\s\S]*?)(?=\n## |$)/);
  if (allDayMatch) {
    const lines = allDayMatch[1].split('\n').filter(l => l.startsWith('- **'));
    for (const line of lines) {
      const eventMatch = line.match(/\*\*(.+?)\*\*\s*—\s*(.+?)(?:\s*\(Org:.*\))?$/);
      const relevantLine = lines[lines.indexOf(line) + 1] || '';
      const relevant = (relevantLine.match(/\*\*Relevant\?\*\*\s*(.*)/)||[])[1]||'';
      if (eventMatch) {
        result.allDay.push({
          dates: eventMatch[1].trim(),
          subject: eventMatch[2].trim(),
          userRelevant: relevant.trim()
        });
      }
    }
  }

  // Timed meetings by day
  const dayBlocks = content.split(/^### /m).slice(1);
  for (const block of dayBlocks) {
    const dayLine = block.split('\n')[0].trim();
    const meetings = [];
    for (const line of block.split('\n').slice(1)) {
      const m = line.match(/^- (\d{2}:\d{2})\s*—\s*(.+)/);
      if (m) meetings.push({ time: m[1], subject: m[2].trim() });
    }
    if (meetings.length) result.meetings[dayLine] = meetings;
  }

  return result;
}

function parseTeams(content) {
  if (!content) return { messages: '', takeaways: '' };
  const msgMatch = content.match(/## Messages\n\n([\s\S]*?)(?=\n## |$)/);
  const takeMatch = content.match(/## My takeaways\n\n([\s\S]*?)$/);
  return {
    messages: msgMatch ? msgMatch[1].trim() : '',
    takeaways: takeMatch ? takeMatch[1].replace(/<!--.*?-->/g, '').trim() : ''
  };
}

// ─── Main ─────────────────────────────────────────────────────────

const args = process.argv.slice(2);
const customerFilter = args.includes('--customer') ? args[args.indexOf('--customer') + 1] : null;
const sectionFilter = args.includes('--section') ? args[args.indexOf('--section') + 1] : null;
const summaryMode = args.includes('--summary');

const config = loadConfig();
const weekDir = getWeekDir(config.projectRoot);
const sourcesDir = path.join(weekDir, 'sources');
const correctionsDir = path.join(weekDir, 'corrections');

if (!fs.existsSync(sourcesDir)) {
  console.error(JSON.stringify({ error: 'No source data. Run: node poll-sources.js' }));
  process.exit(1);
}

// ── Step 1: Read corrections (FIRST — these override everything) ──

const corrections = {
  terminology: readIfExists(path.join(correctionsDir, 'terminology.md')) || '',
  customers: readIfExists(path.join(correctionsDir, 'customers.md')) || '',
  style: readIfExists(path.join(correctionsDir, 'style.md')) || ''
};

// ── Step 2: Read sources ──

const sources = {};

if (!sectionFilter || sectionFilter === 'emails') {
  sources.emails = parseEmails(readIfExists(path.join(sourcesDir, 'sent-emails.md')));
}
if (!sectionFilter || sectionFilter === 'cases') {
  sources.cases = parseCases(readIfExists(path.join(sourcesDir, 'case-updates.md')));
}
if (!sectionFilter || sectionFilter === 'calendar') {
  sources.calendar = parseCalendar(readIfExists(path.join(sourcesDir, 'calendar.md')));
}
if (!sectionFilter || sectionFilter === 'teams') {
  sources.teams = {};
  const teamFiles = fs.readdirSync(sourcesDir).filter(f => f.startsWith('teams-'));
  for (const f of teamFiles) {
    const slug = f.replace('teams-', '').replace('.md', '');
    sources.teams[slug] = parseTeams(readIfExists(path.join(sourcesDir, f)));
  }
}
if (!sectionFilter || sectionFilter === 'transcripts') {
  sources.transcripts = readIfExists(path.join(sourcesDir, 'transcript-reports.md')) || '';
}
if (!sectionFilter || sectionFilter === 'notes') {
  sources.notes = readIfExists(path.join(sourcesDir, 'handwritten-notes.md')) || '';
}

// ── Step 3: Read per-customer summaries ──

const customers = {};
if (!sectionFilter) {
  const mdFiles = fs.readdirSync(weekDir).filter(f =>
    f.endsWith('.md') && !['sources', 'corrections'].some(d => f.startsWith(d))
  );
  for (const f of mdFiles) {
    const name = f.replace('.md', '');
    if (customerFilter && name !== customerFilter) continue;
    customers[name] = readIfExists(path.join(weekDir, f)) || '';
  }
}

// ── Step 4: Metadata ──

const lastPoll = readIfExists(path.join(weekDir, '.last-poll')) || 'never';
const lastGenerated = readIfExists(path.join(weekDir, '.last-generated')) || 'never';

// ── Step 5: Build output ──

const output = {
  week: path.basename(weekDir),
  lastPoll: lastPoll.trim(),
  lastGenerated: lastGenerated.trim(),
  corrections,
  customers
};

if (!summaryMode) {
  output.sources = sources;
}

// In summary mode, just show counts and user-annotated items
if (summaryMode) {
  output.sourceSummary = {
    emails: sources.emails ? {
      total: sources.emails.length,
      annotated: sources.emails.filter(e => e.userNote).length,
      annotatedItems: sources.emails.filter(e => e.userNote).map(e => ({
        subject: e.subject, note: e.userNote
      }))
    } : null,
    cases: sources.cases ? {
      total: sources.cases.length,
      annotated: sources.cases.filter(c => c.userNote).length,
      annotatedItems: sources.cases.filter(c => c.userNote).map(c => ({
        caseNumber: c.caseNumber, note: c.userNote
      }))
    } : null,
    calendar: sources.calendar || null,
    teamsChats: sources.teams ? Object.keys(sources.teams).length : 0,
    teamsTakeaways: sources.teams ? Object.entries(sources.teams)
      .filter(([,v]) => v.takeaways)
      .map(([k,v]) => ({ chat: k, takeaway: v.takeaways })) : []
  };
}

console.log(JSON.stringify(output, null, 2));

// Write timestamp
fs.writeFileSync(path.join(weekDir, '.last-assembled'), new Date().toISOString());
