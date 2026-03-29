#!/usr/bin/env node
/**
 * Code Review Engine
 * Scans Claude Code config for consistency issues, secret leaks, and dead references.
 * Outputs structured JSON report to stdout.
 *
 * Usage:
 *   node review.js [target-path] [--secrets-only] [--config-only] [--json]
 *
 * Default target: ~/.claude/
 * No npm dependencies - pure Node.js (fs, path, os, crypto, child_process).
 */

var fs = require('fs');
var path = require('path');
var os = require('os');
var crypto = require('crypto');
var cp = require('child_process');

var HOME = os.homedir();
var CLAUDE_DIR = path.join(HOME, '.claude');

// ================================================================
// Secret detection patterns (aligned with security-scan/scanner.py)
// ================================================================

var SECRET_PATTERNS = [
  { id: 'hardcoded_password', severity: 'CRITICAL', regex: /(password|passwd|pwd)\s*[:=]\s*['"][^'"]{4,}['"]/gi, label: 'Hardcoded password' },
  { id: 'hardcoded_secret', severity: 'CRITICAL', regex: /(secret|api_key|apikey|token|bearer|auth_token)\s*[:=]\s*['"][^'"]{8,}['"]/gi, label: 'Hardcoded secret/token' },
  { id: 'aws_key', severity: 'CRITICAL', regex: /AKIA[0-9A-Z]{16}/g, label: 'AWS access key' },
  { id: 'private_key', severity: 'CRITICAL', regex: /-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----/g, label: 'Private key' },
  { id: 'bearer_token', severity: 'CRITICAL', regex: /[Bb]earer\s+[A-Za-z0-9\-._~+\/]{20,}/g, label: 'Bearer token' },
  { id: 'jwt_token', severity: 'WARNING', regex: /eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/g, label: 'JWT token' },
  { id: 'generic_key', severity: 'WARNING', regex: /['"][A-Za-z0-9]{32,}['"]/g, label: 'Long opaque string (possible key)' },
];

// Files/dirs to skip
var SKIP_DIRS = ['node_modules', '.git', 'archive', 'file-history', '__pycache__', 'backups'];
var SKIP_FILES = ['.gitignore', 'package-lock.json', 'yarn.lock'];
var SCAN_EXTENSIONS = ['.md', '.js', '.json', '.yaml', '.yml', '.py', '.sh', '.env', '.txt', '.toml'];

// ================================================================
// Helpers
// ================================================================

function fileHash(filePath) {
  try {
    var content = fs.readFileSync(filePath);
    return crypto.createHash('sha256').update(content).digest('hex').slice(0, 12);
  } catch (e) { return null; }
}

function walkDir(dir, extensions, skipDirs) {
  var results = [];
  if (!fs.existsSync(dir)) return results;
  try {
    var entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch (e) { return results; }
  for (var i = 0; i < entries.length; i++) {
    var entry = entries[i];
    var fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (skipDirs.indexOf(entry.name) === -1) {
        results = results.concat(walkDir(fullPath, extensions, skipDirs));
      }
    } else if (entry.isFile()) {
      var ext = path.extname(entry.name).toLowerCase();
      if (SKIP_FILES.indexOf(entry.name) === -1 && extensions.indexOf(ext) !== -1) {
        results.push(fullPath);
      }
    }
  }
  return results;
}

function readFileSafe(filePath) {
  try { return fs.readFileSync(filePath, 'utf8'); } catch (e) { return null; }
}

function relPath(absPath) {
  return absPath.replace(HOME, '~').replace(/\\/g, '/');
}

// ================================================================
// Category 1: Config Consistency
// ================================================================

/**
 * Check 1: Phantom tools -- find mcp__*__ references that don't match real tools.
 */
function checkPhantomTools(targetDir, realTools) {
  var issues = [];
  var files = walkDir(targetDir, ['.md', '.js', '.json', '.py'], SKIP_DIRS);
  var toolRefRegex = /mcp__([a-zA-Z0-9_-]+)__([a-zA-Z0-9_-]+)/g;

  for (var i = 0; i < files.length; i++) {
    var content = readFileSafe(files[i]);
    if (!content) continue;
    var match;
    var lineNum = 0;
    var lines = content.split('\n');
    for (var ln = 0; ln < lines.length; ln++) {
      var line = lines[ln];
      toolRefRegex.lastIndex = 0;
      while ((match = toolRefRegex.exec(line)) !== null) {
        var fullTool = match[0];
        var server = match[1];
        var tool = match[2];
        // Skip strikethrough/negation contexts (~~tool~~ or "don't exist" or "not a real tool")
        if (line.indexOf('~~' + fullTool + '~~') !== -1) continue;
        if (line.indexOf("don't exist") !== -1 || line.indexOf('not a real tool') !== -1) continue;
        if (line.indexOf('NOT exist') !== -1 || line.indexOf('do NOT') !== -1) continue;
        if (line.indexOf('fake tool') !== -1 || line.indexOf('WRONG') !== -1) continue;

        // Check against real tools if we have them
        if (realTools && realTools.length > 0) {
          var isReal = false;
          for (var t = 0; t < realTools.length; t++) {
            if (realTools[t] === fullTool || realTools[t].indexOf(server + '__') !== -1) {
              isReal = true;
              break;
            }
          }
          if (!isReal) {
            issues.push({
              severity: 'CRITICAL',
              file: relPath(files[i]),
              line: ln + 1,
              message: 'References non-existent tool ' + fullTool,
              category: 'phantom-tool'
            });
          }
        }
      }
    }
  }
  return issues;
}

/**
 * Check 2: Path drift -- same-name files in different dirs with different hashes.
 */
function checkPathDrift(targetDir) {
  var issues = [];
  var files = walkDir(targetDir, SCAN_EXTENSIONS, SKIP_DIRS);
  var byName = {};

  for (var i = 0; i < files.length; i++) {
    var name = path.basename(files[i]);
    if (!byName[name]) byName[name] = [];
    byName[name].push(files[i]);
  }

  var keys = Object.keys(byName);
  for (var k = 0; k < keys.length; k++) {
    var copies = byName[keys[k]];
    if (copies.length < 2) continue;
    // Compare hashes
    var hashes = {};
    for (var c = 0; c < copies.length; c++) {
      var h = fileHash(copies[c]);
      if (h) {
        if (!hashes[h]) hashes[h] = [];
        hashes[h].push(copies[c]);
      }
    }
    var uniqueHashes = Object.keys(hashes);
    if (uniqueHashes.length > 1) {
      var locations = copies.map(relPath).join(', ');
      issues.push({
        severity: 'WARNING',
        file: keys[k],
        line: 0,
        message: keys[k] + ' exists in ' + copies.length + ' locations with different content: ' + locations,
        category: 'path-drift'
      });
    }
  }
  return issues;
}

/**
 * Check 3: Dead references -- file paths in docs/instructions that don't exist.
 */
function checkDeadReferences(targetDir) {
  var issues = [];
  var files = walkDir(targetDir, ['.md', '.js'], SKIP_DIRS);
  // Match file-like paths: ~/..., ~/.claude/..., /path/to/..., relative ./... etc.
  var pathRegex = /(?:~\/|\.\/|[A-Za-z]:\\)[^\s'"`)]+\.(yaml|yml|json|md|js|py|sh|env|toml)/g;

  for (var i = 0; i < files.length; i++) {
    var content = readFileSafe(files[i]);
    if (!content) continue;
    var lines = content.split('\n');
    for (var ln = 0; ln < lines.length; ln++) {
      var line = lines[ln];
      // Skip code blocks, comments about format
      if (line.trim().indexOf('#') === 0 && line.indexOf('/') === -1) continue;
      pathRegex.lastIndex = 0;
      var match;
      while ((match = pathRegex.exec(line)) !== null) {
        var refPath = match[0];
        // Resolve ~ to HOME
        var resolved = refPath.replace(/^~/, HOME).replace(/\//g, path.sep);
        // Skip template/example paths
        if (refPath.indexOf('<') !== -1 || refPath.indexOf('{') !== -1) continue;
        if (refPath.indexOf('example') !== -1 || refPath.indexOf('placeholder') !== -1) continue;
        if (refPath.indexOf('/path/to/') !== -1 || refPath.indexOf('/tmp/') !== -1) continue;
        // Skip strikethrough
        if (line.indexOf('~~') !== -1) continue;
        // Check existence
        if (!fs.existsSync(resolved)) {
          issues.push({
            severity: 'INFO',
            file: relPath(files[i]),
            line: ln + 1,
            message: 'References non-existent path: ' + refPath,
            category: 'dead-reference'
          });
        }
      }
    }
  }
  return issues;
}

// ================================================================
// Category 2: Secret Scanning
// ================================================================

/**
 * Scan files for secret patterns. Cross-reference with credential-manager if available.
 */
function scanSecrets(targetDir) {
  var issues = [];
  var files = walkDir(targetDir, SCAN_EXTENSIONS, SKIP_DIRS);

  // Check if credential helper exists
  var credHelper = path.join(CLAUDE_DIR, 'super-manager', 'credentials', 'claude-cred.js');
  var hasCred = fs.existsSync(credHelper);

  for (var i = 0; i < files.length; i++) {
    var filePath = files[i];
    var content = readFileSafe(filePath);
    if (!content) continue;

    // Skip files that are clearly documentation about secrets (like this review.js itself)
    var basename = path.basename(filePath);
    if (basename === 'review.js' || basename === 'scanner.py' || basename === 'SKILL.md') continue;
    if (basename === 'CLAUDE.md' && filePath.indexOf('skills') !== -1) continue;

    var lines = content.split('\n');
    for (var ln = 0; ln < lines.length; ln++) {
      var line = lines[ln];
      // Skip comment-only lines in code files
      if (line.trim().indexOf('//') === 0 || line.trim().indexOf('#') === 0) continue;
      // Skip lines that are regex patterns or documentation
      if (line.indexOf('regex') !== -1 || line.indexOf('PATTERN') !== -1) continue;
      if (line.indexOf('example') !== -1 || line.indexOf('Example') !== -1) continue;

      for (var p = 0; p < SECRET_PATTERNS.length; p++) {
        var pat = SECRET_PATTERNS[p];
        pat.regex.lastIndex = 0;
        if (pat.regex.test(line)) {
          // For generic_key, skip if line looks like a hash or ID field
          if (pat.id === 'generic_key') {
            if (line.indexOf('hash') !== -1 || line.indexOf('sha') !== -1) continue;
            if (line.indexOf('id') !== -1 || line.indexOf('Id') !== -1) continue;
          }

          var issue = {
            severity: pat.severity,
            file: relPath(filePath),
            line: ln + 1,
            message: pat.label + ' detected',
            category: 'secret',
            secretType: pat.id
          };

          // Try cross-reference with credential-manager
          if (hasCred) {
            issue.credentialManagerAvailable = true;
            issue.suggestion = 'Run: credential-manager store <service>/<KEY>';
          } else {
            issue.credentialManagerAvailable = false;
            issue.suggestion = 'Install credential-manager skill for keyring-backed secret storage';
          }

          issues.push(issue);
          break; // one match per line is enough
        }
      }
    }
  }
  return issues;
}

/**
 * Check git history for secrets that were ever committed.
 */
function checkGitHistory(targetDir) {
  var issues = [];
  try {
    // Check if target is a git repo
    cp.execSync('git -C "' + targetDir + '" rev-parse --git-dir', { stdio: 'pipe' });
  } catch (e) {
    return issues; // not a git repo
  }

  var secretFilePatterns = ['*.json', '*.yaml', '*.yml', '*.env', '*.toml'];
  for (var i = 0; i < secretFilePatterns.length; i++) {
    try {
      var output = cp.execSync(
        'git -C "' + targetDir + '" log --all --diff-filter=A -p -- "' + secretFilePatterns[i] + '" 2>/dev/null',
        { stdio: 'pipe', timeout: 10000, maxBuffer: 1024 * 1024 }
      ).toString();

      // Quick scan for secret patterns in git history
      var histLines = output.split('\n');
      for (var ln = 0; ln < histLines.length; ln++) {
        var line = histLines[ln];
        if (line.indexOf('+') !== 0) continue; // only added lines
        for (var p = 0; p < SECRET_PATTERNS.length; p++) {
          var pat = SECRET_PATTERNS[p];
          if (pat.id === 'generic_key') continue; // too noisy for git history
          pat.regex.lastIndex = 0;
          if (pat.regex.test(line)) {
            issues.push({
              severity: 'WARNING',
              file: 'git history',
              line: 0,
              message: pat.label + ' found in git history (may have been removed but is still in commits)',
              category: 'secret-history',
              secretType: pat.id
            });
            break;
          }
        }
      }
    } catch (e) {
      // timeout or other error, skip
    }
  }

  // Dedup git history issues
  var seen = {};
  return issues.filter(function (issue) {
    var key = issue.secretType + ':' + issue.message;
    if (seen[key]) return false;
    seen[key] = true;
    return true;
  });
}

// ================================================================
// Main
// ================================================================

function main() {
  var args = process.argv.slice(2);
  var targetDir = CLAUDE_DIR;
  var secretsOnly = false;
  var configOnly = false;
  var jsonOutput = true; // always JSON for Claude to parse

  for (var i = 0; i < args.length; i++) {
    if (args[i] === '--secrets-only') secretsOnly = true;
    else if (args[i] === '--config-only') configOnly = true;
    else if (args[i] === '--json') jsonOutput = true;
    else if (args[i][0] !== '-') targetDir = args[i].replace(/^~/, HOME);
  }

  var report = {
    timestamp: new Date().toISOString(),
    target: relPath(targetDir),
    config: [],
    secrets: [],
    security: [],
    summary: { critical: 0, warning: 0, info: 0 }
  };

  // Try to get real MCP tools list for phantom tool checking
  var realTools = [];
  try {
    // Read from mcpm tool list if available
    var mcpmState = path.join(CLAUDE_DIR, 'super-manager', 'state', 'mcp-tools-cache.json');
    if (fs.existsSync(mcpmState)) {
      var toolsData = JSON.parse(readFileSafe(mcpmState));
      if (toolsData && toolsData.tools) realTools = toolsData.tools;
    }
  } catch (e) { /* no cache, phantom tool check runs without verification */ }

  // Category 1: Config consistency
  if (!secretsOnly) {
    var phantomIssues = checkPhantomTools(targetDir, realTools);
    var driftIssues = checkPathDrift(targetDir);
    var deadRefIssues = checkDeadReferences(targetDir);
    report.config = phantomIssues.concat(driftIssues).concat(deadRefIssues);
  }

  // Category 2: Secret scanning
  if (!configOnly) {
    var secretIssues = scanSecrets(targetDir);
    var gitIssues = checkGitHistory(targetDir);
    report.secrets = secretIssues.concat(gitIssues);
  }

  // Tally
  var all = report.config.concat(report.secrets).concat(report.security);
  for (var j = 0; j < all.length; j++) {
    var sev = all[j].severity;
    if (sev === 'CRITICAL') report.summary.critical++;
    else if (sev === 'WARNING') report.summary.warning++;
    else report.summary.info++;
  }

  report.summary.total = all.length;

  console.log(JSON.stringify(report, null, 2));
  process.exit(report.summary.critical > 0 ? 1 : 0);
}

main();
