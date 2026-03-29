#!/usr/bin/env node
/**
 * Rule Manager Setup
 *
 * Installs rule-manager infrastructure:
 *   1. Ensures rule directories exist
 *   2. Installs writing-rules.md (meta-rule)
 *   3. Verifies existing rule frontmatter health
 *
 * No dependencies - rule-manager is a leaf node.
 *
 * Usage:
 *   node setup.js
 */

var fs = require('fs');
var path = require('path');
var os = require('os');

var HOME = os.homedir();
var CLAUDE_DIR = path.join(HOME, '.claude');
var UTILS_PATH = path.join(CLAUDE_DIR, 'super-manager', 'shared', 'setup-utils.js');

// Load shared utilities
var utils;
try {
  utils = require(UTILS_PATH);
} catch (e) {
  console.log('[rule-manager:setup] ERROR: Cannot load setup-utils.js');
  console.log('[rule-manager:setup] Expected at: ' + UTILS_PATH);
  console.log('[rule-manager:setup] ' + e.message);
  process.exit(1);
}

var MANAGER_NAME = 'rule-manager';
var p = utils.paths();
var CLAUDE_MD = path.join(HOME, '.claude', 'CLAUDE.md');

// Rule directories to ensure
var DIRS = [
  path.join(p.rulesDir, 'UserPromptSubmit'),
  path.join(p.rulesDir, 'Stop'),
  path.join(p.rulesDir, 'PreToolUse'),
  path.join(p.rulesDir, 'archive'),
  path.join(p.rulesDir, 'backups')
];

// ================================================================
// Embedded rule: writing-rules.md
// ================================================================

var WRITING_RULES_CONTENT = '---\n\
id: writing-rules\n\
name: Writing Rules\n\
keywords: [rule, keyword, keywords, trigger, match, matching, rules, meta, write, create, add, new, frontmatter, why]\n\
enabled: true\n\
priority: 10\n\
---\n\
\n\
# Writing Rules\n\
\n\
## WHY This Exists\n\
\n\
Rules use keyword matching to load contextual rules. Bad keywords mean rules never fire. This meta-rule ensures every rule file is written correctly so the keyword system works reliably.\n\
\n\
## Keyword Rules\n\
\n\
1. **Single words only** - never hyphenated phrases like `getting-started` or `how-it-works`\n\
   - Split into separate words: `getting`, `started`, `how`, `works`\n\
   - User types natural language, not kebab-case\n\
\n\
2. **Short words the user would actually type** - think about what triggers the prompt\n\
   - Good: `bash`, `script`, `write`, `js`\n\
   - Bad: `bash-scripting-safety`, `javascript-heredoc-pattern`\n\
\n\
3. **Include verb forms** - `write`, `writing`, `create`, `add`, `edit`, `fix`, `debug`\n\
\n\
4. **Include synonyms** - `docs` AND `documentation`, `repo` AND `repository`\n\
\n\
5. **No redundant keywords** - if `mcp` covers it, don\'t also add `mcp-server`, `mcp-management`\n\
\n\
6. **5-15 keywords per rule** - fewer than 5 = too narrow, more than 15 = too noisy\n\
\n\
## Frontmatter Format\n\
\n\
```yaml\n\
---\n\
id: kebab-case-id\n\
name: Human Readable Name\n\
keywords: [word1, word2, word3]\n\
enabled: true\n\
priority: 10\n\
---\n\
```\n\
\n\
- `id` matches filename (without .md)\n\
- `priority` default 10, use 100 for critical rules (like review-rules)\n\
- `enabled` defaults to true\n\
\n\
## Content Structure\n\
\n\
Every rule MUST have:\n\
\n\
1. **Title** - `# Short Name`\n\
2. **WHY** section - why this rule exists (not just what to do)\n\
3. **What To Do** - concrete actions\n\
4. **Do NOT** (optional) - common mistakes to avoid\n\
\n\
## Where Rules Live\n\
\n\
Single location: `~/.claude/rule-book/UserPromptSubmit/`\n\
\n\
rule-manager reads/writes here directly. No copies elsewhere.\n\
\n\
## Keyword Selection Process\n\
\n\
When creating a new rule, review the current chat history to find what words the user actually typed that should have triggered this rule. Those words become keywords.\n\
\n\
1. **Look at what the user typed** - the exact words from the conversation that led to needing this rule\n\
2. **Be generous** - better to match too often than miss when needed\n\
3. **Check existing rules** - run `ls ~/.claude/rule-book/UserPromptSubmit/` to see what\'s already covered\n\
\n\
## Keywords vs Patterns\n\
\n\
- **Keywords** = single words for UserPromptSubmit matching (e.g. `bash`, `mcp`, `deploy`)\n\
- **Patterns** = regex for Stop hook response matching (e.g. `(should|want)\\s.{0,20}fix`)\n\
- NEVER use multi-word keywords. Use patterns for phrase matching.\n\
- `add_item()` auto-sanitizes: splits multi-word and hyphenated keywords into singles.\n\
\n\
## Do NOT\n\
\n\
- Do NOT use multi-word or hyphenated keywords (enforced by `_sanitize_keywords()`)\n\
- Do NOT put rules in CLAUDE.md (use rule files)\n\
- Do NOT create hooks when a rule would work\n\
- Do NOT skip the WHY section\n\
- Do NOT maintain duplicate copies of rules anywhere\n';

