#!/usr/bin/env node
/**
 * weekly-data setup — Full bootstrapper. Installs all dependencies, configures, first poll.
 * Assumes: Node.js installed (you're running this), Claude Code installed.
 *
 * Usage:
 *   node setup.js           # Full bootstrap (installs missing deps, configures, polls)
 *   node setup.js --check   # Just check status, don't change anything
 *   node setup.js --reset   # Re-discover everything from scratch
 */

const fs = require('fs');
const path = require('path');
const { execSync, spawnSync } = require('child_process');

const SKILL_DIR = __dirname;
const CONFIG_FILE = path.join(SKILL_DIR, 'config.json');

// GitHub repos for dependencies
const REPOS = {
  msgraphLib: { repo: 'grobomo/msgraph-lib', file: 'token_manager.py', name: 'msgraph-lib' },
  teamsChat: { repo: 'grobomo/teams-chat', file: 'teams_chat.py', name: 'teams-chat' }
};

// ─── Utilities ────────────────────────────────────────────────────

function run(cmd, opts = {}) {
  try {
    return execSync(cmd, {
      encoding: 'utf-8', timeout: opts.timeout || 30000,
      stdio: opts.stdio || 'pipe',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
      ...opts
    }).trim();
  } catch (e) {
    return null;
  }
}

function which(cmd) {
  const result = run(`which ${cmd} 2>/dev/null || where ${cmd} 2>NUL`);
  return result ? result.split('\n')[0].trim() : null;
}

function heading(text) {
  console.log(`\n── ${text} ${'─'.repeat(Math.max(0, 55 - text.length))}`);
}

function ok(msg) { console.log(`  ✓  ${msg}`); }
function warn(msg) { console.log(`  !  ${msg}`); }
function fail(msg) { console.log(`  ✗  ${msg}`); }
function info(msg) { console.log(`     ${msg}`); }
function skip(msg) { console.log(`  ~  ${msg}`); }

// ─── Step 1: Check prerequisites ──────────────────────────────────

function checkPython() {
  heading('Python');
  const py = which('python') || which('python3');
  if (py) {
    const ver = run('python --version') || run('python3 --version');
    ok(`${ver} (${py})`);
    return true;
  }
  fail('Python not found.');
  info('Install from https://www.python.org/downloads/');
  info('Or: winget install Python.Python.3.12');
  info('After installing, restart your terminal and re-run setup.');
  return false;
}

function checkNode() {
  heading('Node.js');
  const ver = run('node --version');
  if (ver) {
    ok(`Node.js ${ver}`);
    return true;
  }
  fail('Node.js not found (but you\'re running this... something is wrong).');
  return false;
}

function checkGit() {
  heading('Git');
  const git = which('git');
  if (git) {
    ok(`Git found (${git})`);
    return true;
  }
  fail('Git not found.');
  info('Install from https://git-scm.com/downloads');
  info('Or: winget install Git.Git');
  return false;
}

function checkPipDeps() {
  heading('Python packages');
  const deps = ['requests', 'msal'];
  const missing = [];
  for (const dep of deps) {
    const result = run(`python -c "import ${dep}"`, { timeout: 10000 });
    if (result === null) missing.push(dep);
  }
  if (missing.length === 0) {
    ok(`All required: ${deps.join(', ')}`);
    return true;
  }
  warn(`Missing: ${missing.join(', ')}. Installing...`);
  const installResult = run(`pip install ${missing.join(' ')}`, { timeout: 60000, stdio: 'inherit' });
  if (installResult !== null) {
    ok('Installed successfully');
    return true;
  }
  fail(`Failed to install: ${missing.join(', ')}`);
  info(`Run manually: pip install ${missing.join(' ')}`);
  return false;
}

// ─── Step 2: Clone/find dependencies ──────────────────────────────

function findUp(startDir, targetFile, maxDepth = 4) {
  const dirs = [startDir];
  let d = startDir;
  for (let i = 0; i < maxDepth; i++) {
    d = path.dirname(d);
    dirs.push(d);
  }
  for (const dir of dirs) {
    const direct = path.join(dir, targetFile);
    if (fs.existsSync(direct)) return dir;
    if (!fs.existsSync(dir)) continue;
    try {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        if (!entry.isDirectory()) continue;
        const candidate = path.join(dir, entry.name, targetFile);
        if (fs.existsSync(candidate)) return path.join(dir, entry.name);
      }
    } catch (_) {}
  }
  return null;
}

function getProjectsDir() {
  // Find a reasonable place to clone sibling projects
  const cwd = process.cwd();
  // If cwd has sibling directories that look like projects, use parent
  const parent = path.dirname(cwd);
  if (fs.existsSync(parent)) return parent;
  return cwd;
}

