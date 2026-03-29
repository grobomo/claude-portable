#!/usr/bin/env python3
"""
{{SKILL_NAME}} - Local HTTP server for browser skill

Provides API endpoints for file operations from browser UI.
"""

import http.server
import json
import os
import sys
import secrets
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PORT = 8765
TOKEN = secrets.token_urlsafe(16)


class SkillHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        
        if parsed.path == "/health":
            self.send_json({"status": "ok"})
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        # Verify token
        if data.get("token") != TOKEN:
            self.send_error(403, "Invalid token")
            return

        if parsed.path == "/action":
            # TODO: Implement action
            self.send_json({"success": True})
        else:
            self.send_error(404)

    def send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        pass  # Suppress logging


def main():
    project_root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    
    # Write token to file for generate.py
    token_file = Path(__file__).parent / ".token"
    token_file.write_text(TOKEN)
    
    print(f"Server starting on http://localhost:{PORT}")
    print(f"Token: {TOKEN}")
    
    server = http.server.HTTPServer(("localhost", PORT), SkillHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