// ================================================================
// Step 1: Ensure directories
// ================================================================

function ensureDirectories() {
  var created = [];
  var existed = [];
  for (var i = 0; i < DIRS.length; i++) {
    if (fs.existsSync(DIRS[i])) {
      existed.push(DIRS[i]);
    } else {
      fs.mkdirSync(DIRS[i], { recursive: true });
      created.push(DIRS[i]);
    }
  }
  return { created: created, existed: existed };
}

// ================================================================
// Step 2: Install writing-rules.md
// ================================================================

function installWritingRules(backupDir) {
  var result = utils.installInstruction({
    id: 'writing-rules',
    content: WRITING_RULES_CONTENT,
    event: 'UserPromptSubmit'
  });

  // Track if we created a new file
  if (result.method !== 'skipped' && backupDir) {
    utils.trackCreatedFile(backupDir, result.path);
  }

  return result;
}

// ================================================================
// Step 3: Verify frontmatter health of all rules
// ================================================================

function verifyFrontmatter() {
  var results = { healthy: [], warnings: [] };
  var events = ['UserPromptSubmit', 'Stop'];

  for (var e = 0; e < events.length; e++) {
    var eventDir = path.join(p.rulesDir, events[e]);
    if (!fs.existsSync(eventDir)) continue;

    var files;
    try {
      files = fs.readdirSync(eventDir);
    } catch (err) {
      results.warnings.push('Cannot read ' + eventDir + ': ' + err.message);
      continue;
    }

    for (var f = 0; f < files.length; f++) {
      if (!files[f].endsWith('.md')) continue;
      var filePath = path.join(eventDir, files[f]);
      var content;
      try {
        content = fs.readFileSync(filePath, 'utf8');
      } catch (err) {
        results.warnings.push(files[f] + ': cannot read (' + err.message + ')');
        continue;
      }

      var issues = [];

      // Check frontmatter exists
      if (!content.startsWith('---')) {
        issues.push('no frontmatter');
      } else {
        var endIdx = content.indexOf('---', 3);
        if (endIdx === -1) {
          issues.push('malformed frontmatter (no closing ---)');
        } else {
          var fm = content.substring(3, endIdx);

          // Check required fields
          if (fm.indexOf('id:') === -1) {
            issues.push('missing id');
          }
          if (fm.indexOf('enabled:') === -1) {
            issues.push('missing enabled');
          }

          // UserPromptSubmit needs keywords, Stop needs keywords or pattern
          if (events[e] === 'UserPromptSubmit') {
            if (fm.indexOf('keywords:') === -1) {
              issues.push('missing keywords');
            }
          } else if (events[e] === 'Stop') {
            if (fm.indexOf('keywords:') === -1 && fm.indexOf('pattern:') === -1) {
              issues.push('missing keywords or pattern');
            }
          }
        }
      }

      if (issues.length > 0) {
        results.warnings.push(events[e] + '/' + files[f] + ': ' + issues.join(', '));
      } else {
        results.healthy.push(events[e] + '/' + files[f]);
      }
    }
  }

  return results;
}

// ================================================================
// CLAUDE.md injection (auto-added by rule-manager setup)
// ================================================================

var CLAUDE_MD_MARKER = '<!-- rule-manager-rules -->';
var CLAUDE_MD_SECTION = [
  '',
  CLAUDE_MD_MARKER,
  '## Rule System (auto-added by rule-manager setup)',
  '',
  'Rules live in `~/.claude/rule-book/` -- NOT `~/.claude/rules/`.',
  'Claude Code natively loads all .md files from `~/.claude/rules/` on every prompt (~50KB wasted context).',
  'Moving rules to `rule-book/` prevents native loading. Hooks inject rules only when keywords match.',
  '',
  '```',
  '~/.claude/rule-book/',
  '  UserPromptSubmit/   # Injected when prompt keywords match (sm-userpromptsubmit.js)',
  '  Stop/               # Checked against response text (sm-stop.js)',
  '  PreToolUse/         # Checked before tool calls (sm-pretooluse.js)',
  '```',
  '',
  'State files (logs, caches) stay in `~/.claude/rules/` -- only .md rule files moved.',
  '- Add rules: use rule-manager skill or write .md files directly in rule-book/',
  '- NEVER put .md files in `~/.claude/rules/` -- they get loaded on every prompt',
  CLAUDE_MD_MARKER,
  ''
].join('\n');

