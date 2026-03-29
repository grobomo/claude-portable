#!/usr/bin/env node
// claude-monitor -- Cross-platform process monitor for Claude Code sessions
// Maps process trees, measures CPU/RAM, detects orphan processes, audits npm cache
//
// Usage:
//   node monitor.js                  # Full report (5s sample)
//   node monitor.js --sample 1       # Quick snapshot (1s)
//   node monitor.js --json           # JSON output
//   node monitor.js --security       # Security audit only
//   node monitor.js --watch 10       # Continuous (every 10s)
//   node monitor.js --out file.txt   # Save to file

var fs = require('fs');
var path = require('path');
var child_process = require('child_process');
var os = require('os');

// -- Args --
var args = process.argv.slice(2);
var SAMPLE_SEC = 5;
var JSON_OUT = false;
var SECURITY_ONLY = false;
var WATCH_SEC = 0;
var OUT_FILE = null;

for (var i = 0; i < args.length; i++) {
  if (args[i] === '--sample' && args[i+1]) { SAMPLE_SEC = parseInt(args[i+1]); i++; }
  else if (args[i] === '--json') { JSON_OUT = true; }
  else if (args[i] === '--security') { SECURITY_ONLY = true; }
  else if (args[i] === '--watch' && args[i+1]) { WATCH_SEC = parseInt(args[i+1]); i++; }
  else if (args[i] === '--out' && args[i+1]) { OUT_FILE = args[i+1]; i++; }
}

var PLATFORM = os.platform(); // win32, darwin, linux

// -- Known-good npx packages (security allowlist) --
var KNOWN_PACKAGES = [
  '@anthropic-ai', '@modelcontextprotocol', '@hono', '@img', '@emnapi',
  '@railsblueprint', '@browsermcp', '@jsep-plugin', '@types', '@azure',
  '@mcp-apps', '@nodelib', '@inquirer', '@isaacs', '@kayvan', '@upstash',
  '@apidevtools', '@babel', '@jridgewell', '@jsdevtools', '@liuli-util',
  '@cspotcode', '@floating-ui', '@playwright',
  'playwright', 'playwright-core', 'chrome-devtools-mcp',
  'commander', 'ws', 'accepts', 'ajv', 'get-shit-done-cc', 'skillsadd',
  'adm-zip', 'async', 'balanced-match', 'bluebird', 'brace-expansion',
  'ansi-escapes', 'bmad-method', 'openapi-zod-client', 'mcpm', 'playwriter',
  'chrome-devtools-mcp', 'skillsadd', 'azure-kusto-data', 'azure-kusto-ingest',
  'dotenv', 'shx', 'vscode-mcp-server', 'zod', '@upstash'
];

// ===== Platform-specific process enumeration =====

function getProcessesWin() {
  try {
    var raw = child_process.execSync(
      'wmic process get ProcessId,ParentProcessId,Name,CommandLine,KernelModeTime,UserModeTime,WorkingSetSize /format:csv',
      { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024, timeout: 10000 }
    );
    var lines = raw.split('\n').filter(function(l) { return l.trim() && !l.startsWith('Node,'); });
    return lines.map(function(l) {
      var p = l.trim().split(',');
      // CSV: Node,CommandLine,KernelModeTime,Name,ParentProcessId,ProcessId,UserModeTime,WorkingSetSize
      return {
        cmd: (p[1] || '').trim(),
        kernel: parseInt(p[2]) || 0,  // 100-nanosecond units
        name: (p[3] || '').trim(),
        ppid: parseInt(p[4]) || 0,
        pid: parseInt(p[5]) || 0,
        user: parseInt(p[6]) || 0,    // 100-nanosecond units
        rss: parseInt(p[7]) || 0
      };
    }).filter(function(p) { return p.pid > 0; });
  } catch(e) {
    return [];
  }
}

function getProcessesUnix() {
  try {
    // ps -eo pid,ppid,pcpu,rss,comm,args
    var raw = child_process.execSync(
      'ps -eo pid,ppid,pcpu,rss,comm,args',
      { encoding: 'utf8', maxBuffer: 10 * 1024 * 1024, timeout: 10000 }
    );
    var lines = raw.split('\n').slice(1).filter(function(l) { return l.trim(); });
    return lines.map(function(l) {
      var parts = l.trim().split(/\s+/);
      var pid = parseInt(parts[0]) || 0;
      var ppid = parseInt(parts[1]) || 0;
      var cpu = parseFloat(parts[2]) || 0;
      var rss = (parseInt(parts[3]) || 0) * 1024; // KB -> bytes
      var name = parts[4] || '';
      var cmd = parts.slice(5).join(' ');
      return { pid: pid, ppid: ppid, name: name, cmd: cmd, rss: rss, cpuPct: cpu, kernel: 0, user: 0 };
    }).filter(function(p) { return p.pid > 0; });
  } catch(e) {
    return [];
  }
}