function ensureDep(key, hasGit) {
  const { repo, file, name } = REPOS[key];
  heading(name);

  // Check if already exists
  const found = findUp(process.cwd(), file);
  if (found) {
    ok(`Found at ${found}`);
    return found;
  }

  if (!hasGit) {
    fail(`${name} not found and git not available to clone it.`);
    info(`Clone manually: git clone https://github.com/${repo}.git`);
    return null;
  }

  // Clone it
  const projectsDir = getProjectsDir();
  const targetDir = path.join(projectsDir, name);
  warn(`Not found. Cloning to ${targetDir}...`);

  const cloneResult = run(`git clone https://github.com/${repo}.git "${targetDir}"`, {
    timeout: 60000, stdio: 'inherit'
  });

  if (cloneResult !== null && fs.existsSync(path.join(targetDir, file))) {
    ok(`Cloned successfully`);

    // Install Python deps if requirements.txt exists
    const reqFile = path.join(targetDir, 'requirements.txt');
    if (fs.existsSync(reqFile)) {
      info('Installing Python dependencies...');
      run(`pip install -r "${reqFile}"`, { timeout: 60000, stdio: 'inherit' });
    }

    return targetDir;
  }

  fail(`Failed to clone ${repo}`);
  info(`Clone manually: cd "${projectsDir}" && git clone https://github.com/${repo}.git`);
  return null;
}

// ─── Step 3: Graph API token ──────────────────────────────────────

function checkGraphToken(msgraphLib) {
  heading('Graph API Token');
  if (!msgraphLib) {
    fail('Cannot test — msgraph-lib not found');
    return false;
  }

  const script = `
import sys
sys.path.insert(0, '${msgraphLib.replace(/\\/g, '/')}')
from token_manager import graph_get
data = graph_get('/me', params={'$select': 'displayName,mail'})
print(data.get('displayName', '?') + '|||' + data.get('mail', '?'))
`;
  const tmpFile = path.join(SKILL_DIR, '.tmp-test.py');
  fs.writeFileSync(tmpFile, script);
  const result = run(`python -u "${tmpFile}"`, { timeout: 15000 });
  try { fs.unlinkSync(tmpFile); } catch (_) {}

  if (result && result.includes('|||')) {
    const [name, mail] = result.split('|||');
    ok(`Authenticated as: ${name} <${mail}>`);
    return true;
  }

  warn('Token expired or not yet created.');
  info('');
  info('To authenticate, run:');
  info(`  cd "${msgraphLib}"`);
  info('  python token_manager.py');
  info('');
  info('This opens a browser for Microsoft login (device code flow).');
  info('After approving, the token is saved locally and auto-refreshes.');
  info('Re-run this setup after authenticating.');
  info('');

  // Check if token file exists at all
  const tokenFile = path.join(require('os').homedir(), '.msgraph', 'tokens.json');
  if (fs.existsSync(tokenFile)) {
    info(`Token file exists at ${tokenFile} but may be expired.`);
    info('Run token_manager.py to refresh it.');
  } else {
    info('No token file found — this is a first-time setup.');
    info('The auth flow will create ~/.msgraph/tokens.json');
  }

  return false;
}

// ─── Step 4: Teams chat config ────────────────────────────────────

function checkTeamsChats(teamsChat) {
  heading('Teams Chats');
  if (!teamsChat) {
    skip('teams-chat not found — Teams polling will be skipped');
    info('This is optional. Emails and calendar will still work.');
    return [];
  }

  const chatScript = fs.existsSync(path.join(path.dirname(teamsChat), 'teams_chat.py'))
    ? teamsChat : null;
  if (!chatScript) {
    skip('teams_chat.py not found at expected path');
    return [];
  }

  const result = run(`python "${chatScript}" list`, { timeout: 15000 });
  if (!result) {
    warn('Could not list Teams chats (token may need refresh)');
    return [];
  }

  const chats = [];
  for (const line of result.split('\n')) {
    const match = line.match(/\[group\]\s+(.+)/);
    if (match) chats.push(match[1].trim());
  }
  ok(`${chats.length} group chats found`);
  if (chats.length > 0) {
    info('Auto-detected chats to poll:');
    for (const c of chats.slice(0, 8)) info(`  - ${c}`);
    if (chats.length > 8) info(`  ... and ${chats.length - 8} more`);
  }

  return chats;
}

// ─── Step 5: Scheduler ────────────────────────────────────────────

