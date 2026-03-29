"""Tiny HTTP server for rule editing from the HTML report.

Provides save, backup, and git operations via JSON API.
Started by main.py on a random port, killed when report is closed.
"""
import json
import os
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs


class RuleEditorHandler(BaseHTTPRequestHandler):
    """Handle rule editing API requests."""

    def log_message(self, format, *args):
        pass  # suppress console spam

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/ping':
            self._json_response({'ok': True})

        elif path == '/api/read':
            params = parse_qs(parsed.query)
            file_path = params.get('path', [None])[0]
            if not file_path:
                self._json_response({'error': 'Missing path'}, 400)
                return
            file_path = _safe_path(file_path)
            if not file_path:
                self._json_response({'error': 'Path not allowed'}, 403)
                return
            try:
                content = file_path.read_text(encoding='utf-8')
                self._json_response({'ok': True, 'content': content, 'path': str(file_path)})
            except Exception as e:
                self._json_response({'error': str(e)}, 500)

        elif path == '/api/git-status':
            params = parse_qs(parsed.query)
            dir_path = params.get('dir', [None])[0]
            if not dir_path:
                dir_path = str(Path.home() / '.claude' / 'rule-book')
            result = _git_status(dir_path)
            self._json_response(result)

        else:
            self._json_response({'error': 'Not found'}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        content_len = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_len)) if content_len > 0 else {}

        if path == '/api/save':
            file_path = body.get('path')
            content = body.get('content')
            if not file_path or content is None:
                self._json_response({'error': 'Missing path or content'}, 400)
                return
            file_path = _safe_path(file_path)
            if not file_path:
                self._json_response({'error': 'Path not allowed'}, 403)
                return
            try:
                file_path.write_text(content, encoding='utf-8')
                self._json_response({'ok': True, 'path': str(file_path)})
            except Exception as e:
                self._json_response({'error': str(e)}, 500)

        elif path == '/api/backup':
            file_path = body.get('path')
            if not file_path:
                self._json_response({'error': 'Missing path'}, 400)
                return
            file_path = _safe_path(file_path)
            if not file_path:
                self._json_response({'error': 'Path not allowed'}, 403)
                return
            try:
                result = _backup_file(file_path)
                self._json_response(result)
            except Exception as e:
                self._json_response({'error': str(e)}, 500)

        elif path == '/api/git-init':
            dir_path = body.get('dir')
            if not dir_path:
                dir_path = str(Path.home() / '.claude' / 'rule-book')
            try:
                result = _git_init(dir_path)
                self._json_response(result)
            except Exception as e:
                self._json_response({'error': str(e)}, 500)

        elif path == '/api/git-commit':
            file_path = body.get('path')
            message = body.get('message', 'Rule edited via claude-report')
            if not file_path:
                self._json_response({'error': 'Missing path'}, 400)
                return
            try:
                result = _git_commit(file_path, message)
                self._json_response(result)
            except Exception as e:
                self._json_response({'error': str(e)}, 500)

        else:
            self._json_response({'error': 'Not found'}, 404)


def _safe_path(p):
    """Only allow paths under ~/.claude/rule-book/ or ~/.claude/rules/."""
    try:
        resolved = Path(p).resolve()
        claude_dir = Path.home() / '.claude'
        allowed = [
            claude_dir / 'rule-book',
            claude_dir / 'rules',
        ]
        for a in allowed:
            try:
                resolved.relative_to(a.resolve())
                return resolved
            except ValueError:
                continue
        return None
    except Exception:
        return None


def _backup_file(file_path):
    """Back up a rule file: copy to archive/ with timestamp suffix."""
    if not file_path.exists():
        return {'error': f'File not found: {file_path}'}

    archive_dir = file_path.parent / 'archive'
    archive_dir.mkdir(exist_ok=True)

    ts = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_name = f'{file_path.stem}.bak_{ts}{file_path.suffix}'
    backup_path = archive_dir / backup_name

    shutil.copy2(file_path, backup_path)
    return {
        'ok': True,
        'backup_path': str(backup_path),
        'original': str(file_path),
    }


def _git_status(dir_path):
    """Check if a directory is in a git repo and if rules are tracked."""
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--is-inside-work-tree'],
            cwd=dir_path, capture_output=True, text=True, timeout=5
        )
        is_repo = result.returncode == 0

        tracked = False
        dirty = False
        if is_repo:
            # Check if there are tracked files
            result2 = subprocess.run(
                ['git', 'ls-files', '--error-unmatch', '.'],
                cwd=dir_path, capture_output=True, text=True, timeout=5
            )
            tracked = result2.returncode == 0

            # Check for uncommitted changes
            result3 = subprocess.run(
                ['git', 'status', '--porcelain', '.'],
                cwd=dir_path, capture_output=True, text=True, timeout=5
            )
            dirty = bool(result3.stdout.strip())

        return {
            'ok': True,
            'is_repo': is_repo,
            'tracked': tracked,
            'dirty': dirty,
            'dir': dir_path,
        }
    except FileNotFoundError:
        return {'ok': True, 'is_repo': False, 'tracked': False, 'dirty': False, 'dir': dir_path}
    except Exception as e:
        return {'error': str(e)}


def _git_init(dir_path):
    """Initialize a git repo in the given directory."""
    try:
        env = os.environ.copy()
        env['GIT_COMMITTER_NAME'] = 'claude-report'
        env['GIT_COMMITTER_EMAIL'] = 'claude-report@local'
        env['GIT_AUTHOR_NAME'] = 'claude-report'
        env['GIT_AUTHOR_EMAIL'] = 'claude-report@local'
        subprocess.run(['git', 'init'], cwd=dir_path, capture_output=True, text=True, timeout=30, env=env)
        # Disable GPG signing for this local backup repo
        subprocess.run(['git', 'config', 'commit.gpgsign', 'false'], cwd=dir_path, capture_output=True, text=True, timeout=10, env=env)
        subprocess.run(['git', 'add', '.'], cwd=dir_path, capture_output=True, text=True, timeout=30, env=env)
        result = subprocess.run(
            ['git', 'commit', '-m', 'Initial commit: rule-book tracked by claude-report'],
            cwd=dir_path, capture_output=True, text=True, timeout=30, env=env
        )
        if result.returncode != 0:
            return {'error': f'git commit failed: {result.stderr.strip()}'}
        return {'ok': True, 'dir': dir_path}
    except Exception as e:
        return {'error': str(e)}


def _git_commit(file_path, message):
    """Stage and commit a specific file."""
    try:
        dir_path = str(Path(file_path).parent)
        env = os.environ.copy()
        env['GIT_COMMITTER_NAME'] = 'claude-report'
        env['GIT_COMMITTER_EMAIL'] = 'claude-report@local'
        env['GIT_AUTHOR_NAME'] = 'claude-report'
        env['GIT_AUTHOR_EMAIL'] = 'claude-report@local'
        subprocess.run(['git', 'add', str(file_path)], cwd=dir_path, capture_output=True, text=True, timeout=30, env=env)
        result = subprocess.run(
            ['git', 'commit', '--no-gpg-sign', '-m', message],
            cwd=dir_path, capture_output=True, text=True, timeout=30, env=env
        )
        return {'ok': True, 'output': result.stdout.strip() or result.stderr.strip()}
    except Exception as e:
        return {'error': str(e)}


def start_server(port=0):
    """Start the editor server. Returns (server, port)."""
    server = HTTPServer(('127.0.0.1', port), RuleEditorHandler)
    actual_port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, actual_port


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    server, actual_port = start_server(port)
    print(f'Rule editor server running on http://127.0.0.1:{actual_port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