function getProcessesLinuxProc() {
  // Read /proc/[pid]/stat for precise jiffies-based CPU
  try {
    var pids = fs.readdirSync('/proc').filter(function(d) { return /^\d+$/.test(d); });
    var hz = 100; // usually 100 on Linux
    try { hz = parseInt(child_process.execSync('getconf CLK_TCK', {encoding:'utf8'})) || 100; } catch(e) {}

    return pids.map(function(pidStr) {
      try {
        var stat = fs.readFileSync('/proc/' + pidStr + '/stat', 'utf8');
        var cmdline = fs.readFileSync('/proc/' + pidStr + '/cmdline', 'utf8').replace(/\0/g, ' ').trim();
        // Parse stat: pid (comm) state ppid ... utime stime ...
        var match = stat.match(/^(\d+)\s+\(([^)]+)\)\s+\S+\s+(\d+)\s+(?:\S+\s+){9}(\d+)\s+(\d+)/);
        if (!match) return null;
        var rssPages = parseInt(stat.split(/\s+/)[23]) || 0;
        return {
          pid: parseInt(match[1]),
          ppid: parseInt(match[3]),
          name: match[2],
          cmd: cmdline || match[2],
          kernel: Math.round((parseInt(match[5]) / hz) * 10000000), // stime -> 100ns units
          user: Math.round((parseInt(match[4]) / hz) * 10000000),   // utime -> 100ns units
          rss: rssPages * 4096
        };
      } catch(e) { return null; }
    }).filter(Boolean);
  } catch(e) {
    return [];
  }
}

function getProcesses() {
  if (PLATFORM === 'win32') return getProcessesWin();
  if (PLATFORM === 'linux' && fs.existsSync('/proc/1/stat')) return getProcessesLinuxProc();
  return getProcessesUnix();
}

// ===== Identify Claude processes =====

function isClaudeProcess(p) {
  if (PLATFORM === 'win32') return p.name === 'claude.exe';
  // macOS/Linux: binary name varies
  return p.name === 'claude' ||
         (p.cmd && (p.cmd.indexOf('/claude') !== -1 || p.cmd.indexOf('claude-code') !== -1));
}

// ===== Build process tree =====

function buildTree(procs, rootPids) {
  var childMap = {};
  procs.forEach(function(p) {
    if (!childMap[p.ppid]) childMap[p.ppid] = [];
    childMap[p.ppid].push(p);
  });

  function walk(pid, depth) {
    var results = [];
    var kids = childMap[pid] || [];
    kids.forEach(function(k) {
      results.push({ proc: k, depth: depth });
      results.push.apply(results, walk(k.pid, depth + 1));
    });
    return results;
  }

  var trees = {};
  rootPids.forEach(function(rpid) {
    trees[rpid] = walk(rpid, 1);
  });
  return trees;
}

// ===== CPU measurement =====

function measureCPU(sampleSec, callback) {
  var t1 = getProcesses();
  var start = Date.now();

  setTimeout(function() {
    var t2 = getProcesses();
    var elapsed = (Date.now() - start) / 1000;

    // Build t1 lookup
    var m1 = {};
    t1.forEach(function(p) { m1[p.pid] = p; });

    // Calculate CPU delta for each process
    var results = t2.map(function(p) {
      var prev = m1[p.pid];
      var cpuPct;
      if (prev && (PLATFORM === 'win32' || (PLATFORM === 'linux' && fs.existsSync('/proc/1/stat')))) {
        var dKernel = (p.kernel - prev.kernel) / 10000; // 100ns -> ms
        var dUser = (p.user - prev.user) / 10000;
        cpuPct = ((dKernel + dUser) / (elapsed * 1000)) * 100;
      } else if (p.cpuPct !== undefined) {
        cpuPct = p.cpuPct; // macOS ps gives instantaneous %
      } else {
        cpuPct = null;
      }
      p.cpuPct = cpuPct;
      return p;
    });

    callback(results, elapsed);
  }, sampleSec * 1000);
}

// ===== NPX cache audit =====

