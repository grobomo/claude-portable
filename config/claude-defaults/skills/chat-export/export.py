#!/usr/bin/env python3
"""Export Claude Code conversation JSONL to terminal-styled HTML with expandable tool calls."""
import json
import html
import re
import sys
import base64
import os
from datetime import datetime
from pathlib import Path

import argparse
import subprocess

def parse_args():
    p = argparse.ArgumentParser(description='Export Claude Code conversation to HTML')
    p.add_argument('jsonl', nargs='?', help='Path to JSONL file (auto-detects current session if omitted)')
    p.add_argument('--name', help='Session name (auto-detects from first user message)')
    p.add_argument('--project', help='Project name (auto-detects from JSONL path)')
    p.add_argument('--branch', help='Git branch (auto-detects from git)')
    p.add_argument('--out', help='Output HTML path')
    p.add_argument('--screenshots', help='Directory of screenshots to embed as gallery')
    p.add_argument('--landing', action='store_true', help='Regenerate landing page only')
    p.add_argument('--all', action='store_true', help='Export all sessions for current project')
    p.add_argument('--stitch', action='store_true', help='Stitch all related sessions (same slug) into one export with compact dividers')
    p.add_argument('--project-path', help='Project working directory path')
    return p.parse_args()

def find_current_session():
    import os
    projects_dir = os.path.expanduser('~/.claude/projects')
    newest, newest_mtime = None, 0
    for root, dirs, files in os.walk(projects_dir):
        for f in files:
            if f.endswith('.jsonl'):
                fp = os.path.join(root, f)
                mt = os.path.getmtime(fp)
                if mt > newest_mtime:
                    newest_mtime, newest = mt, fp
    return newest

def find_project_sessions(project_slug=None):
    """Find all JSONL sessions for a project. If no slug given, use cwd-based slug."""
    projects_dir = os.path.expanduser('~/.claude/projects')
    if not project_slug:
        # Build slug from cwd the same way Claude Code does
        cwd = os.getcwd()
        # Normalize to forward slashes, replace colon and slashes with -
        slug = cwd.replace('\\', '-').replace('/', '-').replace(':', '-').replace(' ', '-')
        # Remove leading dash
        if slug.startswith('-'):
            slug = slug[1:]
        project_slug = slug
    # Find matching project directory
    target_dir = os.path.join(projects_dir, project_slug)
    sessions = []
    if os.path.isdir(target_dir):
        for f in os.listdir(target_dir):
            if f.endswith('.jsonl'):
                sessions.append(os.path.join(target_dir, f))
    if not sessions:
        # Try partial match
        for d in os.listdir(projects_dir):
            if project_slug.lower() in d.lower():
                dpath = os.path.join(projects_dir, d)
                if os.path.isdir(dpath):
                    for f in os.listdir(dpath):
                        if f.endswith('.jsonl'):
                            sessions.append(os.path.join(dpath, f))
    sessions.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return sessions

def find_related_sessions(jsonl_path):
    """Find all JSONL files with the same slug (conversation thread) and return sorted by start time."""
    parent_dir = os.path.dirname(jsonl_path)
    # Extract slug from target file
    target_slug = None
    with open(jsonl_path, encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get('slug'):
                    target_slug = obj['slug']
                    break
            except:
                continue
    if not target_slug:
        return [jsonl_path]

    # Find all JSONL files in same project dir with matching slug
    related = []
    for fname in os.listdir(parent_dir):
        if not fname.endswith('.jsonl'):
            continue
        fp = os.path.join(parent_dir, fname)
        found_slug = False
        first_ts = ''
        with open(fp, encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f):
                if i > 200:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if not first_ts and obj.get('timestamp'):
                        first_ts = obj['timestamp']
                    if obj.get('slug') == target_slug:
                        found_slug = True
                        break
                except:
                    continue
        if found_slug:
            related.append((fp, first_ts))

    # Sort by first timestamp (chronological order)
    related.sort(key=lambda x: x[1])
    return [fp for fp, _ in related] if related else [jsonl_path]


def detect_project_name(jsonl_path):
    import os
    parent = os.path.basename(os.path.dirname(jsonl_path))
    parts = parent.replace('--', '/').split('-')
    return parts[-1] if parts else 'unknown'

def detect_session_name(messages):
    import re
    for m in messages:
        if m['role'] == 'user' and m['texts']:
            text = m['texts'][0][:60].strip()
            return re.sub(r'[<>:"/\|?*]', '', text) or 'session'
    return 'session'

def detect_branch():
    import subprocess
    try:
        return subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                                        stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return 'main'

def detect_project_path():
    import os
    cwd = os.getcwd()
    home = os.path.expanduser('~')
    if cwd.startswith(home):
        return '~' + cwd[len(home):].replace(chr(92), '/')
    return cwd.replace(chr(92), '/')

EXPORTS_DIR = os.path.expanduser('~/Downloads/claude-exports')



def embed_image(path):
    try:
        p = Path(path)
        if not p.exists():
            return None
        ext = p.suffix.lower()
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext.lstrip("."), "image/png")
        data = base64.b64encode(p.read_bytes()).decode()
        return f"data:{mime};base64,{data}"
    except Exception:
        return None