function checkScheduler() {
  heading('Scheduler');
  const schedulerPath = path.join(path.dirname(SKILL_DIR), 'claude-scheduler', 'scheduler.py');
  if (fs.existsSync(schedulerPath)) {
    ok('claude-scheduler found');
    return schedulerPath;
  }
  skip('claude-scheduler not found — auto-polling disabled');
  info('You can still poll manually: node poll-sources.js');
  info('To enable auto-polling, install the claude-scheduler skill.');
  return null;
}

// ─── Step 6: Project root ─────────────────────────────────────────

function detectProjectRoot() {
  heading('Project Root');
  const cwd = process.cwd();

  // Check for reports/ directory
  if (fs.existsSync(path.join(cwd, 'reports'))) {
    ok(`Using current directory: ${cwd}`);
    info('Found reports/ directory — data will be cached in reports/weekly-data/');
    return cwd;
  }

  // Create reports/ in cwd
  warn(`No reports/ directory found. Creating in ${cwd}`);
  fs.mkdirSync(path.join(cwd, 'reports'), { recursive: true });
  ok('Created reports/ directory');
  return cwd;
}

// ─── Step 7: Notes directories ────────────────────────────────────

function detectNotesDirs() {
  heading('Handwritten Notes');
  const candidates = [
    // Common patterns — OneDrive, Documents, etc.
    path.join(require('os').homedir(), 'OneDrive', 'Documents'),
    path.join(require('os').homedir(), 'Documents'),
  ];

  // Also check for OneDrive with org name (e.g. "OneDrive - CompanyName")
  const homeDir = require('os').homedir();
  try {
    for (const entry of fs.readdirSync(homeDir, { withFileTypes: true })) {
      if (entry.isDirectory() && entry.name.startsWith('OneDrive - ')) {
        const docsDir = path.join(homeDir, entry.name, 'Documents');
        if (fs.existsSync(docsDir)) candidates.unshift(docsDir);
      }
    }
  } catch (_) {}

  const found = candidates.filter(d => fs.existsSync(d));
  if (found.length > 0) {
    ok(`Found ${found.length} document directories`);
    for (const d of found.slice(0, 3)) info(`  - ${d}`);
    info('Edit config.json notesDirs to add/remove scan directories.');
    return found.slice(0, 3);
  }

  skip('No standard document directories found');
  info('Add directories to config.json notesDirs manually if you have notes files.');
  return [];
}

// ─── Step 8: Teams targets (which chats to poll) ─────────────────

function detectTeamsTargets(chats) {
  // Build auto-detected targets from chat names
  const targets = {};
  const patterns = [
    // Common team chat patterns
    { match: /squad/i, slug: 'squad' },
    { match: /internal/i, slug: 'internal' },
    { match: /external/i, slug: 'external' },
  ];

  for (const chat of chats) {
    for (const p of patterns) {
      if (p.match.test(chat) && !targets[chat]) {
        // Use first matching word as the slug key
        targets[chat] = p.slug;
        break;
      }
    }
  }

  // If no auto-detected targets, use top 5 group chats
  if (Object.keys(targets).length === 0 && chats.length > 0) {
    for (const chat of chats.slice(0, 5)) {
      const slug = chat.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 20);
      targets[chat] = slug;
    }
  }

  return targets;
}

// ─── Main ─────────────────────────────────────────────────────────

const args = process.argv.slice(2);
const checkOnly = args.includes('--check');
const reset = args.includes('--reset');

console.log('');
console.log('╔══════════════════════════════════════════════════════════╗');
console.log('║                Weekly Data — Setup                       ║');
console.log('║                                                          ║');
console.log('║  Builds a local cache of your work activity:             ║');
console.log('║  emails, cases, Teams chats, calendar, Trello.           ║');
console.log('║  Auto-refreshes every 15 min. Editable by you.           ║');
console.log('║  Ask Claude for a summary anytime — no API calls.        ║');
console.log('╚══════════════════════════════════════════════════════════╝');

// ── Prerequisites ──

const hasPython = checkPython();
const hasNode = checkNode();
const hasGit = checkGit();

if (!hasPython || !hasNode) {
  console.log('\n════════════════════════════════════════════════════════');
  console.log('Install the missing prerequisites above, then re-run:');
  console.log(`  node "${path.join(SKILL_DIR, 'setup.js')}"`);
  console.log('════════════════════════════════════════════════════════\n');
  process.exit(1);
}

const hasPipDeps = checkPipDeps();

// ── Dependencies (clone if missing) ──

const msgraphLib = ensureDep('msgraphLib', hasGit);
const teamsChatDir = ensureDep('teamsChat', hasGit);
const teamsChat = teamsChatDir ? path.join(teamsChatDir, 'teams_chat.py') : null;

