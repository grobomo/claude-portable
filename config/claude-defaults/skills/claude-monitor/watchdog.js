// Claude Code CPU Watchdog v5
// Uses Job Object CPU rate capping instead of suspend/resume.
// Process stays responsive (can accept keystrokes) but CPU is hard-capped.
//
// Idle tabs: capped at 2%
// Active tabs (API streaming): uncapped
// Detection: ReadTransferCount delta over sample window

const { execSync } = require('child_process');
const path = require('path');

const args = process.argv.slice(2).reduce((a, s) => {
  const m = s.match(/^--(\w+)=(.+)$/);
  if (m) a[m[1]] = m[2];
  return a;
}, {});

const CYCLE = parseInt(args.cycle || '5') * 1000;
const SAMPLE = parseInt(args.sample || '2') * 1000;
const GRACE = parseInt(args.grace || '2');
const IDLE_BYTES = parseInt(args.threshold || '30000');
const CAP_PCT = parseInt(args.cap || '2');
const EXE = path.join(__dirname, 'throttle.exe');

// Detect "our" claude.exe. --exclude=PID overrides auto-detection.
let selfClaude = parseInt(args.exclude || '0');

const procs = new Map(); // pid -> { state: 'active'|'capped', idleCount }
let running = true;

function ts() { return new Date().toLocaleTimeString('en-US', { hour12: false }); }
function log(m) { process.stdout.write('[' + ts() + '] ' + m + '\n'); }
function kb(b) { return b > 1048576 ? (b/1048576).toFixed(1)+'MB' : b > 1024 ? (b/1024).toFixed(1)+'KB' : b+'B'; }
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function getPids() {
  try {
    return execSync('wmic process where "name=\'claude.exe\'" get ProcessId /format:csv',
      { encoding: 'utf8', timeout: 5000 }).trim().split('\n')
      .filter(l => l.trim() && !l.startsWith('Node'))
      .map(l => parseInt(l.trim().split(',').pop()))
      .filter(n => !isNaN(n) && n > 0 && n !== selfClaude);
  } catch(e) { return []; }
}

function getReads() {
  try {
    const r = {};
    for (const line of execSync(
      'wmic process where "name=\'claude.exe\'" get ProcessId,ReadTransferCount /format:csv',
      { encoding: 'utf8', timeout: 5000 }).trim().split('\n').slice(1)) {
      const p = line.trim().split(',');
      if (p.length >= 3) { const pid = parseInt(p[1]); if (pid > 0) r[pid] = parseInt(p[2]) || 0; }
    }
    return r;
  } catch(e) { return {}; }
}

function run(pid, action, val) {
  try {
    const cmd = val ? '"'+EXE+'" '+pid+' '+action+' '+val : '"'+EXE+'" '+pid+' '+action;
    return execSync(cmd, { encoding:'utf8', timeout:5000 }).trim();
  } catch(e) { return 'ERR'; }
}

async function poll() {
  const pids = getPids();
  if (!pids.length) return;

  for (const pid of pids) {
    if (!procs.has(pid)) procs.set(pid, { state: 'active', idleCount: 0 });
  }
  for (const [pid] of procs) {
    if (!pids.includes(pid)) procs.delete(pid);
  }

  // Sample all processes at once
  const a = getReads();
  await sleep(SAMPLE);
  const b = getReads();

  for (const [pid, info] of procs) {
    const delta = (b[pid]||0) - (a[pid]||0);
    const isActive = delta > IDLE_BYTES;

    if (isActive && info.state === 'capped') {
      // Was capped, now active -> uncap
      run(pid, 'uncap');
      info.state = 'active';
      info.idleCount = 0;
      log('UNCAP   PID ' + pid + ' (reads: ' + kb(delta) + ')');
    } else if (isActive) {
      info.idleCount = 0;
    } else if (!isActive && info.state === 'active') {
      info.idleCount++;
      if (info.idleCount >= GRACE) {
        run(pid, 'cap', String(CAP_PCT));
        info.state = 'capped';
        log('CAP     PID ' + pid + ' at ' + CAP_PCT + '% (idle ' + info.idleCount + ' cycles)');
      }
    }
  }
}

async function detectSelf() {
  if (selfClaude > 0) { log('Self excluded via --exclude=' + selfClaude); return; }
  // The active tab has accumulated far more total ReadTransferCount from API streaming.
  // Compare absolute values -- the one with the most bytes = this tab.
  log('Detecting self (highest cumulative reads)...');
  const reads = getReads();
  let maxBytes = 0, maxPid = 0, secondMax = 0;
  for (const pid of Object.keys(reads)) {
    const bytes = reads[pid] || 0;
    log('  PID ' + pid + ': total reads=' + kb(bytes));
    if (bytes > maxBytes) { secondMax = maxBytes; maxBytes = bytes; maxPid = parseInt(pid); }
    else if (bytes > secondMax) { secondMax = bytes; }
  }
  // Only auto-exclude if the winner has significantly more reads (2x+) than the runner-up
  if (maxPid > 0 && (secondMax === 0 || maxBytes > secondMax * 2)) {
    selfClaude = maxPid;
    log('  -> self = PID ' + selfClaude + ' (' + kb(maxBytes) + ' total, next=' + kb(secondMax) + ')');
  } else {
    log('  -> ambiguous (top=' + kb(maxBytes) + ' next=' + kb(secondMax) + ') - will cap all');
    log('  -> use --exclude=PID to specify manually');
  }
}

async function main() {
  log('=== Claude Code CPU Watchdog v5 (cap mode) ===');
  log('cycle=' + (CYCLE/1000) + 's sample=' + (SAMPLE/1000) + 's cap=' + CAP_PCT + '% threshold=' + kb(IDLE_BYTES) + ' grace=' + GRACE);
  await detectSelf();
  const pids = getPids();
  log(pids.length + ' other claude.exe: ' + pids.join(', '));
  log('');

  while (running) {
    try { await poll(); } catch(e) { log('ERR: ' + e.message); }
    await sleep(CYCLE);
  }
}

function cleanup() {
  running = false;
  log('Uncapping all...');
  for (const [pid, info] of procs) {
    if (info.state === 'capped') { run(pid, 'uncap'); log('  UNCAP ' + pid); }
  }
  process.exit(0);
}
process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);
process.on('exit', () => {
  for (const [pid, info] of procs) {
    if (info.state === 'capped') try { run(pid, 'uncap'); } catch(e) {}
  }
});

main();