function auditNpxCache() {
  var cacheDir;
  if (PLATFORM === 'win32') {
    cacheDir = path.join(process.env.LOCALAPPDATA || '', 'npm-cache', '_npx');
  } else {
    cacheDir = path.join(process.env.HOME || '~', '.npm', '_npx');
  }

  if (!fs.existsSync(cacheDir)) return { dir: cacheDir, entries: [], unknown: [] };

  var entries = [];
  var unknown = [];

  try {
    var dirs = fs.readdirSync(cacheDir);
    dirs.forEach(function(d) {
      var modDir = path.join(cacheDir, d, 'node_modules');
      if (!fs.existsSync(modDir)) return;

      var pkgs;
      try { pkgs = fs.readdirSync(modDir); } catch(e) { return; }

      var stat;
      try { stat = fs.statSync(path.join(cacheDir, d)); } catch(e) { return; }

      // Read package.json to find direct (explicitly installed) packages
      var topLevel = [];
      try {
        var pkgJsonPath = path.join(cacheDir, d, 'package.json');
        if (fs.existsSync(pkgJsonPath)) {
          var pkgJson = JSON.parse(fs.readFileSync(pkgJsonPath, 'utf8'));
          topLevel = Object.keys(pkgJson.dependencies || {});
        }
      } catch(e) {}
      // hasPkgJson means we reliably know the direct deps
      var hasPkgJson = topLevel.length > 0;

      // Fallback: list non-hidden, non-scoped top-level dirs
      // These are flat installs (no package.json) -- skip per-package audit
      if (!hasPkgJson) {
        topLevel = pkgs.filter(function(p) {
          return p[0] !== '.' && p !== 'node_modules';
        });
      }

      var entry = {
        hash: d,
        packages: topLevel,
        modified: stat.mtime.toISOString().split('T')[0],
        hasManifest: hasPkgJson
      };
      entries.push(entry);

      // Only audit entries with package.json (reliable direct-dep list)
      if (hasPkgJson) {
        topLevel.forEach(function(pkg) {
          var isKnown = KNOWN_PACKAGES.some(function(k) {
            if (pkg === k) return true;
            if (k.startsWith('@') && pkg.startsWith(k + '/')) return true;
            if (k.startsWith('@') && pkg.startsWith(k)) return true;
            return false;
          });
          if (!isKnown) {
            unknown.push({ hash: d, package: pkg, modified: entry.modified });
          }
        });
      }
    });
  } catch(e) {}

  return { dir: cacheDir, entries: entries, unknown: unknown };
}

// ===== Detect orphan node processes =====

function findOrphans(procs, claudePids) {
  // Collect all PIDs in Claude process trees
  var inTree = {};
  var childMap = {};
  procs.forEach(function(p) {
    if (!childMap[p.ppid]) childMap[p.ppid] = [];
    childMap[p.ppid].push(p);
  });

  function markTree(pid) {
    inTree[pid] = true;
    (childMap[pid] || []).forEach(function(k) { markTree(k.pid); });
  }
  claudePids.forEach(markTree);

  return procs.filter(function(p) {
    var isNode = p.name === 'node.exe' || p.name === 'node' ||
                 p.name === 'npm.exe' || p.name === 'npm' ||
                 p.name === 'npx.exe' || p.name === 'npx';
    return isNode && !inTree[p.pid];
  });
}

// ===== Classify tab state =====

function classifyTabState(treeNodes) {
  // ACTIVE = has running bash/cmd children doing work
  // IDLE = only mcp-manager and idle MCP servers
  var hasActiveBash = treeNodes.some(function(n) {
    var p = n.proc;
    var isBash = p.name === 'bash.exe' || p.name === 'bash' || p.name === 'sh' || p.name === 'zsh';
    return isBash && p.cpuPct !== null && p.cpuPct > 1.0;
  });
  var hasActiveNode = treeNodes.some(function(n) {
    var p = n.proc;
    var isNode = p.name === 'node.exe' || p.name === 'node';
    return isNode && p.cpuPct !== null && p.cpuPct > 5.0;
  });
  return (hasActiveBash || hasActiveNode) ? 'ACTIVE' : 'IDLE';
}

// ===== Format helpers =====

function fmtBytes(b) {
  if (b > 1073741824) return (b / 1073741824).toFixed(1) + ' GB';
  if (b > 1048576) return (b / 1048576).toFixed(0) + ' MB';
  if (b > 1024) return (b / 1024).toFixed(0) + ' KB';
  return b + ' B';
}

function fmtCpu(pct) {
  if (pct === null || pct === undefined) return 'N/A';
  return pct.toFixed(1) + '%';
}

function truncCmd(cmd, maxLen) {
  if (!cmd) return '';
  cmd = cmd.replace(/\s+/g, ' ');
  if (cmd.length > maxLen) return cmd.substring(0, maxLen - 3) + '...';
  return cmd;
}