def md_to_html(text):
    text = html.escape(text)
    def code_block(m):
        code = m.group(2)
        return f'<pre class="code-block"><code>{code}</code></pre>'
    text = re.sub(r'```(\w*)\n(.*?)```', code_block, text, flags=re.DOTALL)
    text = re.sub(r'`([^`]+)`', r'<code class="inline-code">\1</code>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'^#### (.+)$', r'<h4>\1</h4>', text, flags=re.MULTILINE)
    text = re.sub(r'^### (.+)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.+)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
    # Tables
    lines = text.split('\n')
    result = []
    in_table = False
    for line in lines:
        stripped = line.strip()
        if '|' in stripped and stripped.startswith('|') and stripped.endswith('|'):
            cells = [c.strip() for c in stripped.split('|')[1:-1]]
            if all(re.match(r'^[-:]+$', c) for c in cells):
                continue
            if not in_table:
                result.append('<table class="md-table">')
                in_table = True
                result.append('<tr>' + ''.join(f'<th>{c}</th>' for c in cells) + '</tr>')
            else:
                result.append('<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>')
        else:
            if in_table:
                result.append('</table>')
                in_table = False
            result.append(line)
    if in_table:
        result.append('</table>')
    text = '\n'.join(result)
    text = re.sub(r'^- (.+)$', r'<li>\1</li>', text, flags=re.MULTILINE)
    text = re.sub(r'(<li>.*?</li>\n?)+', lambda m: '<ul>' + m.group(0) + '</ul>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank">\1</a>', text)
    text = re.sub(r'\n\n+', '</p><p>', text)
    text = '<p>' + text + '</p>'
    text = text.replace('<p></p>', '')
    text = re.sub(r'<p>---</p>', '<hr>', text)
    return text


def tool_summary(tool):
    name = tool['name']
    inp = tool['input']
    if name == 'Write':
        return f"Write -> {inp.get('file_path', '?')}"
    elif name == 'Read':
        return f"Read -> {inp.get('file_path', '?')}"
    elif name == 'Edit':
        return f"Edit -> {inp.get('file_path', '?')}"
    elif name == 'Bash':
        cmd = inp.get('command', '')
        if len(cmd) > 80:
            cmd = cmd[:77] + '...'
        return f"$ {cmd}"
    elif name == 'Glob':
        return f"Glob -> {inp.get('pattern', '?')}"
    elif name == 'Grep':
        return f"Grep -> {inp.get('pattern', '?')}"
    elif name == 'WebSearch':
        return f"WebSearch: {inp.get('query', '?')}"
    elif name == 'WebFetch':
        return f"WebFetch: {inp.get('url', '?')[:60]}"
    elif name == 'Task':
        desc = inp.get('description', inp.get('prompt', '?'))[:60]
        return f"Task: {desc}"
    elif name == 'Skill':
        return f"Skill: {inp.get('skill', '?')}"
    elif 'mcp__' in name:
        server = name.split('__')[1] if '__' in name else '?'
        tool_name = name.split('__')[2] if name.count('__') >= 2 else '?'
        return f"MCP {server}/{tool_name}"
    else:
        return f"{name}()"


def tool_full_detail(tool):
    """Full detail text for the expanded view."""
    name = tool['name']
    inp = tool['input']
    parts = [f"Tool: {name}"]

    if name == 'Bash':
        parts.append(f"Command:\n{inp.get('command', '')}")
        if inp.get('description'):
            parts.append(f"Description: {inp['description']}")
    elif name in ('Read', 'Write', 'Edit', 'Glob', 'Grep'):
        for k, v in inp.items():
            if k == 'content' and len(str(v)) > 500:
                parts.append(f"{k}: ({len(str(v))} chars)")
            elif k == 'old_string' or k == 'new_string':
                val = str(v)
                if len(val) > 300:
                    val = val[:300] + '...'
                parts.append(f"{k}:\n{val}")
            else:
                parts.append(f"{k}: {v}")
    elif name == 'WebSearch':
        parts.append(f"Query: {inp.get('query', '')}")
    elif name == 'WebFetch':
        parts.append(f"URL: {inp.get('url', '')}")
        parts.append(f"Prompt: {inp.get('prompt', '')}")
    elif name == 'Task':
        parts.append(f"Description: {inp.get('description', '')}")
        prompt = inp.get('prompt', '')
        if len(prompt) > 500:
            prompt = prompt[:500] + '...'
        parts.append(f"Prompt: {prompt}")
        if inp.get('subagent_type'):
            parts.append(f"Agent: {inp['subagent_type']}")
    elif name == 'Skill':
        parts.append(f"Skill: {inp.get('skill', '')}")
        if inp.get('args'):
            parts.append(f"Args: {inp['args']}")
    elif 'mcp__' in name:
        for k, v in inp.items():
            val = json.dumps(v, indent=2) if isinstance(v, (dict, list)) else str(v)
            if len(val) > 300:
                val = val[:300] + '...'
            parts.append(f"{k}: {val}")
    else:
        for k, v in inp.items():
            val = str(v)
            if len(val) > 300:
                val = val[:300] + '...'
            parts.append(f"{k}: {val}")

    return '\n'.join(parts)


def parse_messages(jsonl_path, stitch_paths=None):
    """Parse JSONL into conversation turns, matching tool_uses to their results.
    If stitch_paths is provided, parse multiple JSONL files in order with boundary markers."""
    if stitch_paths and len(stitch_paths) > 1:
        all_messages = []
        for idx, sp in enumerate(stitch_paths):
            session_id = os.path.splitext(os.path.basename(sp))[0]
            if idx > 0:
                # Insert session boundary marker
                # Get first timestamp from this file
                first_ts = ''
                with open(sp, encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        try:
                            obj = json.loads(line.strip())
                            if obj.get('timestamp'):
                                first_ts = obj['timestamp']
                                break
                        except:
                            continue
                all_messages.append({
                    'role': 'boundary',
                    'boundary_type': 'session',
                    'timestamp': first_ts,
                    'session_id': session_id,
                    'label': f'New Session: {session_id[:8]}...',
                })
            msgs = parse_messages(sp)
            all_messages.extend(msgs)
        return all_messages

    messages = []
    # First pass: collect all tool results keyed by tool_use_id
    tool_results_map = {}  # tool_use_id -> result text
    tool_result_images = {}  # tool_use_id -> list of image data URIs

    all_records = []
    with open(jsonl_path, encoding='utf-8') as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            all_records.append(d)

    # Collect tool results from user messages
    for d in all_records:
        if d['type'] != 'user':
            continue
        msg = d.get('message', {})
        content = msg.get('content', [])
        if isinstance(content, str):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get('type') == 'tool_result':
                tuid = block.get('tool_use_id', '')
                result_content = block.get('content', '')
                result_text = ''
                images = []
                if isinstance(result_content, list):
                    for rc in result_content:
                        if isinstance(rc, dict) and rc.get('type') == 'text':
                            result_text += rc.get('text', '') + '\n'
                        elif isinstance(rc, dict) and rc.get('type') == 'image':
                            src = rc.get('source', {})
                            if src.get('type') == 'base64':
                                data_uri = f"data:{src.get('media_type','image/jpeg')};base64,{src.get('data','')}"
                                images.append(data_uri)
                elif isinstance(result_content, str):
                    result_text = result_content
                if tuid:
                    tool_results_map[tuid] = result_text.strip()
                    if images:
                        tool_result_images[tuid] = images

    # Build index of compact boundaries by UUID for ordering
    compact_boundaries = {}
    for d in all_records:
        if d.get('type') == 'system' and d.get('subtype') == 'compact_boundary':
            compact_boundaries[d.get('uuid', '')] = d

    # Second pass: build conversation turns
    for d in all_records:
        # Inject compact boundary markers
        if d.get('type') == 'system' and d.get('subtype') == 'compact_boundary':
            meta = d.get('compactMetadata', {})
            trigger = meta.get('trigger', 'auto')
            pre_tokens = meta.get('preTokens', 0)
            # Estimate context % (Claude's context is ~200k tokens)
            ctx_pct = round(pre_tokens / 200000 * 100) if pre_tokens else 0
            ts = d.get('timestamp', '')
            messages.append({
                'role': 'boundary',
                'boundary_type': 'compact',
                'timestamp': ts,
                'trigger': trigger,
                'context_pct': ctx_pct,
                'pre_tokens': pre_tokens,
                'label': f'{trigger.title()}-compact at {ctx_pct}% context used ({pre_tokens:,} tokens)',
            })
            continue

        if d['type'] not in ('user', 'assistant'):
            continue

        msg = d.get('message', {})
        role = msg.get('role', d['type'])
        content = msg.get('content', [])
        timestamp = d.get('timestamp', '')

        if isinstance(content, str):
            content = [{"type": "text", "text": content}]

        turn = {
            "role": role,
            "timestamp": timestamp,
            "texts": [],
            "tool_uses": [],
            "images": [],
            "hook_content": [],
        }

        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get('type', '')

            if btype == 'text':
                text = block.get('text', '')
                if '<system-reminder>' in text and role == 'user':
                    # Extract hook-injected content
                    hooks = re.findall(r'<system-reminder>(.*?)</system-reminder>', text, flags=re.DOTALL)
                    for h in hooks:
                        stripped = h.strip()
                        if stripped:
                            turn['hook_content'].append(stripped)
                    cleaned = re.sub(r'<system-reminder>.*?</system-reminder>', '', text, flags=re.DOTALL).strip()
                    if cleaned:
                        turn['texts'].append(cleaned)
                else:
                    if text.strip():
                        turn['texts'].append(text)

            elif btype == 'tool_use':
                tuid = block.get('id', '')
                tool_entry = {
                    "name": block.get('name', 'unknown'),
                    "input": block.get('input', {}),
                    "id": tuid,
                    "result": tool_results_map.get(tuid, ''),
                    "result_images": tool_result_images.get(tuid, []),
                }
                turn['tool_uses'].append(tool_entry)

            elif btype == 'image':
                src = block.get('source', {})
                if src.get('type') == 'base64':
                    data_uri = f"data:{src.get('media_type','image/jpeg')};base64,{src.get('data','')}"
                    turn['images'].append(data_uri)

        # Only include turns with visible content
        # For user turns: must have actual text (not just tool_results which are shown in assistant turns)
        # For assistant turns: must have text or tool_uses
        if role == 'user':
            if turn['texts'] or turn['images'] or turn['hook_content']:
                messages.append(turn)
        elif role == 'assistant':
            if turn['texts'] or turn['tool_uses'] or turn['images']:
                messages.append(turn)

    return messages


def generate_raw_text(messages):
    """Generate plain text version of conversation for raw export."""
    lines = []
    for turn in messages:
        if turn['role'] == 'boundary':
            label = turn.get('label', 'Context Boundary')
            lines.append('')
            lines.append('=' * 72)
            lines.append(f'  {label}')
            lines.append('=' * 72)
            lines.append('')
            continue

        role = 'You' if turn['role'] == 'user' else 'Claude'
        ts = turn.get('timestamp', '')
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                ts_display = dt.strftime('%Y-%m-%d %H:%M')
            except Exception:
                ts_display = ''
        else:
            ts_display = ''

        header = f"--- {role}"
        if ts_display:
            header += f" [{ts_display}]"
        header += " ---"
        lines.append(header)

        for text in turn['texts']:
            lines.append(text)

        for tool in turn.get('tool_uses', []):
            name = tool['name']
            inp = tool['input']
            lines.append(f"\n[Tool: {name}]")
            if name == 'Bash':
                lines.append(f"Command: {inp.get('command', '')}")
                if inp.get('description'):
                    lines.append(f"Description: {inp['description']}")
            elif name in ('Read', 'Write', 'Edit', 'Glob', 'Grep'):
                for k, v in inp.items():
                    val = str(v)
                    if len(val) > 3000:
                        val = val[:3000] + f'... ({len(str(v))} chars)'
                    lines.append(f"{k}: {val}")
            elif name == 'WebSearch':
                lines.append(f"Query: {inp.get('query', '')}")
            elif name == 'WebFetch':
                lines.append(f"URL: {inp.get('url', '')}")
                lines.append(f"Prompt: {inp.get('prompt', '')}")
            elif name == 'Task':
                lines.append(f"Description: {inp.get('description', '')}")
                lines.append(f"Prompt: {inp.get('prompt', '')}")
                if inp.get('subagent_type'):
                    lines.append(f"Agent: {inp['subagent_type']}")
            elif name == 'Skill':
                lines.append(f"Skill: {inp.get('skill', '')}")
                if inp.get('args'):
                    lines.append(f"Args: {inp['args']}")
            else:
                for k, v in inp.items():
                    val = json.dumps(v, indent=2) if isinstance(v, (dict, list)) else str(v)
                    if len(val) > 3000:
                        val = val[:3000] + '...'
                    lines.append(f"{k}: {val}")

            if tool.get('result'):
                result = tool['result']
                if len(result) > 5000:
                    result = result[:5000] + f'\n... ({len(tool["result"])} chars total)'
                lines.append(f"\n[Output]")
                lines.append(result)

        lines.append('')
    return '\n'.join(lines)


def generate_html(messages, out_path, session_name="Session", project_name="project", branch="main", project_path="~/project", screenshot_dir=None, session_id="", working_dir=""):
    screenshots = {}
    if screenshot_dir and os.path.isdir(screenshot_dir):
        for f in sorted(os.listdir(screenshot_dir)):
            if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                uri = embed_image(os.path.join(screenshot_dir, f))
                if uri:
                    screenshots[f] = uri

    html_parts = []
    html_parts.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Claude Code Export - {session_name}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #0C0C0C;
    color: #CCCCCC;
    font-family: 'Cascadia Code', 'Cascadia Mono', 'Consolas', 'Courier New', monospace;
    font-size: 17px;
    line-height: 1.5;
    padding: 0;
  }}
  .header-wrapper {{
    position: sticky;
    top: 0;
    z-index: 100;
  }}
  .terminal-chrome {{
    background: #1F1F1F;
    padding: 6px 16px;
    display: flex;
    align-items: center;
  }}
  .terminal-logo {{
    display: flex;
    align-items: center;
    flex-shrink: 0;
  }}
  .terminal-title {{
    flex: 1;
    text-align: center;
    color: #CCCCCC;
    font-size: 15px;
    letter-spacing: 0.3px;
  }}
  .terminal-title .session-name {{ color: #6A9FB5; }}
  .terminal-actions {{
    flex-shrink: 0;
  }}
  .export-btn {{
    background: #2D2D2D;
    border: 1px solid #555;
    color: #CCCCCC;
    font-family: 'Cascadia Code', 'Consolas', monospace;
    font-size: 13px;
    padding: 3px 10px;
    border-radius: 3px;
    cursor: pointer;
  }}
  .export-btn:hover {{
    background: #3D3D3D;
    color: #FFFFFF;
  }}
  .toolbar-btn {{
    background: #2D2D2D;
    border: 1px solid #555;
    color: #CCCCCC;
    font-family: 'Cascadia Code', 'Consolas', monospace;
    font-size: 13px;
    padding: 3px 10px;
    border-radius: 3px;
    cursor: pointer;
    margin-left: 6px;
  }}
  .toolbar-btn:hover {{
    background: #3D3D3D;
    color: #FFFFFF;
  }}
  .toolbar-btn.active {{
    background: #3D3D3D;
    border-color: #6A9FB5;
    color: #6A9FB5;
  }}
  #backToTop {{
    display: none;
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: #2D2D2D;
    border: 1px solid #555;
    color: #CCCCCC;
    font-family: 'Cascadia Code', 'Consolas', monospace;
    font-size: 13px;
    padding: 8px 14px;
    border-radius: 6px;
    cursor: pointer;
    z-index: 150;
    text-align: center;
  }}
  #backToTop:hover {{
    background: #3D3D3D;
    color: #FFFFFF;
    border-color: #6A9FB5;
  }}
  .turn-count {{
    color: #666;
    font-size: 13px;
    margin-left: 12px;
  }}
  .boundary-divider {{
    width: 100%;
    min-height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: 24px 0;
    position: relative;
  }}
  .boundary-divider.compact {{
    background: linear-gradient(180deg, #0a1628 0%, #122040 30%, #122040 70%, #0a1628 100%);
    border-top: 2px solid #2563eb;
    border-bottom: 2px solid #2563eb;
  }}
  .boundary-divider.session {{
    background: linear-gradient(180deg, #0a2818 0%, #0d3520 30%, #0d3520 70%, #0a2818 100%);
    border-top: 2px solid #22c55e;
    border-bottom: 2px solid #22c55e;
  }}
  .boundary-label {{
    font-family: 'Cascadia Code', 'Consolas', monospace;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    padding: 4px 20px;
  }}
  .boundary-divider.compact .boundary-label {{
    color: #60a5fa;
  }}
  .boundary-divider.session .boundary-label {{
    color: #4ade80;
  }}
  .boundary-timestamp {{
    font-size: 11px;
    color: #6b7280;
    margin-left: 12px;
  }}
  .terminal-body {{
    padding: 12px 6%;
    width: 100%;
    max-width: 100%;
    margin: 0 auto;
  }}
  .session-header {{
    color: #6A9FB5;
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid #333;
  }}
  .session-header .path {{ color: #8BC34A; }}
  .msg {{
    margin-bottom: 16px;
    padding: 8px 0;
  }}
  .msg-header {{
    margin-bottom: 4px;
    font-size: 16px;
  }}
  .user .msg-header {{ color: #CCCCCC; }}
  .user .msg-header .role {{ color: #6A9FB5; font-weight: bold; }}
  .user .msg-header .prompt-char {{ color: #8BC34A; font-weight: bold; }}
  .user .msg-body {{ color: #FFFFFF; padding-left: 20px; }}
  .assistant .msg-header .role {{ color: #D4A0FF; font-weight: bold; }}
  .assistant .msg-body {{ color: #CCCCCC; padding-left: 20px; }}

  /* Hook-injected content (system-reminders from hooks) */
  details.hook-content {{
    background: #0d1926;
    border-left: 3px solid #1f6feb;
    margin: 6px 0 6px 20px;
    border-radius: 0 4px 4px 0;
  }}
  details.hook-content summary {{
    padding: 4px 12px;
    font-size: 14px;
    color: #58a6ff;
    cursor: pointer;
    list-style: none;
    user-select: none;
  }}
  details.hook-content summary::-webkit-details-marker {{ display: none; }}
  details.hook-content summary::before {{
    content: '[H]';
    color: #1f6feb;
    margin-right: 6px;
    font-weight: bold;
  }}
  details.hook-content summary:hover {{
    color: #79c0ff;
    background: #0d1926;
  }}
  details.hook-content[open] summary {{
    color: #79c0ff;
    background: #0d1926;
    border-bottom: 1px solid #1c3a5e;
  }}
  details.hook-content[open] summary::before {{
    content: '[-]';
  }}
  .hook-detail {{
    padding: 8px 12px;
    font-size: 13px;
    color: #8b949e;
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 300px;
    overflow-y: auto;
  }}

  /* Expandable tool use - details/summary */
  details.tool-use {{
    background: #1A1A2E;
    border-left: 3px solid #4A4A8A;
    margin: 6px 0 6px 20px;
    border-radius: 0 4px 4px 0;
  }}
  details.tool-use summary {{
    padding: 4px 12px;
    font-size: 16px;
    color: #888;
    cursor: pointer;
    list-style: none;
    user-select: none;
  }}
  details.tool-use summary::-webkit-details-marker {{ display: none; }}
  details.tool-use summary::before {{
    content: '[*]';
    color: #6A6ACA;
    margin-right: 6px;
    font-weight: bold;
  }}
  details.tool-use summary:hover {{
    color: #BBB;
    background: #1E1E3A;
  }}
  details.tool-use[open] summary {{
    color: #AAA;
    background: #1E1E3A;
    border-bottom: 1px solid #333;
  }}
  details.tool-use[open] summary::before {{
    content: '[-]';
  }}
  .tool-detail {{
    padding: 8px 12px;
    font-size: 15px;
    max-height: 400px;
    overflow-y: auto;
  }}
  .tool-detail .tool-input {{
    color: #9CDCFE;
    white-space: pre-wrap;
    word-break: break-all;
  }}
  .tool-detail .tool-output {{
    margin-top: 6px;
    padding-top: 6px;
    border-top: 1px solid #2A2A4A;
  }}
  .tool-detail .tool-output-label {{
    color: #6A6ACA;
    font-size: 14px;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 3px;
  }}
  .tool-detail .tool-output-content {{
    color: #8BC34A;
    white-space: pre-wrap;
    word-break: break-all;
  }}
  .tool-detail .tool-output-content.error {{
    color: #F44747;
  }}
  .tool-detail .tool-result-img {{
    max-width: 100%;
    max-height: 300px;
    border: 1px solid #444;
    border-radius: 4px;
    margin-top: 6px;
  }}

  .inline-code {{
    background: #1E1E1E;
    color: #CE9178;
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 16px;
  }}
  .code-block {{
    background: #1E1E1E;
    border: 1px solid #333;
    border-radius: 4px;
    padding: 10px 14px;
    margin: 8px 0;
    overflow-x: auto;
    font-size: 16px;
    line-height: 1.4;
  }}
  .code-block code {{ color: #D4D4D4; }}
  .md-table {{
    border-collapse: collapse;
    margin: 8px 0;
    font-size: 16px;
    width: 100%;
  }}
  .md-table th, .md-table td {{
    border: 1px solid #444;
    padding: 4px 10px;
    text-align: left;
  }}
  .md-table th {{ background: #1E1E2E; color: #9CDCFE; }}
  .md-table td {{ background: #141414; }}
  .msg-body h1, .msg-body h2, .msg-body h3, .msg-body h4 {{
    color: #569CD6;
    margin: 10px 0 4px 0;
  }}
  .msg-body h1 {{ font-size: 19px; }}
  .msg-body h2 {{ font-size: 17px; }}
  .msg-body h3 {{ font-size: 16px; }}
  .msg-body h4 {{ font-size: 16px; color: #9CDCFE; }}
  strong {{ color: #DCDCAA; }}
  a {{ color: #6A9FB5; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  hr {{ border: none; border-top: 1px solid #333; margin: 12px 0; }}
  ul {{ padding-left: 20px; margin: 4px 0; }}
  li {{ margin: 2px 0; }}
  .screenshot {{
    max-width: min(800px, 100%);
    width: auto;
    border: 1px solid #444;
    border-radius: 4px;
    margin: 8px 0;
  }}
  .timestamp {{ color: #555; font-size: 15px; float: right; }}
  .gallery {{
    margin-top: 32px;
    padding-top: 16px;
    border-top: 2px solid #333;
  }}
  .gallery h2 {{ color: #569CD6; margin-bottom: 12px; }}
  .gallery-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
    gap: 12px;
  }}
  .gallery-item {{
    background: #141414;
    border: 1px solid #333;
    border-radius: 6px;
    padding: 8px;
  }}
  .gallery-item img {{ width: 100%; border-radius: 4px; }}
  .gallery-item .caption {{
    color: #888;
    font-size: 15px;
    margin-top: 4px;
    text-align: center;
  }}
  ::-webkit-scrollbar {{ width: 10px; }}
  ::-webkit-scrollbar-track {{ background: #1E1E1E; }}
  ::-webkit-scrollbar-thumb {{ background: #444; border-radius: 4px; }}
  ::-webkit-scrollbar-thumb:hover {{ background: #555; }}

  /* Toolbar row: project path + search */
  .toolbar-row {{
    background: #181818;
    border-bottom: 1px solid #333;
    padding: 4px 16px;
    display: flex;
    align-items: center;
    position: relative;
  }}
  .toolbar-row .path {{ color: #8BC34A; font-size: 14px; white-space: nowrap; cursor: pointer; }}
  .toolbar-row .path:hover {{ text-decoration: underline; }}
  .toolbar-row .branch {{ color: #666; font-size: 14px; }}
  .back-link {{ color: #6A9FB5; font-size: 13px; text-decoration: none; margin-right: 12px; white-space: nowrap; }}
  .back-link:hover {{ color: #8BC0D6; text-decoration: underline; }}
  .toolbar-right {{ display: flex; align-items: center; margin-left: auto; gap: 2px; }}
  .search-group {{
    display: flex;
    align-items: center;
    gap: 6px;
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
  }}
  .search-group input {{
    background: #2D2D2D;
    border: 1px solid #555;
    color: #CCCCCC;
    font-family: 'Cascadia Code', 'Consolas', monospace;
    font-size: 14px;
    padding: 3px 10px;
    border-radius: 3px;
    width: 260px;
    outline: none;
  }}
  .search-group input:focus {{
    border-color: #007ACC;
  }}
  .search-group button {{
    background: #2D2D2D;
    border: 1px solid #555;
    color: #CCCCCC;
    font-family: 'Cascadia Code', 'Consolas', monospace;
    font-size: 13px;
    padding: 3px 10px;
    border-radius: 3px;
    cursor: pointer;
  }}
  .search-group button:hover {{
    background: #3D3D3D;
  }}
  .search-group .hit-count {{
    color: #888;
    font-size: 13px;
    margin-left: 8px;
  }}

  /* When search results panel is open, split the page */
  body.search-open .terminal-body {{
    height: calc(100vh - 40px - 30px - 200px);
    overflow-y: auto;
  }}
  body.search-open .search-results-panel {{
    display: block;
  }}

  /* Search results panel - NPP style */
  .search-results-panel {{
    display: none;
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    height: 200px;
    background: #1E1E1E;
    border-top: 2px solid #555;
    z-index: 200;
    font-family: 'Cascadia Code', 'Consolas', monospace;
    font-size: 14px;
  }}
  .search-results-header {{
    background: #2D2D30;
    border-bottom: 1px solid #444;
    padding: 3px 10px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    color: #CCCCCC;
    font-size: 13px;
    user-select: none;
  }}
  .search-results-header .close-btn {{
    cursor: pointer;
    color: #CCCCCC;
    font-size: 16px;
    padding: 0 4px;
    line-height: 1;
  }}
  .search-results-header .close-btn:hover {{
    color: #FF5F57;
  }}
  .search-results-info {{
    background: #1A1A2E;
    padding: 2px 10px;
    color: #6A9FB5;
    font-size: 12px;
    border-bottom: 1px solid #333;
  }}
  .search-results-list {{
    overflow-y: auto;
    height: calc(100% - 48px);
  }}
  .search-result-item {{
    padding: 1px 10px 1px 40px;
    color: #CCCCCC;
    cursor: pointer;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .search-result-item:hover {{
    background: #2A2D2E;
  }}
  /* NPP selected result: dull yellow background */
  .search-result-item.selected {{
    background: #6B6B2E;
  }}
  .search-result-item .line-ref {{
    color: #569CD6;
    margin-right: 12px;
    display: inline-block;
    min-width: 80px;
  }}

  /* Highlight matches in conversation content - NPP style dull yellow */
  .search-highlight {{
    background: #6B6B2E;
    color: #FFFFFF;
    border-radius: 2px;
    padding: 0 1px;
  }}
  /* Active/clicked highlight - brighter */
  .search-highlight-active {{
    background: #8B8B00;
    color: #FFFFFF;
    outline: 1px solid #AAAA00;
    border-radius: 2px;
    padding: 0 1px;
  }}

  /* Resize handle for search panel */
  .search-resize-handle {{
    position: absolute;
    top: -3px;
    left: 0;
    right: 0;
    height: 6px;
    cursor: ns-resize;
    z-index: 201;
  }}
  .resume-copy {{ background: #238636; border-color: #2ea043; }}
  .resume-copy:hover {{ background: #2ea043; color: #fff; }}
  .resume-launch {{ background: #1f6feb; border-color: #388bfd; }}
  .resume-launch:hover {{ background: #388bfd; color: #fff; }}
  .gen-link {{ color: #58a6ff; text-decoration: none; cursor: pointer; }}
  .gen-link:hover {{ text-decoration: underline; }}
  .spinner-overlay {{
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(12, 12, 12, 0.92); z-index: 500;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    opacity: 0; transition: opacity 0.3s; pointer-events: none;
  }}
  .spinner-overlay.active {{ opacity: 1; pointer-events: auto; }}
  .comet-ring {{
    width: 64px; height: 64px; border-radius: 50%;
    background: conic-gradient(from 0deg, #333 0%, #555 25%, #999 50%, #ccc 75%, #fff 95%, #333 100%);
    -webkit-mask: radial-gradient(circle, transparent 55%, black 58%);
    mask: radial-gradient(circle, transparent 55%, black 58%);
    animation: comet-spin 1.2s linear infinite;
  }}
  @keyframes comet-spin {{
    to {{ transform: rotate(-360deg); }}
  }}
  .spinner-text {{
    color: #888; font-size: 13px; margin-top: 16px;
  }}
  .spinner-cmd {{
    color: #58a6ff; font-size: 11px; margin-top: 8px; cursor: pointer;
    background: #1a1a2e; padding: 6px 12px; border-radius: 4px;
    border: 1px solid #333;
  }}
  .spinner-cmd:hover {{ border-color: #58a6ff; }}
  .toast {{
    position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%);
    background: #238636; color: #fff; padding: 10px 24px; border-radius: 6px;
    font-size: 14px; opacity: 0; transition: opacity 0.3s; z-index: 9999;
    pointer-events: none;
  }}
  .toast.show {{ opacity: 1; }}
</style>
</head>
<body>
<div class="header-wrapper">
<div class="terminal-chrome">
  <div class="terminal-logo">
    <img src="data:image/png;base64,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" alt="Scarab Logo" style="height: 32px; width: auto; image-rendering: auto;" />
  </div>
  <div class="terminal-title">Claude Code Export: <span class="session-name">{session_name} - {datetime.now().strftime('%Y-%m-%d')}</span></div>
  <div class="terminal-actions">
    <button class="export-btn" onclick="exportRawTxt()" title="Export as plain text for importing to a new Claude session">Export Raw TXT</button>
  </div>
</div>
<div class="toolbar-row">
  <a href="../index.html" class="back-link" title="Back to all sessions">&lt; All Sessions</a>
  <span class="path" onclick="openProjectDir()" title="Open in Explorer">{project_path}</span>&nbsp;<span class="branch">({branch})</span>
  <div class="toolbar-right">
    {'<button class="toolbar-btn resume-copy" onclick="copyResume()" title="Copy resume command to clipboard">Resume: Copy</button><button class="toolbar-btn resume-launch" onclick="launchResume()" title="Copy terminal-launch command">Resume: Launch</button>' if session_id else ''}
    <button class="toolbar-btn" onclick="scrollToBottom()" title="Jump to end of conversation">Bottom</button>
    <button class="toolbar-btn" id="expandCollapseBtn" onclick="toggleAllToolCalls()" title="Expand or collapse all tool call details">Expand All</button>
    <span class="turn-count">{len(messages)} turns</span>
  </div>
  <div class="search-group">
    <input type="text" id="searchInput" placeholder="Search conversation..." />
    <button onclick="doSearch()">Find All</button>
    <span class="hit-count" id="hitCount"></span>
  </div>
</div>
</div>
<div class="terminal-body" id="terminalBody">
""")

    for turn in messages:
        role = turn['role']

        # Render boundary dividers (compact or session breaks)
        if role == 'boundary':
            btype = turn.get('boundary_type', 'compact')
            label = html.escape(turn.get('label', 'Context Boundary'))
            ts = turn.get('timestamp', '')
            ts_display = ''
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    ts_display = dt.strftime('%Y-%m-%d %H:%M UTC')
                except Exception:
                    pass
            html_parts.append(f'<div class="boundary-divider {btype}">')
            html_parts.append(f'  <span class="boundary-label">{label}</span>')
            if ts_display:
                html_parts.append(f'  <span class="boundary-timestamp">{ts_display}</span>')
            html_parts.append('</div>')
            continue

        ts = turn.get('timestamp', '')
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                ts_display = dt.strftime('%H:%M')
            except Exception:
                ts_display = ''
        else:
            ts_display = ''

        html_parts.append(f'<div class="msg {role}">')

        if role == 'user':
            html_parts.append('  <div class="msg-header">')
            if ts_display:
                html_parts.append(f'    <span class="timestamp">{ts_display}</span>')
            html_parts.append('    <span class="prompt-char">&gt;</span> <span class="role">You</span>')
            html_parts.append('  </div>')
            html_parts.append('  <div class="msg-body">')
            for text in turn['texts']:
                html_parts.append(f'    {md_to_html(text)}')
            for img_uri in turn['images']:
                html_parts.append(f'    <img class="screenshot" src="{img_uri}" />')
            html_parts.append('  </div>')

            # Hook-injected content (collapsible, blue-bordered)
            for hc in turn.get('hook_content', []):
                # Extract a short label from first line
                first_line = hc.split('\n')[0][:80].strip()
                if first_line.startswith('#'):
                    first_line = first_line.lstrip('# ')
                label = html.escape(first_line) if first_line else 'Hook injection'
                html_parts.append(f'  <details class="hook-content">')
                html_parts.append(f'    <summary>Hook: {label}</summary>')
                html_parts.append(f'    <div class="hook-detail">{html.escape(hc)}</div>')
                html_parts.append(f'  </details>')

        elif role == 'assistant':
            html_parts.append('  <div class="msg-header">')
            if ts_display:
                html_parts.append(f'    <span class="timestamp">{ts_display}</span>')
            html_parts.append('    <span class="role">Claude</span>')
            html_parts.append('  </div>')

            # Expandable tool uses
            for tool in turn['tool_uses']:
                summary_text = html.escape(tool_summary(tool))
                detail_text = html.escape(tool_full_detail(tool))
                result_text = tool.get('result', '')
                result_images = tool.get('result_images', [])

                html_parts.append(f'  <details class="tool-use">')
                html_parts.append(f'    <summary>{summary_text}</summary>')
                html_parts.append(f'    <div class="tool-detail">')
                html_parts.append(f'      <div class="tool-input">{detail_text}</div>')

                if result_text or result_images:
                    html_parts.append(f'      <div class="tool-output">')
                    html_parts.append(f'        <div class="tool-output-label">Output</div>')
                    if result_text:
                        # Truncate very long outputs
                        display_result = result_text
                        if len(display_result) > 2000:
                            display_result = display_result[:2000] + f'\n... ({len(result_text)} chars total)'
                        err_class = ' error' if any(w in display_result.lower() for w in ['error', 'traceback', 'exception', 'failed']) else ''
                        html_parts.append(f'        <div class="tool-output-content{err_class}">{html.escape(display_result)}</div>')
                    for img_uri in result_images:
                        html_parts.append(f'        <img class="tool-result-img" src="{img_uri}" />')
                    html_parts.append(f'      </div>')

                html_parts.append(f'    </div>')
                html_parts.append(f'  </details>')

            # Text content
            html_parts.append('  <div class="msg-body">')
            for text in turn['texts']:
                html_parts.append(f'    {md_to_html(text)}')
            for img_uri in turn['images']:
                html_parts.append(f'    <img class="screenshot" src="{img_uri}" />')
            html_parts.append('  </div>')

        html_parts.append('</div>')

    # Screenshot gallery
    if screenshots:
        html_parts.append('<div class="gallery">')
        html_parts.append('<h2>{project_name} Screenshots</h2>')
        html_parts.append('<div class="gallery-grid">')
        for name, uri in screenshots.items():
            caption = name.replace('.png', '').replace('.jpg', '').replace('-', ' ')
            html_parts.append(f'<div class="gallery-item">')
            html_parts.append(f'  <img src="{uri}" />')
            html_parts.append(f'  <div class="caption">{html.escape(caption)}</div>')
            html_parts.append(f'</div>')
        html_parts.append('</div></div>')

    # Generate raw text for export
    raw_text = generate_raw_text(messages)
    raw_text_js = json.dumps(raw_text).replace('</script>', r'<\/script>')

    html_parts.append("""
</div>

<!-- Search Results Panel (NPP style) -->
<div class="search-results-panel" id="searchPanel">
  <div class="search-resize-handle" id="resizeHandle"></div>
  <div class="search-results-header">
    <span id="searchResultsTitle">Search results - (0 hits)</span>
    <span class="close-btn" onclick="closeSearch()">&times;</span>
  </div>
  <div class="search-results-info" id="searchResultsInfo"></div>
  <div class="search-results-list" id="searchResultsList"></div>
</div>

<script>
let currentHighlights = [];
let originalContents = new Map();

function doSearch() {
  const query = document.getElementById('searchInput').value.trim();
  if (!query) return;

  // Clear previous search
  clearHighlights();

  const body = document.body;
  const panel = document.getElementById('searchPanel');
  const list = document.getElementById('searchResultsList');
  const title = document.getElementById('searchResultsTitle');
  const info = document.getElementById('searchResultsInfo');
  const hitCount = document.getElementById('hitCount');

  // Find all text nodes in the conversation that match
  const terminalBody = document.getElementById('terminalBody');
  const results = [];
  let totalHits = 0;

  // Walk through all .msg elements
  const messages = terminalBody.querySelectorAll('.msg');
  messages.forEach((msg, msgIdx) => {
    // Search in msg-body, tool-use summaries, and tool-detail
    const searchTargets = msg.querySelectorAll('.msg-body, details.tool-use summary, .tool-input, .tool-output-content');
    searchTargets.forEach(target => {
      const text = target.textContent;
      const regex = new RegExp(escapeRegex(query), 'gi');
      let match;
      while ((match = regex.exec(text)) !== null) {
        totalHits++;
        // Get context: surrounding text
        const start = Math.max(0, match.index - 40);
        const end = Math.min(text.length, match.index + query.length + 60);
        let context = text.substring(start, end).replace(/\\n/g, ' ').trim();
        if (start > 0) context = '...' + context;
        if (end < text.length) context = context + '...';

        // Determine role
        const role = msg.classList.contains('user') ? 'You' : 'Claude';

        results.push({
          msgIdx: msgIdx,
          element: msg,
          target: target,
          matchIndex: match.index,
          matchLen: query.length,
          context: context,
          role: role,
          hitNum: totalHits
        });
      }
    });
  });

  // Highlight all matches in the DOM
  highlightMatches(query);

  // Update panel
  title.textContent = 'Search results - (' + totalHits + ' hits)';
  info.textContent = 'Search "' + query + '" (' + totalHits + ' hits in conversation)';
  hitCount.textContent = totalHits + ' hits';

  // Build result list
  list.innerHTML = '';
  results.forEach((r, idx) => {
    const item = document.createElement('div');
    item.className = 'search-result-item';
    item.setAttribute('data-idx', idx);

    const lineRef = document.createElement('span');
    lineRef.className = 'line-ref';
    lineRef.textContent = r.role + ' #' + (r.msgIdx + 1) + ':';

    const contextSpan = document.createElement('span');
    // Highlight the match in the context
    const esc = escapeHtml(r.context);
    const qEsc = escapeHtml(query);
    const re = new RegExp('(' + escapeRegex(qEsc) + ')', 'gi');
    contextSpan.innerHTML = esc.replace(re, '<span style="color:#AAAA00;font-weight:bold;">$1</span>');

    item.appendChild(lineRef);
    item.appendChild(contextSpan);

    item.addEventListener('click', function() {
      // Remove selected from all
      list.querySelectorAll('.search-result-item.selected').forEach(el => el.classList.remove('selected'));
      item.classList.add('selected');

      // Remove active highlight from previous
      document.querySelectorAll('.search-highlight-active').forEach(el => {
        el.className = 'search-highlight';
      });

      // Scroll to the message
      r.element.scrollIntoView({ behavior: 'smooth', block: 'center' });

      // Find and activate the specific highlight
      const highlights = r.element.querySelectorAll('.search-highlight');
      // Count which match this is within the element
      let matchCount = 0;
      for (let i = 0; i < results.length; i++) {
        if (results[i].element === r.element && i < idx) matchCount++;
      }
      // Activate the nth highlight in this message
      let hlCount = 0;
      highlights.forEach(hl => {
        // Find highlights in the same target
        if (r.target.contains(hl)) {
          if (hlCount === (r.hitNum - countPriorHitsInTarget(results, idx))) {
            hl.className = 'search-highlight-active';
          }
          hlCount++;
        }
      });

      // Simpler approach: just activate based on global order
      const allHighlights = terminalBody.querySelectorAll('.search-highlight, .search-highlight-active');
      allHighlights.forEach(hl => hl.className = 'search-highlight');
      if (allHighlights[idx]) {
        allHighlights[idx].className = 'search-highlight-active';
        // Ensure it's visible
        setTimeout(() => allHighlights[idx].scrollIntoView({ behavior: 'smooth', block: 'center' }), 100);
      }
    });

    list.appendChild(item);
  });

  // Open panel
  body.classList.add('search-open');
  panel.style.display = 'block';
}

function countPriorHitsInTarget(results, idx) {
  let count = 0;
  for (let i = 0; i < idx; i++) {
    if (results[i].target === results[idx].target) count++;
  }
  return count;
}

function highlightMatches(query) {
  const terminalBody = document.getElementById('terminalBody');
  const targets = terminalBody.querySelectorAll('.msg-body p, .msg-body li, .msg-body h1, .msg-body h2, .msg-body h3, .msg-body h4, .msg-body td, .msg-body th, .msg-body strong, details.tool-use summary, .tool-input, .tool-output-content');

  targets.forEach(target => {
    // Skip elements that contain other targets (avoid double-processing)
    if (target.querySelector('.search-highlight')) return;

    const walker = document.createTreeWalker(target, NodeFilter.SHOW_TEXT, null, false);
    const textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);

    textNodes.forEach(node => {
      const text = node.textContent;
      const regex = new RegExp('(' + escapeRegex(query) + ')', 'gi');
      if (!regex.test(text)) return;

      const frag = document.createDocumentFragment();
      let lastIdx = 0;
      regex.lastIndex = 0;
      let m;
      while ((m = regex.exec(text)) !== null) {
        // Text before match
        if (m.index > lastIdx) {
          frag.appendChild(document.createTextNode(text.substring(lastIdx, m.index)));
        }
        // Highlighted match
        const span = document.createElement('span');
        span.className = 'search-highlight';
        span.textContent = m[1];
        frag.appendChild(span);
        currentHighlights.push(span);
        lastIdx = m.index + m[0].length;
      }
      // Remaining text
      if (lastIdx < text.length) {
        frag.appendChild(document.createTextNode(text.substring(lastIdx)));
      }
      node.parentNode.replaceChild(frag, node);
    });
  });
}

function clearHighlights() {
  // Remove all highlight spans and restore text
  document.querySelectorAll('.search-highlight, .search-highlight-active').forEach(span => {
    const parent = span.parentNode;
    parent.replaceChild(document.createTextNode(span.textContent), span);
    parent.normalize();
  });
  currentHighlights = [];
}

function closeSearch() {
  clearHighlights();
  document.body.classList.remove('search-open');
  document.getElementById('searchPanel').style.display = 'none';
  document.getElementById('searchResultsList').innerHTML = '';
  document.getElementById('hitCount').textContent = '';
}

function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&');
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

// Search on Enter key
document.getElementById('searchInput').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') doSearch();
  if (e.key === 'Escape') closeSearch();
});

// Resize handle for search panel
(function() {
  const handle = document.getElementById('resizeHandle');
  const panel = document.getElementById('searchPanel');
  let startY, startH;
  handle.addEventListener('mousedown', function(e) {
    startY = e.clientY;
    startH = panel.offsetHeight;
    document.addEventListener('mousemove', onDrag);
    document.addEventListener('mouseup', onStop);
    e.preventDefault();
  });
  function onDrag(e) {
    const newH = startH + (startY - e.clientY);
    if (newH > 80 && newH < window.innerHeight - 200) {
      panel.style.height = newH + 'px';
      // Recalc conversation area
      document.getElementById('terminalBody').style.height =
        'calc(100vh - 40px - 30px - ' + newH + 'px)';
    }
  }
  function onStop() {
    document.removeEventListener('mousemove', onDrag);
    document.removeEventListener('mouseup', onStop);
  }
})();
</script>

<script>
const RAW_TEXT = """ + raw_text_js + """;
function openProjectDir() {
  const winPath = '/home/claude/OneDrive - TrendMicro\\\\Documents\\\\ProjectsCL\\\\moltbot';
  const fileUrl = 'file:///' + winPath.replace(/\\\\/g, '/').replace(/ /g, '%20');
  window.open(fileUrl, '_blank');
}
function exportRawTxt() {
  const blob = new Blob([RAW_TEXT], {type: 'text/plain;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = document.title.replace(/[^a-zA-Z0-9]/g, '-') + '.txt';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(a.href);
}
var RESUME_SID = '""" + session_id + """';
var RESUME_DIR = '""" + working_dir.replace("'", "\\'") + """';
function showToast(msg) {
  var t = document.getElementById('toast');
  if (!t) { t = document.createElement('div'); t.id = 'toast'; t.className = 'toast'; document.body.appendChild(t); }
  t.textContent = msg; t.className = 'toast show';
  setTimeout(function() { t.className = 'toast'; }, 2000);
}
function copyResume() {
  if (!RESUME_SID) { showToast('No session ID available'); return; }
  var cmd = 'cd "' + RESUME_DIR + '" && claude -r ' + RESUME_SID;
  navigator.clipboard.writeText(cmd).then(function() { showToast('Copied: ' + cmd); });
}
function launchResume() {
  if (!RESUME_SID) { showToast('No session ID available'); return; }
  var isWin = navigator.platform.indexOf('Win') > -1;
  var cmd;
  if (isWin) {
    var winDir = RESUME_DIR.replace(/[/]/g, '\\');
    cmd = 'cmd /k cd /d "' + winDir + '" && claude -r ' + RESUME_SID;
  } else {
    cmd = 'cd "' + RESUME_DIR + '" && claude -r ' + RESUME_SID;
  }
  navigator.clipboard.writeText(cmd).then(function() {
    if (isWin) {
      showToast('Copied -- press Win+R, paste, Enter');
    } else {
      showToast('Copied -- paste in Terminal, Enter');
    }
  });
}
</script>


<button id="backToTop" onclick="window.scrollTo({top:0, behavior:'smooth'})" title="Back to top">Back to Top</button>

<script>
// Back to top button visibility
window.addEventListener('scroll', function() {{
  var btn = document.getElementById('backToTop');
  if (btn) btn.style.display = window.scrollY > 600 ? 'block' : 'none';
}});

// Scroll to bottom
function scrollToBottom() {{
  window.scrollTo({{top: document.body.scrollHeight, behavior: 'smooth'}});
}}

// Expand/collapse all tool calls
var allExpanded = false;
function toggleAllToolCalls() {{
  var details = document.querySelectorAll('details.tool-use');
  allExpanded = !allExpanded;
  details.forEach(function(d) {{ d.open = allExpanded; }});
  var btn = document.getElementById('expandCollapseBtn');
  if (btn) btn.textContent = allExpanded ? 'Collapse All' : 'Expand All';
  btn.classList.toggle('active', allExpanded);
}}

// Ctrl+F intercepts to use built-in search
document.addEventListener('keydown', function(e) {{
  if ((e.ctrlKey || e.metaKey) && e.key === 'f') {{
    e.preventDefault();
    var input = document.getElementById('searchInput');
    if (input) {{ input.focus(); input.select(); }}
  }}
}});
</script>
</body>
</html>""")

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(html_parts))


    return out_path



def _first_jsonl_timestamp(jsonl_path):
    """Extract the earliest timestamp from a JSONL file as a local epoch float."""
    try:
        with open(jsonl_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    ts = obj.get('timestamp')
                    if ts:
                        # JSONL timestamps are UTC ISO format
                        # Parse and convert to local epoch for consistency with file mtimes
                        from datetime import timezone
                        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        return dt.timestamp()  # Returns UTC epoch, same basis as os.path.getmtime
                except Exception:
                    continue
    except Exception:
        pass
    return None


def _find_related_jsonl_by_slug(jsonl_path):
    """Find all JSONL files with the same slug (conversation thread)."""
    parent_dir = os.path.dirname(jsonl_path)
    if not os.path.isdir(parent_dir):
        return [jsonl_path] if os.path.exists(jsonl_path) else []
    target_slug = None
    try:
        with open(jsonl_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if obj.get('slug'):
                        target_slug = obj['slug']
                        break
                except Exception:
                    continue
    except Exception:
        pass
    if not target_slug:
        return [jsonl_path] if os.path.exists(jsonl_path) else []
    related = []
    for fname in os.listdir(parent_dir):
        if not fname.endswith('.jsonl'):
            continue
        fp = os.path.join(parent_dir, fname)
        try:
            with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        if obj.get('slug') == target_slug:
                            related.append(fp)
                            break
                    except Exception:
                        continue
        except Exception:
            continue
    return related if related else [jsonl_path]


def _project_path_from_jsonl(jsonl_path):
    """Derive a short relative project path from the JSONL project directory name.

    Directory names look like:
      ${PROJECT_PATH}
      ${PROJECT_PATH}
    We convert back to path separators and take last 3 real path segments.
    """
    dirname = os.path.basename(os.path.dirname(jsonl_path))
    # -- is a path separator, single - is a hyphen within a segment
    # But the slug format uses single - for both separators and hyphens
    # Known prefixes to strip for brevity
    for prefix in [
        '${PROJECT_PATH}',
        '${PROJECT_PATH}',
        '${PROJECT_PATH}-',
    ]:
        if dirname.startswith(prefix):
            dirname = dirname[len(prefix):]
            break
    # What remains is the project name (may contain hyphens)
    return dirname


def update_manifest(exports_dir, project_name, session_name, html_path, branch, turn_count,
                    jsonl_source=None, project_path=None):
    """Update manifest.json with export metadata."""
    manifest_path = os.path.join(exports_dir, 'manifest.json')
    manifest = []
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except Exception:
            manifest = []

    # Remove existing entry for same HTML path
    rel_path = os.path.relpath(html_path, exports_dir).replace(chr(92), '/')
    manifest = [e for e in manifest if e.get('path') != rel_path]

    entry = {
        'path': rel_path,
        'project': project_name,
        'session': session_name,
        'branch': branch,
        'turns': turn_count,
        'size': os.path.getsize(html_path),
        'exported': datetime.now().isoformat(),
    }
    if jsonl_source:
        entry['jsonl_source'] = jsonl_source
        entry['project_path'] = _project_path_from_jsonl(jsonl_source)
        # Extract session UUID from JSONL filename for resume support
        entry['session_id'] = os.path.basename(jsonl_source).replace('.jsonl', '')
        # Extract working directory from first JSONL entry
        try:
            with open(jsonl_source, 'r', encoding='utf-8') as jf:
                for line in jf:
                    obj = json.loads(line)
                    if obj.get('cwd'):
                        entry['working_dir'] = obj['cwd'].replace(chr(92), '/')
                        break
        except Exception:
            pass
        # Compute created/last_modified from related JSONL files
        jsonl_files = _find_related_jsonl_by_slug(jsonl_source)
        if jsonl_files:
            mtimes = [os.path.getmtime(f) for f in jsonl_files]
            # Use file creation time (os.path.getctime) for "created" --
            # on Windows this is the actual file birth time, which matches
            # when the session was first started. JSONL timestamps are UTC
            # and require timezone conversion; file ctime is already local.
            ctimes = [os.path.getctime(f) for f in jsonl_files]
            entry['created'] = datetime.fromtimestamp(min(ctimes)).isoformat()
            entry['last_modified'] = datetime.fromtimestamp(max(mtimes)).isoformat()
    if project_path and 'project_path' not in entry:
        entry['project_path'] = project_path

    manifest.append(entry)

    # Sort by last_modified or exported descending
    manifest.sort(key=lambda e: e.get('last_modified', e.get('exported', '')), reverse=True)

    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    return manifest_path


def _scan_all_sessions():
    """Scan all JSONL session files across all projects. Returns list of dicts."""
    import glob as g
    projects_dir = os.path.expanduser('~/.claude/projects')
    sessions = []
    for proj_dir in g.glob(os.path.join(projects_dir, '*')):
        if not os.path.isdir(proj_dir):
            continue
        slug = os.path.basename(proj_dir)
        for jsonl in g.glob(os.path.join(proj_dir, '*.jsonl')):
            stat = os.stat(jsonl)
            if stat.st_size < 100:
                continue  # skip empty/tiny files
            uuid = os.path.basename(jsonl).replace('.jsonl', '')
            first_msg = ''
            cwd = ''
            version = ''
            try:
                with open(jsonl, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            obj = json.loads(line)
                            if not cwd and obj.get('cwd'):
                                cwd = obj['cwd'].replace(chr(92), '/')
                            if not version and obj.get('version'):
                                version = obj['version']
                            # Match both 'human' and 'user' type entries
                            if obj.get('type') in ('human', 'user'):
                                msg = obj.get('message', {})
                                if isinstance(msg, dict):
                                    content = msg.get('content', '')
                                    if isinstance(content, list):
                                        for c in content:
                                            if isinstance(c, dict) and c.get('type') == 'text':
                                                text = c['text'].strip()
                                                # Skip system/hook/task notifications
                                                if text and not text.startswith('<') and not text.startswith('Read the output'):
                                                    first_msg = text[:100]
                                                    break
                                    elif isinstance(content, str):
                                        text = content.strip()
                                        if text and not text.startswith('<') and not text.startswith('Read the output'):
                                            first_msg = text[:100]
                                if first_msg:
                                    break
                        except Exception:
                            pass
            except Exception:
                pass
            project_name = _project_path_from_jsonl(jsonl)
            sessions.append({
                'session_id': uuid,
                'slug': slug,
                'project': project_name,
                'working_dir': cwd,
                'modified': stat.st_mtime,
                'created': stat.st_ctime,
                'size': stat.st_size,
                'first_msg': first_msg,
                'version': version,
                'jsonl_path': jsonl,
            })
    sessions.sort(key=lambda s: s['modified'], reverse=True)
    return sessions


def generate_landing_page(exports_dir):
    """Generate index.html landing page with search, resume buttons, and recent sessions tab."""
    manifest_path = os.path.join(exports_dir, 'manifest.json')
    manifest = []
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except Exception:
            manifest = []

    # Backfill session_id and working_dir for older manifest entries
    for entry in manifest:
        if 'session_id' not in entry and entry.get('jsonl_source'):
            entry['session_id'] = os.path.basename(entry['jsonl_source']).replace('.jsonl', '')
        if 'working_dir' not in entry and entry.get('jsonl_source'):
            try:
                with open(entry['jsonl_source'], 'r', encoding='utf-8') as jf:
                    for line in jf:
                        obj = json.loads(line)
                        if obj.get('cwd'):
                            entry['working_dir'] = obj['cwd'].replace(chr(92), '/')
                            break
            except Exception:
                pass
    # Save backfilled manifest
    if manifest and os.path.exists(manifest_path):
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)

    esc = html.escape

    # Build exported sessions rows
    export_rows = []
    for entry in manifest:
        size_mb = entry.get('size', 0) / (1024 * 1024)
        size_str = f'{size_mb:.1f} MB' if size_mb >= 1 else f'{entry.get("size", 0) / 1024:.0f} KB'
        last_mod = entry.get('last_modified', entry.get('exported', ''))[:16].replace('T', ' ')
        created = entry.get('created', '')[:16].replace('T', ' ')
        proj_path = entry.get('project_path', entry.get('project', ''))
        sid = entry.get('session_id', '')
        wdir = entry.get('working_dir', '')
        resume_cmd = f'cd &quot;{esc(wdir)}&quot; &amp;&amp; claude -r {esc(sid)}' if sid and wdir else ''
        resume_btn = (
            f'<div class="btn-group">'
            f'<button class="resume-btn" onclick="copyResume(this, \'{esc(sid)}\', \'{esc(wdir)}\')" '
            f'title="Copy resume command">Copy</button>'
            f'<button class="launch-btn" onclick="launchResume(\'{esc(sid)}\', \'{esc(wdir)}\')" '
            f'title="Open terminal and resume">Launch</button>'
            f'</div>'
        ) if sid else ''
        export_rows.append(
            f'        <tr class="export-row" data-search="{esc(proj_path)} {esc(entry.get("session",""))} {esc(sid)}">\n'
            f'          <td><a href="{esc(entry.get("path",""))}">{esc(entry.get("session","")[:70])}</a></td>\n'
            f'          <td>{esc(proj_path)}</td>\n'
            f'          <td class="sid" onclick="copySid(\'{esc(sid)}\')" title="Click to copy full ID">{esc(sid[:8])}...</td>\n'
            f'          <td>{entry.get("turns", 0)}</td>\n'
            f'          <td>{size_str}</td>\n'
            f'          <td data-sort="{esc(last_mod)}">{last_mod}</td>\n'
            f'          <td>{resume_btn}</td>\n'
            f'        </tr>'
        )

    # Scan all recent sessions
    all_sessions = _scan_all_sessions()
    # Build "Recent Sessions" rows (top 50)
    session_rows = []
    exported_ids = {e.get('session_id') for e in manifest if e.get('session_id')}
    exported_paths = {e.get('session_id'): e.get('path', '') for e in manifest if e.get('session_id')}
    for s in all_sessions[:50]:
        size_kb = s['size'] / 1024
        size_str = f'{size_kb / 1024:.1f} MB' if size_kb >= 1024 else f'{size_kb:.0f} KB'
        mod_dt = datetime.fromtimestamp(s['modified']).strftime('%Y-%m-%d %H:%M')
        cre_dt = datetime.fromtimestamp(s['created']).strftime('%Y-%m-%d %H:%M')
        sid = s['session_id']
        wdir = s['working_dir']
        resume_cmd = f'cd &quot;{esc(wdir)}&quot; &amp;&amp; claude -r {esc(sid)}' if sid and wdir else ''
        resume_btn = (
            f'<button class="resume-btn" onclick="copyResume(this, \'{esc(sid)}\', \'{esc(wdir)}\')" '
            f'title="{resume_cmd}">Resume</button>'
        ) if sid and wdir else ''
        exported_badge = '<span class="badge-exported">[E]</span> ' if sid in exported_ids else ''
        first_msg_display = esc(s['first_msg'][:70]) if s['first_msg'] else '<span style="color:#666">(no message)</span>'
        export_href = exported_paths.get(sid, '')
        if export_href:
            first_msg_link = f'<a href="{esc(export_href)}">{first_msg_display}</a>'
        else:
            _jsonl_esc = esc(s.get("jsonl_path", "").replace(chr(92), "/"))
            first_msg_link = f'<a href="#" class="gen-link" onclick="generateExport(this, \'{esc(sid)}\', \'{_jsonl_esc}\'); return false;">{first_msg_display}</a>'
        session_rows.append(
            f'        <tr class="session-row" data-search="{esc(s["project"])} {esc(s["first_msg"])} {esc(sid)}">\n'
            f'          <td>{exported_badge}{first_msg_link}</td>\n'
            f'          <td>{esc(s["project"])}</td>\n'
            f'          <td class="sid" onclick="copySid(\'{esc(sid)}\')" title="Click to copy full ID">{esc(sid[:8])}...</td>\n'
            f'          <td>{size_str}</td>\n'
            f'          <td data-sort="{esc(cre_dt)}">{cre_dt}</td>\n'
            f'          <td data-sort="{esc(mod_dt)}">{mod_dt}</td>\n'
            f'          <td>{resume_btn}</td>\n'
            f'        </tr>'
        )

    export_table = '\n'.join(export_rows)
    session_table = '\n'.join(session_rows)

    landing_html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Claude Code Sessions</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #0C0C0C; color: #CCCCCC; font-family: "Cascadia Code", "Consolas", monospace; padding: 0; }}
  .header {{
    background: #1a1a2e; border-bottom: 1px solid #333;
    padding: 12px 20px; display: flex; align-items: center; gap: 16px;
    position: sticky; top: 0; z-index: 100;
  }}
  .header h1 {{ color: #D4A843; font-size: 18px; font-weight: 600; flex: 1; }}
  .search-box {{
    background: #2a2a3e; border: 1px solid #444; border-radius: 6px;
    color: #CCCCCC; padding: 8px 14px; font-size: 14px; width: 300px;
    font-family: inherit;
  }}
  .search-box:focus {{ outline: none; border-color: #D4A843; }}
  thead {{ position: sticky; top: 44px; z-index: 50; }}
  thead th {{ background: #1a1a2e; }}
  .tabs {{
    display: flex; gap: 0; background: #1a1a2e; border-bottom: 1px solid #333;
    padding: 0 20px;
  }}
  .tab {{
    padding: 10px 20px; cursor: pointer; color: #888; font-size: 13px;
    border-bottom: 2px solid transparent; transition: all 0.2s;
  }}
  .tab:hover {{ color: #ccc; }}
  .tab.active {{ color: #D4A843; border-bottom-color: #D4A843; }}
  .container {{ padding: 20px; }}
  .tab-content {{ display: none; }}
  .tab-content.active {{ display: block; }}
  .stats {{ color: #888; margin-bottom: 16px; font-size: 13px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; padding: 10px 12px; color: #D4A843; border-bottom: 2px solid #333; font-size: 13px; cursor: pointer; user-select: none; }}
  th:hover {{ color: #fff; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #222; font-size: 12px; }}
  td a {{ color: #58a6ff; text-decoration: none; }}
  td a:hover {{ text-decoration: underline; }}
  tr:hover {{ background: #1a1a2e; }}
  .hidden {{ display: none; }}
  .sort-arrow {{ margin-left: 4px; font-size: 10px; }}
  .sid {{ color: #8b949e; cursor: pointer; font-size: 11px; }}
  .sid:hover {{ color: #58a6ff; }}
  .resume-btn {{
    background: #238636; color: #fff; border: none; border-radius: 4px;
    padding: 4px 8px; cursor: pointer; font-size: 11px; font-family: inherit;
    transition: background 0.2s;
  }}
  .resume-btn:hover {{ background: #2ea043; }}
  .resume-btn.copied {{ background: #1a7f37; }}
  .launch-btn {{
    background: #1f6feb; color: #fff; border: none; border-radius: 4px;
    padding: 4px 8px; cursor: pointer; font-size: 11px; font-family: inherit;
    transition: background 0.2s; margin-left: 4px;
  }}
  .launch-btn:hover {{ background: #388bfd; }}
  .btn-group {{ display: flex; gap: 2px; align-items: center; }}
  .badge-exported {{ color: #3fb950; font-size: 10px; }}
  .toast {{
    position: fixed; bottom: 20px; right: 20px; background: #238636;
    color: #fff; padding: 10px 20px; border-radius: 6px; font-size: 13px;
    opacity: 0; transition: opacity 0.3s; pointer-events: none; z-index: 200;
  }}
  .toast.show {{ opacity: 1; }}
</style>
</head>
<body>
<div class="header">
  <h1>Claude Code Sessions</h1>
  <input type="text" class="search-box" placeholder="Search..." id="searchBox">
</div>
<div class="tabs">
  <div class="tab active" onclick="switchTab('recent')">Recent Sessions ({len(all_sessions[:50])})</div>
  <div class="tab" onclick="switchTab('exports')">Exported ({len(manifest)})</div>
</div>
<div class="container">
  <div id="tab-recent" class="tab-content active">
    <div class="stats">{len(all_sessions)} total session(s), showing {min(50, len(all_sessions))}</div>
    <table>
      <thead><tr>
        <th onclick="sortTab('recent',0)">First Message</th>
        <th onclick="sortTab('recent',1)">Project</th>
        <th onclick="sortTab('recent',2)">Session ID</th>
        <th onclick="sortTab('recent',3)">Size</th>
        <th onclick="sortTab('recent',4)">Created</th>
        <th onclick="sortTab('recent',5)">Modified</th>
        <th>Resume</th>
      </tr></thead>
      <tbody id="recentTable">
{session_table}
      </tbody>
    </table>
  </div>
  <div id="tab-exports" class="tab-content">
    <div class="stats">{len(manifest)} export(s)</div>
    <table>
      <thead><tr>
        <th onclick="sortTab('exports',0)">Session</th>
        <th onclick="sortTab('exports',1)">Project</th>
        <th onclick="sortTab('exports',2)">Session ID</th>
        <th onclick="sortTab('exports',3)">Turns</th>
        <th onclick="sortTab('exports',4)">Size</th>
        <th onclick="sortTab('exports',5)">Last Modified</th>
        <th>Resume</th>
      </tr></thead>
      <tbody id="exportTable">
{export_table}
      </tbody>
    </table>
  </div>
</div>
<div class="spinner-overlay" id="spinnerOverlay">
  <div class="comet-ring"></div>
  <div class="spinner-text" id="spinnerText">Generating export...</div>
  <div class="spinner-cmd" id="spinnerCmd" onclick="copySpinnerCmd()" title="Click to copy command"></div>
</div>
<div class="toast" id="toast"></div>
<script>
function showToast(msg) {{
  var t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(function() {{ t.classList.remove('show'); }}, 2000);
}}
function copyResume(btn, sid, wdir) {{
  var cmd = 'cd "' + wdir.replace(/[\\]/g, '/') + '" && claude -r ' + sid;
  navigator.clipboard.writeText(cmd).then(function() {{
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    showToast('Resume command copied to clipboard');
    setTimeout(function() {{ btn.textContent = 'Copy'; btn.classList.remove('copied'); }}, 2000);
  }});
}}
function launchResume(sid, wdir) {{
  var isWin = navigator.platform.indexOf('Win') > -1;
  var cmd;
  if (isWin) {{
    var winDir = wdir.replace(/[/]/g, '\\');
    cmd = 'cmd /k cd /d "' + winDir + '" && claude -r ' + sid;
  }} else {{
    cmd = 'cd "' + wdir + '" && claude -r ' + sid;
  }}
  navigator.clipboard.writeText(cmd).then(function() {{
    if (isWin) {{
      showToast('Copied -- press Win+R, paste, Enter');
    }} else {{
      showToast('Copied -- paste in Terminal, Enter');
    }}
  }});
}}
function generateExport(link, sid, jsonlPath) {{
  var overlay = document.getElementById('spinnerOverlay');
  var cmdEl = document.getElementById('spinnerCmd');
  var cmd = 'python3 ~/.claude/skills/chat-export/export.py --jsonl "' + jsonlPath + '"';
  cmdEl.textContent = cmd;
  cmdEl.dataset.cmd = cmd;
  overlay.classList.add('active');
  // Cannot run Python from file:// -- show command to copy
  document.getElementById('spinnerText').textContent = 'Generating export... paste command in terminal:';
}}
function copySpinnerCmd() {{
  var cmd = document.getElementById('spinnerCmd').dataset.cmd;
  navigator.clipboard.writeText(cmd).then(function() {{
    showToast('Command copied -- paste in terminal, then refresh');
    setTimeout(function() {{
      document.getElementById('spinnerOverlay').classList.remove('active');
    }}, 1500);
  }});
}}
function copySid(sid) {{
  navigator.clipboard.writeText(sid).then(function() {{
    showToast('Session ID copied: ' + sid);
  }});
}}
function switchTab(name) {{
  document.querySelectorAll('.tab').forEach(function(t, i) {{
    t.classList.toggle('active', (name === 'recent' && i === 0) || (name === 'exports' && i === 1));
  }});
  document.querySelectorAll('.tab-content').forEach(function(c) {{
    c.classList.toggle('active', c.id === 'tab-' + name);
  }});
}}
document.getElementById('searchBox').addEventListener('input', function() {{
  var q = this.value.toLowerCase();
  document.querySelectorAll('.export-row, .session-row').forEach(function(r) {{
    r.classList.toggle('hidden', !r.dataset.search.toLowerCase().includes(q));
  }});
}});
var sortDirs = {{}};
function sortTab(tab, col) {{
  var tbodyId = tab === 'recent' ? 'recentTable' : 'exportTable';
  var tbody = document.getElementById(tbodyId);
  var rows = Array.from(tbody.querySelectorAll('tr'));
  var key = tab + col;
  sortDirs[key] = !sortDirs[key];
  rows.sort(function(a, b) {{
    var va = a.cells[col].dataset.sort || a.cells[col].textContent.trim();
    var vb = b.cells[col].dataset.sort || b.cells[col].textContent.trim();
    var na = parseFloat(va), nb = parseFloat(vb);
    if (!isNaN(na) && !isNaN(nb)) return sortDirs[key] ? na - nb : nb - na;
    return sortDirs[key] ? va.localeCompare(vb) : vb.localeCompare(va);
  }});
  rows.forEach(function(r) {{ tbody.appendChild(r); }});
}}
</script>
</body>
</html>'''

    index_path = os.path.join(exports_dir, 'index.html')
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(landing_html)


    return index_path


if __name__ == '__main__':
    args = parse_args()

    # Landing page only mode
    if args.landing:
        os.makedirs(EXPORTS_DIR, exist_ok=True)
        # Auto-generate missing exports
        all_sess = _scan_all_sessions()
        manifest_path = os.path.join(EXPORTS_DIR, 'manifest.json')
        existing_manifest = []
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    existing_manifest = json.load(f)
            except Exception:
                pass
        exported_sids = {e.get('session_id') for e in existing_manifest if e.get('session_id')}
        missing = [s for s in all_sess if s['session_id'] not in exported_sids and s.get('jsonl_path')]
        if missing:
            print(f'Generating {len(missing)} missing export(s)...')
            for s in missing:
                try:
                    msgs = parse_messages(s['jsonl_path'])
                    if not msgs or len(msgs) < 2:
                        continue
                    pname = _project_path_from_jsonl(s['jsonl_path']).split('/')[-1] or 'project'
                    sname = detect_session_name(msgs)
                    br = detect_branch()
                    ppath = s.get('working_dir', '')
                    project_dir = os.path.join(EXPORTS_DIR, 'worker')
                    os.makedirs(project_dir, exist_ok=True)
                    safe_name = re.sub(r'[^a-zA-Z0-9-]', '-', sname.lower())[:50]
                    opath = os.path.join(project_dir, f'{safe_name}.html')
                    out = generate_html(msgs, opath, session_name=sname,
                                        project_name=pname, branch=br,
                                        project_path=ppath, screenshot_dir=None,
                                        session_id=s['session_id'], working_dir=s.get('working_dir', ''))
                    size = os.path.getsize(out)
                    size_str = f'{size/1024/1024:.1f} MB' if size > 1024*1024 else f'{size/1024:.0f} KB'
                    print(f'  {sname[:40]:40s} {len(msgs):5d} turns  {size_str:>8s}')
                    update_manifest(EXPORTS_DIR, pname, sname, out, br, len(msgs),
                                    jsonl_source=s['jsonl_path'])
                except Exception as e:
                    print(f'  SKIP: {s["session_id"][:8]}: {e}')
        lp = generate_landing_page(EXPORTS_DIR)
        if lp:
            print(f'Landing page: {lp}')
        sys.exit(0)

    # Export all sessions mode
    if getattr(args, 'all', False):
        sessions = find_project_sessions()
        if not sessions:
            print('ERROR: No sessions found for current project')
            sys.exit(1)
        print(f'Found {len(sessions)} session(s)')
        os.makedirs(EXPORTS_DIR, exist_ok=True)
        for jsonl_path in sessions:
            try:
                msgs = parse_messages(jsonl_path)
                if not msgs:
                    continue
                pname = args.project or detect_project_name(jsonl_path)
                sname = detect_session_name(msgs)
                br = args.branch or detect_branch()
                ppath = args.project_path or detect_project_path()
                project_dir = os.path.join(EXPORTS_DIR, pname)
                os.makedirs(project_dir, exist_ok=True)
                safe_name = re.sub(r'[^a-zA-Z0-9-]', '-', sname.lower())[:50]
                opath = os.path.join(project_dir, f'{safe_name}.html')
                _sid = os.path.basename(jsonl_path).replace('.jsonl', '')
                _wdir = ''
                try:
                    with open(jsonl_path, 'r', encoding='utf-8') as _jf:
                        for _line in _jf:
                            _obj = json.loads(_line)
                            if _obj.get('cwd'):
                                _wdir = _obj['cwd'].replace(chr(92), '/')
                                break
                except Exception:
                    pass
                out = generate_html(msgs, opath, session_name=sname,
                                    project_name=pname, branch=br,
                                    project_path=ppath, screenshot_dir=args.screenshots,
                                    session_id=_sid, working_dir=_wdir)
                size = os.path.getsize(out)
                size_str = f'{size/1024/1024:.1f} MB' if size > 1024*1024 else f'{size/1024:.0f} KB'
                print(f'  {sname[:40]:40s} {len(msgs):5d} turns  {size_str:>8s}  -> {out}')
                update_manifest(EXPORTS_DIR, pname, sname, out, br, len(msgs),
                                jsonl_source=jsonl_path)
            except Exception as e:
                print(f'  ERROR: {jsonl_path}: {e}')
        lp = generate_landing_page(EXPORTS_DIR)
        if lp:
            print(f'Landing page: {lp}')
        sys.exit(0)

    # Resolve JSONL path
    jsonl_path = args.jsonl
    if not jsonl_path:
        jsonl_path = find_current_session()
        if not jsonl_path:
            print('ERROR: No JSONL file specified and could not auto-detect current session')
            sys.exit(1)
        print(f'Auto-detected session: {jsonl_path}')

    # Stitch mode: find and merge related sessions
    stitch_paths = None
    if getattr(args, 'stitch', False):
        stitch_paths = find_related_sessions(jsonl_path)
        if len(stitch_paths) > 1:
            print(f'Stitch mode: found {len(stitch_paths)} related session(s)')
            for sp in stitch_paths:
                sz = os.path.getsize(sp)
                sz_str = f'{sz/1024/1024:.1f}MB' if sz > 1024*1024 else f'{sz/1024:.0f}KB'
                print(f'  {os.path.basename(sp)} ({sz_str})')
        else:
            print('Stitch mode: only 1 session found, exporting normally')

    # Parse messages
    msgs = parse_messages(jsonl_path, stitch_paths=stitch_paths)
    print(f'Parsed {len(msgs)} conversation turns')

    # Auto-detect metadata
    project_name = args.project or detect_project_name(jsonl_path)
    session_name = args.name or detect_session_name(msgs)
    branch = args.branch or detect_branch()
    project_path = args.project_path or detect_project_path()
    screenshot_dir = args.screenshots

    # Determine output path
    if args.out:
        out_path = args.out
    else:
        project_dir = os.path.join(EXPORTS_DIR, project_name)
        os.makedirs(project_dir, exist_ok=True)
        safe_name = re.sub(r'[^a-zA-Z0-9-]', '-', session_name.lower())[:50]
        out_path = os.path.join(project_dir, f'{safe_name}.html')

    # Extract session_id and working_dir for resume buttons
    _sid = os.path.basename(jsonl_path).replace('.jsonl', '')
    _wdir = ''
    try:
        with open(jsonl_path, 'r', encoding='utf-8') as _jf:
            for _line in _jf:
                _obj = json.loads(_line)
                if _obj.get('cwd'):
                    _wdir = _obj['cwd'].replace(chr(92), '/')
                    break
    except Exception:
        pass

    # Generate HTML
    out = generate_html(msgs, out_path, session_name=session_name,
                        project_name=project_name, branch=branch,
                        project_path=project_path, screenshot_dir=screenshot_dir,
                        session_id=_sid, working_dir=_wdir)
    print(f'Exported to: {out}')
    size = os.path.getsize(out)
    if size > 1024*1024:
        print(f'Size: {size/1024/1024:.1f} MB')
    else:
        print(f'Size: {size/1024:.0f} KB')

    # Update manifest and landing page
    os.makedirs(EXPORTS_DIR, exist_ok=True)
    update_manifest(EXPORTS_DIR, project_name, session_name, out, branch, len(msgs),
                    jsonl_source=jsonl_path)
    lp = generate_landing_page(EXPORTS_DIR)
    if lp:
        print(f'Landing page: {lp}')
