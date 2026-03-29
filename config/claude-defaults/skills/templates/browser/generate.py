#!/usr/bin/env python3
"""
{{SKILL_NAME}} - HTML generator for browser skill
"""

import sys
from pathlib import Path

TEMPLATE = '''<!DOCTYPE html>
<html>
<head>
    <title>{{SKILL_NAME}}</title>
    <style>
        body { font-family: system-ui; margin: 20px; background: #1e1e1e; color: #d4d4d4; }
        h1 { color: #569cd6; }
        .container { max-width: 1200px; margin: 0 auto; }
        button { background: #0e639c; color: white; border: none; padding: 8px 16px; cursor: pointer; }
        button:hover { background: #1177bb; }
    </style>
</head>
<body>
    <div class="container">
        <h1>{{SKILL_NAME}}</h1>
        <p>Browser skill UI template</p>
        <button onclick="doAction()">Action</button>
    </div>
    <script>
        const TOKEN = "{{TOKEN}}";
        const API = "http://localhost:8765";
        
        async function doAction() {
            const res = await fetch(API + "/action", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({token: TOKEN})
            });
            const data = await res.json();
            console.log(data);
        }
    </script>
</body>
</html>'''


def main():
    skill_dir = Path(__file__).parent
    
    # Read token from server
    token_file = skill_dir / ".token"
    if token_file.exists():
        token = token_file.read_text().strip()
    else:
        token = "NO_TOKEN"
    
    # Generate HTML
    html = TEMPLATE.replace("{{TOKEN}}", token)
    html = html.replace("{{SKILL_NAME}}", "{{SKILL_NAME}}")
    
    output = skill_dir / "index.html"
    output.write_text(html)
    print(f"Generated: {output}")


if __name__ == "__main__":
    main()