function injectClaudeMdSection() {
  if (!fs.existsSync(CLAUDE_MD)) return { action: 'no_file' };
  var content = fs.readFileSync(CLAUDE_MD, 'utf8');
  if (content.indexOf(CLAUDE_MD_MARKER) !== -1) return { action: 'already_present' };
  fs.writeFileSync(CLAUDE_MD, content + CLAUDE_MD_SECTION, 'utf8');
  return { action: 'injected' };
}

function removeClaudeMdSection() {
  if (!fs.existsSync(CLAUDE_MD)) return false;
  var content = fs.readFileSync(CLAUDE_MD, 'utf8');
  var startIdx = content.indexOf(CLAUDE_MD_MARKER);
  if (startIdx === -1) return false;
  var endIdx = content.indexOf(CLAUDE_MD_MARKER, startIdx + 1);
  if (endIdx === -1) return false;
  var endOfMarker = endIdx + CLAUDE_MD_MARKER.length;
  var before = content.slice(0, startIdx).replace(/\n+$/, '\n');
  var after = content.slice(endOfMarker).replace(/^\n+/, '\n');
  fs.writeFileSync(CLAUDE_MD, before + after, 'utf8');
  return true;
}

// ================================================================
// Main
// ================================================================

function main() {
  console.log('');
  console.log('[rule-manager:setup] Starting...');
  console.log('');

  // -- Backup --
  console.log('[1/4] Creating backup...');
  var filesToBackup = [p.settingsJson, CLAUDE_MD];

  // Also backup writing-rules.md if it exists
  var existingWI = path.join(p.rulesDir, 'UserPromptSubmit', 'writing-rules.md');
  if (fs.existsSync(existingWI)) {
    filesToBackup.push(existingWI);
  }

  var bk = utils.backup(MANAGER_NAME, filesToBackup);
  console.log('[rule-manager:setup]   Backup: ' + bk.backupDir);

  // -- Step 1: Directories --
  console.log('[2/4] Ensuring directories...');
  var dirs = ensureDirectories();
  if (dirs.created.length > 0) {
    for (var i = 0; i < dirs.created.length; i++) {
      console.log('[rule-manager:setup]   Created: ' + path.relative(CLAUDE_DIR, dirs.created[i]));
      utils.trackCreatedFile(bk.backupDir, dirs.created[i]);
    }
  }
  if (dirs.existed.length > 0) {
    console.log('[rule-manager:setup]   ' + dirs.existed.length + ' dir(s) already existed');
  }

  // -- Step 2: Install rule --
  console.log('[3/4] Installing rules...');
  var instResult = installWritingRules(bk.backupDir);
  console.log('[rule-manager:setup]   writing-rules.md: ' + instResult.method);

  // -- Step 3: Inject CLAUDE.md section --
  console.log('[4/4] Injecting CLAUDE.md rule-book docs...');
  var mdResult = injectClaudeMdSection();
  console.log('[rule-manager:setup]   CLAUDE.md: ' + mdResult.action);

  // -- Verify frontmatter health --
  console.log('');
  console.log('[rule-manager:setup] Verifying frontmatter health...');
  var fmResults = verifyFrontmatter();
  console.log('[rule-manager:setup]   Healthy: ' + fmResults.healthy.length + ' rule(s)');
  if (fmResults.warnings.length > 0) {
    console.log('[rule-manager:setup]   Warnings: ' + fmResults.warnings.length);
    for (var w = 0; w < fmResults.warnings.length; w++) {
      console.log('[rule-manager:setup]     [!] ' + fmResults.warnings[w]);
    }
  }

  // -- Summary --
  var warnings = [];
  if (fmResults.warnings.length > 0) {
    warnings.push(fmResults.warnings.length + ' rule(s) have frontmatter issues');
  }

  utils.printSummary({
    manager: MANAGER_NAME,
    backup: bk,
    instructions: [instResult],
    hooks: [],
    warnings: warnings
  });
}

// ================================================================
// Exports
// ================================================================

module.exports = {
  main: main,
  ensureDirectories: ensureDirectories,
  installWritingRules: installWritingRules,
  verifyFrontmatter: verifyFrontmatter,
  injectClaudeMdSection: injectClaudeMdSection,
  removeClaudeMdSection: removeClaudeMdSection,
  WRITING_RULES_CONTENT: WRITING_RULES_CONTENT
};

if (require.main === module) main();
