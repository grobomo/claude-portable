"""Rule scanner - finds all Claude Code rules and their firing stats."""
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.path_utils import get_home, get_claude_dir


class RuleScanner:
    """Scan rule-book/ for rules and parse loader logs for firing stats."""

    def __init__(self):
        self.home = get_home()
        self.claude_dir = get_claude_dir()

    def scan(self, quick=False) -> Dict[str, Any]:
        rules_by_event = {}
        rule_book_dir = self.claude_dir / 'rule-book'
        rules_dir = self.claude_dir / 'rules'

        # Scan rule-book/ (canonical location)
        for event_dir_name in ['UserPromptSubmit', 'Stop', 'PreToolUse', 'PostToolUse']:
            rules_list = []
            edir = rule_book_dir / event_dir_name
            if edir.is_dir():
                for f in sorted(edir.iterdir()):
                    if f.suffix != '.md':
                        continue
                    try:
                        content = f.read_text(encoding='utf-8')
                        meta = self._parse_frontmatter(content)
                        if not meta:
                            continue
                        meta['_file'] = f.name
                        meta['_path'] = str(f)
                        meta['_event'] = event_dir_name
                        meta['_source'] = 'rule-book'
                        if 'id' not in meta:
                            meta['id'] = f.stem
                        rules_list.append(meta)
                    except Exception:
                        pass
            if rules_list:
                rules_list.sort(key=lambda r: int(r.get('priority', '10') or '10'))
                rules_by_event[event_dir_name] = rules_list

        # Flag any .md files in rules/ (WRONG location -- should be in rule-book/)
        misplaced_rules = []
        for event_dir_name in ['UserPromptSubmit', 'Stop', 'PreToolUse', 'PostToolUse']:
            edir = rules_dir / event_dir_name
            if not edir.is_dir():
                continue
            for f in sorted(edir.iterdir()):
                if f.suffix != '.md':
                    continue
                try:
                    content = f.read_text(encoding='utf-8')
                    meta = self._parse_frontmatter(content)
                    if not meta:
                        meta = {}
                    meta['_file'] = f.name
                    meta['_path'] = str(f)
                    meta['_event'] = event_dir_name
                    meta['_source'] = 'rules (MISPLACED)'
                    if 'id' not in meta:
                        meta['id'] = f.stem
                    misplaced_rules.append(meta)
                except Exception:
                    pass
        # Also flag any .md at rules/ root level (not in event subdirs)
        if rules_dir.is_dir():
            for f in sorted(rules_dir.iterdir()):
                if f.suffix == '.md' and f.is_file():
                    try:
                        content = f.read_text(encoding='utf-8')
                        meta = self._parse_frontmatter(content) or {}
                        meta['_file'] = f.name
                        meta['_path'] = str(f)
                        meta['_event'] = 'unknown'
                        meta['_source'] = 'rules (MISPLACED)'
                        if 'id' not in meta:
                            meta['id'] = f.stem
                        misplaced_rules.append(meta)
                    except Exception:
                        pass

        # Parse firing stats from logs
        firing_stats = {}
        if not quick:
            firing_stats = self._parse_firing_stats(rules_dir)

        # Also scan MCP-collocated rules
        mcp_rules = self._scan_mcp_rules()

        return {
            'rules_by_event': rules_by_event,
            'firing_stats': firing_stats,
            'mcp_rules': mcp_rules,
            'misplaced_rules': misplaced_rules,
            'total': sum(len(v) for v in rules_by_event.values()),
            'mcp_total': sum(len(v) for v in mcp_rules.values()),
            'misplaced_total': len(misplaced_rules),
        }

    def _parse_frontmatter(self, content: str) -> dict:
        """Parse YAML frontmatter from markdown."""
        if not content.startswith('---'):
            return {}
        end = content.find('---', 3)
        if end == -1:
            return {}
        yaml_str = content[3:end].strip()
        meta = {}
        current_list_key = None
        for line in yaml_str.split('\n'):
            trimmed = line.strip()
            if trimmed.startswith('- ') and current_list_key:
                if not isinstance(meta.get(current_list_key), list):
                    meta[current_list_key] = []
                meta[current_list_key].append(trimmed[2:].strip())
                continue
            current_list_key = None
            col = line.find(':')
            if col == -1:
                continue
            key = line[:col].strip()
            val = line[col+1:].strip()
            if val.startswith('[') and val.endswith(']'):
                meta[key] = [s.strip().strip('"').strip("'") for s in val[1:-1].split(',')]
            elif val == '':
                current_list_key = key
            else:
                meta[key] = val.strip('"').strip("'")
        meta['body'] = content[end+3:].strip()
        return meta

    def _parse_firing_stats(self, rules_dir: Path) -> Dict[str, Dict]:
        """Parse loader.log and stop-loader.log for firing counts by time window."""
        stats = defaultdict(lambda: {'hour': 0, 'day': 0, 'week': 0, 'month': 0, 'year': 0, 'total': 0, 'last_fired': None})
        now = datetime.now(timezone.utc)
        cutoffs = {
            'hour': now - timedelta(hours=1),
            'day': now - timedelta(days=1),
            'week': now - timedelta(weeks=1),
            'month': now - timedelta(days=30),
            'year': now - timedelta(days=365),
        }

        # Parse UserPromptSubmit/PreToolUse firings from loader.log
        loader_log = rules_dir / 'loader.log'
        if loader_log.exists():
            self._parse_log_file(loader_log, stats, cutoffs, now, 'keyword')

        # Parse Stop firings from stop-loader.log
        stop_log = rules_dir / 'stop-loader.log'
        if stop_log.exists():
            self._parse_log_file(stop_log, stats, cutoffs, now, 'stop')

        return dict(stats)

    def _parse_log_file(self, log_path: Path, stats, cutoffs, now, log_type):
        """Parse a single log file for firing events."""
        # Patterns:
        # loader.log:  2026-03-11T02:50:18.351Z [KEYWORD] trigger="..." match=rule-id (2/2) -> path
        # loader.log:  2026-02-14 19:46:14 [KEYWORD] trigger="..." match="hook" -> file.md (loaded)
        # stop-loader: 2026-03-11T02:38:51.571Z [STOP] pattern hit -> rule-file.md matched="..."
        # stop-loader: 2026-03-11T02:06:18.116Z [STOP] BLOCKING - 1 rule(s): rule-id ("pattern: ...")

        keyword_re = re.compile(
            r'^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})'
            r'.*?\[KEYWORD\].*?->\s*(?:.*[/\\])?([^/\\\s]+\.md)'
        )
        stop_hit_re = re.compile(
            r'^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})'
            r'.*?\[STOP\]\s+(?:pattern hit|BLOCKING).*?(?:->|rule\(s\):)\s*(\S+)'
        )

        try:
            # Read file in chunks from the end for efficiency on large logs
            file_size = log_path.stat().st_size
            # Only parse last 2MB for performance
            max_bytes = 2 * 1024 * 1024
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                if file_size > max_bytes:
                    f.seek(file_size - max_bytes)
                    f.readline()  # skip partial line
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    match = None
                    rule_id = None

                    if log_type == 'keyword':
                        m = keyword_re.match(line)
                        if m:
                            ts_str = m.group(1)
                            rule_file = m.group(2)
                            rule_id = rule_file.replace('.md', '')
                            match = m
                    else:  # stop
                        m = stop_hit_re.match(line)
                        if m:
                            ts_str = m.group(1)
                            raw = m.group(2)
                            # Could be "rule-id" or "rule-file.md"
                            rule_id = raw.replace('.md', '').strip('"').strip("'")
                            match = m

                    if match and rule_id:
                        # Parse timestamp
                        ts = self._parse_ts(ts_str)
                        if ts is None:
                            continue
                        stats[rule_id]['total'] += 1
                        for window, cutoff in cutoffs.items():
                            if ts >= cutoff:
                                stats[rule_id][window] += 1
                        # Track last fired
                        if stats[rule_id]['last_fired'] is None or ts > stats[rule_id]['last_fired']:
                            stats[rule_id]['last_fired'] = ts
        except Exception:
            pass

    def _parse_ts(self, ts_str):
        """Parse timestamp string to datetime."""
        for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S'):
            try:
                dt = datetime.strptime(ts_str, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    def _scan_mcp_rules(self) -> Dict[str, List[Dict]]:
        """Scan MCP server directories for collocated rules."""
        result = {}
        mcp_base = self.claude_dir.parent / 'Documents' / 'ProjectsCL1' / 'MCP'
        if not mcp_base.is_dir():
            return result
        for server_dir in mcp_base.iterdir():
            if not server_dir.is_dir():
                continue
            rules_dir = server_dir / 'rules'
            if not rules_dir.is_dir():
                continue
            rules_list = []
            for f in sorted(rules_dir.iterdir()):
                if f.suffix != '.md':
                    continue
                try:
                    content = f.read_text(encoding='utf-8')
                    meta = self._parse_frontmatter(content)
                    if meta:
                        meta['_file'] = f.name
                        meta['_path'] = str(f)
                        meta['_event'] = 'UserPromptSubmit'
                        meta['_source'] = f'mcp:{server_dir.name}'
                        if 'id' not in meta:
                            meta['id'] = f.stem
                        rules_list.append(meta)
                except Exception:
                    pass
            if rules_list:
                result[server_dir.name] = rules_list
        return result
