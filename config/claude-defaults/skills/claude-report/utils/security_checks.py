"""Security pattern detection for Claude Code files."""
import re
import base64
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Suspicious patterns
PATTERNS = {
    'external_url': re.compile(r'https?://(?!localhost|127\.0\.0\.1)[^\s\'"]+', re.I),
    'base64_string': re.compile(r'[A-Za-z0-9+/]{40,}={0,2}'),
    'eval_exec': re.compile(r'\b(eval|exec)\s*\('),
    'encoded_payload': re.compile(r'(atob|btoa|Buffer\.from|base64\.b64decode)\s*\('),
    'shell_injection': re.compile(r'(subprocess|os\.system|os\.popen|shell=True)'),
    'network_calls': re.compile(r'(requests\.|urllib|fetch\(|axios|http\.get)'),
    'file_exfil': re.compile(r'(open\([^)]*["\']w|writeFile|fs\.write)'),
}

def check_file_security(filepath: Path) -> List[Dict[str, Any]]:
    """Check a file for suspicious patterns."""
    flags = []
    
    if not filepath.exists():
        return [{'type': 'missing', 'message': 'Referenced file not found'}]
    
    # Check modification time
    mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
    if datetime.now() - mtime < timedelta(hours=24):
        flags.append({
            'type': 'recent_mod',
            'message': f'Modified {mtime.strftime("%Y-%m-%d %H:%M")}',
            'severity': 'info'
        })
    
    # Read and scan content
    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')
    except Exception as e:
        return [{'type': 'read_error', 'message': str(e), 'severity': 'warning'}]
    
    # Check patterns
    for name, pattern in PATTERNS.items():
        matches = pattern.findall(content)
        if matches:
            # Dedupe and limit
            unique = list(set(matches))[:5]
            flags.append({
                'type': name,
                'message': f'Found: {", ".join(str(m)[:50] for m in unique)}',
                'severity': 'warning' if name in ('eval_exec', 'shell_injection') else 'info',
                'count': len(matches)
            })
    
    return flags

def check_path_location(filepath: Path, expected_roots: List[Path]) -> Dict[str, Any]:
    """Check if file is in expected location."""
    resolved = filepath.resolve()
    for root in expected_roots:
        try:
            resolved.relative_to(root.resolve())
            return None  # In expected location
        except ValueError:
            continue
    
    return {
        'type': 'unexpected_location',
        'message': f'File outside expected paths',
        'severity': 'warning'
    }

def is_base64_valid(s: str) -> bool:
    """Check if string is valid base64."""
    try:
        base64.b64decode(s, validate=True)
        return True
    except Exception:
        return False
