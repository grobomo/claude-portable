#!/usr/bin/env node
/**
 * @hook skill-mcp-claudemd-injector
 * @event UserPromptSubmit
 * @matcher *
 * @description Unified context injector with 3 modules:
 *   - claudemd: Injects global ~/.claude/CLAUDE.md
 *   - skill: Injects skill docs based on keyword matching
 *   - mcp: Suggests MCP servers based on keyword matching
 */
const fs = require('fs');
const path = require('path');

const HOOK_NAME = 'skill-mcp-claudemd-injector';
const EVENT_TYPE = 'UserPromptSubmit';
const HOME = process.env.HOME || process.env.USERPROFILE;
const LOG_FILE = path.join(HOME, '.claude', 'hooks', 'hooks.log');

// Logging with module name
function log(module, level, msg) {
  const ts = new Date().toISOString();
  fs.appendFileSync(LOG_FILE, `${ts} [${level}] [${EVENT_TYPE}] [${HOOK_NAME}:${module}] ${msg}\n`);
}

// ===== MODULE: claudemd =====
function moduleClaudeMd() {
  const claudeMdPath = path.join(HOME, '.claude', 'CLAUDE.md');
  try {
    if (fs.existsSync(claudeMdPath)) {
      const content = fs.readFileSync(claudeMdPath, 'utf-8');
      log('claudemd', 'INFO', 'injected global CLAUDE.md');
      return `<system-reminder>\nGlobal instructions from ~/.claude/CLAUDE.md:\n\n${content}\n</system-reminder>`;
    }
  } catch (e) {
    log('claudemd', 'ERROR', `failed: ${e.message}`);
  }
  log('claudemd', 'DEBUG', 'no global CLAUDE.md found');
  return null;
}

// ===== MODULE: skill =====
function moduleSkill(prompt) {
  const registryPath = path.join(HOME, '.claude', 'hooks', 'skill-registry.json');
  try {
    if (!fs.existsSync(registryPath)) {
      log('skill', 'DEBUG', 'no skill-registry.json');
      return null;
    }
    
    const registry = JSON.parse(fs.readFileSync(registryPath, 'utf-8'));
    const matched = [];
    
    for (const skill of registry.skills || []) {
      if (!skill.enabled) continue;
      const hit = (skill.keywords || []).some(kw => prompt.includes(kw.toLowerCase()));
      if (hit) matched.push(skill);
    }
    
    if (matched.length === 0) {
      log('skill', 'DEBUG', 'no skills matched');
      return null;
    }
    
    const injections = [];
    for (const skill of matched) {
      try {
        const skillPath = skill.skillPath.replace(/\//g, path.sep);
        if (fs.existsSync(skillPath)) {
          const content = fs.readFileSync(skillPath, 'utf-8');
          injections.push(`<skill-context name="${skill.name}" id="${skill.id}">\n${content}\n</skill-context>`);
        }
      } catch (e) {}
    }
    
    if (injections.length > 0) {
      log('skill', 'INFO', `injected ${matched.length} skills: ${matched.map(s => s.id).join(', ')}`);
      return `--- SKILL CONTEXT INJECTED ---\n${injections.join('\n\n')}\n--- END SKILL CONTEXT ---`;
    }
  } catch (e) {
    log('skill', 'ERROR', `failed: ${e.message}`);
  }
  return null;
}

// ===== MODULE: mcp =====
function moduleMcp(prompt) {
  const serversPaths = [
    path.join(HOME, 'OneDrive - TrendMicro', 'Documents', 'ProjectsCL', 'MCP', 'mcp-manager', 'servers.yaml'),
    path.join(HOME, 'mcp', 'mcp-manager', 'servers.yaml')
  ];
  
  const serversPath = serversPaths.find(p => fs.existsSync(p));
  if (!serversPath) {
    log('mcp', 'DEBUG', 'no servers.yaml found');
    return null;
  }
  
  try {
    const content = fs.readFileSync(serversPath, 'utf-8');
    const servers = parseServersYaml(content);
    const matched = [];
    
    for (const [name, server] of Object.entries(servers)) {
      if (!server.enabled) continue;
      const terms = [...(server.keywords || []), ...(server.tags || [])].map(t => t.toLowerCase());
      if (terms.some(t => prompt.includes(t))) {
        matched.push({ name, description: server.description || name });
      }
    }
    
    if (matched.length === 0) {
      log('mcp', 'DEBUG', 'no MCP servers matched');
      return null;
    }
    
    log('mcp', 'INFO', `suggested ${matched.length} MCPs: ${matched.map(s => s.name).join(', ')}`);
    const lines = ['--- MCP SERVER SUGGESTION ---', 'Relevant MCP servers for this task:'];
    for (const s of matched) lines.push(`- ${s.name}: ${s.description}`);
    lines.push('Use mcp__mcp-manager tools to start/call these.');
    lines.push('--- END MCP SUGGESTION ---');
    return lines.join('\n');
  } catch (e) {
    log('mcp', 'ERROR', `failed: ${e.message}`);
  }
  return null;
}

// Simple YAML parser for servers.yaml
function parseServersYaml(content) {
  const servers = {};
  let current = null, inKw = false, inTags = false;
  
  for (const line of content.split('\n')) {
    const trimmed = line.trim();
    const indent = line.length - line.trimStart().length;
    
    if (indent === 2 && trimmed.endsWith(':') && !trimmed.includes(' ')) {
      current = trimmed.slice(0, -1);
      servers[current] = { keywords: [], tags: [], enabled: false, description: '' };
      inKw = inTags = false;
      continue;
    }
    if (!current) continue;
    
    if (trimmed.startsWith('description:')) {
      servers[current].description = trimmed.split(':').slice(1).join(':').trim();
    } else if (trimmed.startsWith('enabled:')) {
      servers[current].enabled = trimmed.includes('true');
    } else if (trimmed === 'keywords:') { inKw = true; inTags = false; }
    else if (trimmed === 'tags:') { inTags = true; inKw = false; }
    else if (trimmed.startsWith('- ') && (inKw || inTags)) {
      const val = trimmed.slice(2).trim();
      if (inKw) servers[current].keywords.push(val);
      if (inTags) servers[current].tags.push(val);
    } else if (!trimmed.startsWith('-') && trimmed.includes(':')) {
      inKw = inTags = false;
    }
  }
  return servers;
}

// ===== MAIN =====
async function main() {
  let input = '';
  for await (const chunk of process.stdin) input += chunk;
  
  let hookData;
  try { hookData = JSON.parse(input); } catch (e) { process.exit(0); }
  
  const prompt = (hookData.prompt || '').toLowerCase();
  if (!prompt) process.exit(0);
  
  const outputs = [];
  
  // Run all 3 modules
  const claudemd = moduleClaudeMd();
  if (claudemd) outputs.push(claudemd);
  
  const skill = moduleSkill(prompt);
  if (skill) outputs.push(skill);
  
  const mcp = moduleMcp(prompt);
  if (mcp) outputs.push(mcp);
  
  if (outputs.length > 0) {
    console.log(outputs.join('\n'));
  }
  
  process.exit(0);
}

main().catch(() => process.exit(0));