// ── Auth ──

const hasToken = msgraphLib ? checkGraphToken(msgraphLib) : false;

if (!hasToken) {
  console.log('\n════════════════════════════════════════════════════════');
  console.log('Graph API authentication required before continuing.');
  console.log('Follow the instructions above, then re-run setup.');
  console.log('════════════════════════════════════════════════════════\n');

  // Save partial config so re-run doesn't re-clone
  if (msgraphLib) {
    const partialConfig = {
      msgraphLib,
      teamsChat,
      projectRoot: process.cwd(),
      partial: true,
      created: new Date().toISOString()
    };
    fs.writeFileSync(CONFIG_FILE, JSON.stringify(partialConfig, null, 2));
    info(`Partial config saved. Re-run setup after authenticating.`);
  }
  process.exit(1);
}

// ── Detect everything else ──

const chats = checkTeamsChats(teamsChat);
const scheduler = checkScheduler();
const projectRoot = detectProjectRoot();
const notesDirs = detectNotesDirs();
const teamsTargets = detectTeamsTargets(chats);

if (checkOnly) {
  console.log('\n  Check complete. No changes made.\n');
  process.exit(0);
}

// ── Save config ──

heading('Saving Configuration');
const newConfig = {
  msgraphLib,
  teamsChat,
  projectRoot,
  scheduler,
  notesDirs,
  teamsTargets,
  created: new Date().toISOString(),
  updated: new Date().toISOString()
};
fs.writeFileSync(CONFIG_FILE, JSON.stringify(newConfig, null, 2));
ok(`Config saved: ${CONFIG_FILE}`);

// ── Create data directories ──

function getWeekDir(root) {
  const now = new Date();
  const day = now.getDay();
  const fri = new Date(now);
  fri.setDate(now.getDate() + (5 - (day === 0 ? 7 : day)));
  return path.join(root, 'reports', 'weekly-data', fri.toISOString().slice(0, 10));
}

const weekDir = getWeekDir(projectRoot);
fs.mkdirSync(path.join(weekDir, 'sources'), { recursive: true });
fs.mkdirSync(path.join(weekDir, 'corrections'), { recursive: true });

for (const f of ['terminology.md', 'customers.md', 'style.md']) {
  const p = path.join(weekDir, 'corrections', f);
  if (!fs.existsSync(p)) {
    const name = f.replace('.md', '');
    fs.writeFileSync(p, `# ${name.charAt(0).toUpperCase() + name.slice(1)} Corrections\n\nEdit this file to correct how summaries interpret your data.\nThese corrections persist and are applied to all future reports.\n\n`);
  }
}

// ── First poll ──

heading('First Poll');
console.log('');
try {
  const pollScript = path.join(SKILL_DIR, 'poll-sources.js');
  execSync(`node "${pollScript}"`, { stdio: 'inherit', timeout: 120000 });
} catch (e) {
  warn('First poll had errors (non-fatal). You can re-run: node poll-sources.js');
}

// ── Schedule 15-min polling ──

if (scheduler) {
  heading('Auto-Polling Schedule');
  try {
    const pollCmd = `node "${path.join(SKILL_DIR, 'poll-sources.js')}"`;
    const result = run(`python "${scheduler}" add --name "weekly-data-poller" --command "${pollCmd}" --interval 15`);
    if (result && result.includes('Added')) {
      ok('Scheduled: poll every 15 minutes');
    } else if (result && result.includes('exists')) {
      ok('Already scheduled');
    } else {
      skip('Could not auto-schedule. Poll manually or ask Claude to set it up.');
    }
  } catch (e) {
    skip('Scheduler error. Poll manually: node poll-sources.js');
  }
}

// ── Done ──

console.log('');
console.log('╔══════════════════════════════════════════════════════════╗');
console.log('║                  Setup Complete                          ║');
console.log('╠══════════════════════════════════════════════════════════╣');
console.log('║                                                          ║');
console.log('║  Your data is cached locally and refreshes every 15 min. ║');
console.log('║                                                          ║');
console.log('║  Data location:                                          ║');
console.log(`║    ${weekDir.slice(0, 54).padEnd(54)} ║`);
console.log('║                                                          ║');
console.log('║  What to do next:                                        ║');
console.log('║    • Ask Claude: "what did I do this week?"              ║');
console.log('║    • Edit sources/*.md to correct AI interpretations     ║');
console.log('║    • Edit corrections/*.md for persistent rules          ║');
console.log('║    • "refresh data" to force immediate poll              ║');
console.log('║                                                          ║');
console.log('╚══════════════════════════════════════════════════════════╝');
console.log('');