// ===== Main report =====

function runReport(callback) {
  var report = { timestamp: new Date().toISOString(), platform: PLATFORM, tabs: [], orphans: [], npxAudit: null, summary: {} };

  if (SECURITY_ONLY) {
    // Quick security audit -- no CPU sampling needed
    var procs = getProcesses();
    var claudeProcs = procs.filter(isClaudeProcess);
    var claudePids = claudeProcs.map(function(p) { return p.pid; });

    report.orphans = findOrphans(procs, claudePids).map(function(p) {
      return { pid: p.pid, ppid: p.ppid, name: p.name, cmd: truncCmd(p.cmd, 120) };
    });
    report.npxAudit = auditNpxCache();
    report.summary = {
      tabCount: claudeProcs.length, idleCount: 0, activeCount: 0,
      totalCpu: 'N/A', totalRam: 'N/A',
      orphanCount: report.orphans.length,
      unknownPkgCount: report.npxAudit.unknown.length,
      alerts: []
    };
    if (report.orphans.length > 0) report.summary.alerts.push(report.orphans.length + ' orphan node process(es)');
    if (report.npxAudit.unknown.length > 0) report.summary.alerts.push(report.npxAudit.unknown.length + ' unknown package(s) in npx cache');
    callback(report);
    return;
  }

  measureCPU(SAMPLE_SEC, function(procs, elapsed) {
    report.sampleSeconds = elapsed;

    var claudeProcs = procs.filter(isClaudeProcess);
    var claudePids = claudeProcs.map(function(p) { return p.pid; });
    var trees = buildTree(procs, claudePids);

    var totalCpu = 0;
    var totalRam = 0;
    var idleCount = 0;

    claudeProcs.forEach(function(cp) {
      var treeNodes = trees[cp.pid] || [];
      var state = classifyTabState(treeNodes);
      if (state === 'IDLE') idleCount++;

      var tabCpu = cp.cpuPct || 0;
      var tabRam = cp.rss;
      treeNodes.forEach(function(n) {
        tabCpu += (n.proc.cpuPct || 0);
        tabRam += n.proc.rss;
      });
      totalCpu += tabCpu;
      totalRam += tabRam;

      var children = treeNodes.map(function(n) {
        return {
          pid: n.proc.pid,
          name: n.proc.name,
          cpu: fmtCpu(n.proc.cpuPct),
          cpuRaw: n.proc.cpuPct,
          ram: fmtBytes(n.proc.rss),
          ramRaw: n.proc.rss,
          cmd: truncCmd(n.proc.cmd, 100),
          depth: n.depth
        };
      });

      report.tabs.push({
        pid: cp.pid,
        ppid: cp.ppid,
        cpu: fmtCpu(cp.cpuPct),
        cpuRaw: cp.cpuPct,
        ram: fmtBytes(cp.rss),
        ramRaw: cp.rss,
        totalCpu: fmtCpu(tabCpu),
        totalRam: fmtBytes(tabRam),
        state: state,
        children: children
      });
    });

    // Orphan detection
    report.orphans = findOrphans(procs, claudePids).map(function(p) {
      return { pid: p.pid, ppid: p.ppid, name: p.name, cmd: truncCmd(p.cmd, 120), cpu: fmtCpu(p.cpuPct) };
    });

    // NPX audit
    report.npxAudit = auditNpxCache();

    // Summary
    report.summary = {
      tabCount: claudeProcs.length,
      idleCount: idleCount,
      activeCount: claudeProcs.length - idleCount,
      totalCpu: fmtCpu(totalCpu),
      totalCpuRaw: totalCpu,
      totalRam: fmtBytes(totalRam),
      totalRamRaw: totalRam,
      orphanCount: report.orphans.length,
      unknownPkgCount: report.npxAudit.unknown.length,
      alerts: []
    };

    // Generate alerts
    if (totalCpu > 50) {
      report.summary.alerts.push('HIGH CPU: ' + fmtCpu(totalCpu) + ' total across ' + claudeProcs.length + ' tabs');
    }
    report.tabs.forEach(function(t) {
      if (t.state === 'IDLE' && t.cpuRaw > 20) {
        report.summary.alerts.push('IDLE TAB PID ' + t.pid + ' using ' + t.cpu + ' CPU');
      }
    });
    if (report.orphans.length > 0) {
      report.summary.alerts.push(report.orphans.length + ' orphan node process(es) detected');
    }
    if (report.npxAudit.unknown.length > 0) {
      report.summary.alerts.push(report.npxAudit.unknown.length + ' unknown package(s) in npx cache');
    }

    callback(report);
  });
}

// ===== Text formatter =====

function formatText(report) {
  var out = [];
  var sep = '='.repeat(72);
  var thin = '-'.repeat(72);

  out.push(sep);
  out.push('  CLAUDE MONITOR REPORT');
  out.push('  ' + report.timestamp + '  |  Platform: ' + report.platform);
  if (report.sampleSeconds) out.push('  CPU sample: ' + report.sampleSeconds.toFixed(1) + 's');
  out.push(sep);

  if (report.summary.alerts && report.summary.alerts.length > 0) {
    out.push('');
    out.push('  [!] ALERTS:');
    report.summary.alerts.forEach(function(a) { out.push('      * ' + a); });
  }

  // Summary
  out.push('');
  out.push('  SUMMARY');
  out.push(thin);
  var s = report.summary;
  out.push('  Tabs: ' + s.tabCount + ' (' + s.activeCount + ' active, ' + s.idleCount + ' idle)');
  out.push('  Total CPU: ' + s.totalCpu + '  |  Total RAM: ' + s.totalRam);
  out.push('  Orphan processes: ' + s.orphanCount + '  |  Unknown npx packages: ' + s.unknownPkgCount);

  // Tab details
  if (report.tabs.length > 0) {
    out.push('');
    out.push('  TAB PROCESS TREES');
    out.push(thin);

    report.tabs.forEach(function(tab, idx) {
      out.push('');
      out.push('  [Tab ' + (idx+1) + '] PID ' + tab.pid + '  |  State: ' + tab.state +
               '  |  CPU: ' + tab.cpu + '  |  RAM: ' + tab.ram +
               '  |  Total: ' + tab.totalCpu + ' / ' + tab.totalRam);

      if (tab.children.length > 0) {
        tab.children.forEach(function(c) {
          var indent = '  ' + '  '.repeat(c.depth);
          var cpuFlag = (c.cpuRaw !== null && c.cpuRaw > 5) ? ' [!]' : '';
          out.push(indent + '|- ' + c.name + ' (PID ' + c.pid + ') CPU:' + c.cpu + ' RAM:' + c.ram + cpuFlag);
          if (c.cmd) out.push(indent + '   ' + c.cmd);
        });
      } else {
        out.push('    (no children)');
      }
    });
  }

  // Orphans
  if (report.orphans.length > 0) {
    out.push('');
    out.push('  ORPHAN PROCESSES (node/npm/npx not under any Claude tab)');
    out.push(thin);
    report.orphans.forEach(function(o) {
      out.push('  PID ' + o.pid + ' (ppid ' + o.ppid + ') ' + o.name +
               (o.cpu ? ' CPU:' + o.cpu : ''));
      if (o.cmd) out.push('    ' + o.cmd);
    });
  }

  // NPX audit
  if (report.npxAudit) {
    out.push('');
    out.push('  NPX CACHE AUDIT (' + report.npxAudit.dir + ')');
    out.push(thin);
    out.push('  Total cached entries: ' + report.npxAudit.entries.length);

    if (report.npxAudit.unknown.length > 0) {
      out.push('');
      out.push('  [!] UNKNOWN PACKAGES:');
      report.npxAudit.unknown.forEach(function(u) {
        out.push('    * ' + u.package + ' (hash: ' + u.hash + ', modified: ' + u.modified + ')');
      });
    } else {
      out.push('  All packages match known allowlist. OK.');
    }

    out.push('');
    out.push('  Full inventory:');
    report.npxAudit.entries.forEach(function(e) {
      out.push('    ' + e.hash.substring(0,8) + '  ' + e.modified + '  ' +
               e.packages.slice(0, 5).join(', ') +
               (e.packages.length > 5 ? ' (+' + (e.packages.length - 5) + ' more)' : ''));
    });
  }

  out.push('');
  out.push(sep);
  return out.join('\n');
}

// ===== Run =====

function run() {
  runReport(function(report) {
    var output;
    if (JSON_OUT) {
      output = JSON.stringify(report, null, 2);
    } else {
      output = formatText(report);
    }

    if (OUT_FILE) {
      var outPath = OUT_FILE;
      if (outPath.startsWith('~/')) outPath = path.join(os.homedir(), outPath.substring(2));
      fs.writeFileSync(outPath, output, 'utf8');
      console.log('[SAVED] ' + outPath);
    }

    console.log(output);

    if (WATCH_SEC > 0) {
      setTimeout(run, WATCH_SEC * 1000);
    }
  });
}

run();
