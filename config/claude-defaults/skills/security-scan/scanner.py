#!/usr/bin/env python3
"""
Security Scanner - Scan code for vulnerabilities, malware, and sensitive data.
Replaces suspicious URLs, public IPs, and domains with safe placeholders.
"""
import os
import re
import json
import argparse
from datetime import datetime
from pathlib import Path

# Patterns to detect
VULN_PATTERNS = {
    "eval/exec": r"\b(eval|exec)\s*\(",
    "subprocess": r"\bsubprocess\.(call|run|Popen|check_output)",
    "os.system": r"\bos\.system\s*\(",
    "shell=True": r"shell\s*=\s*True",
    "pickle": r"\bpickle\.(load|loads)\s*\(",
    "yaml.unsafe_load": r"yaml\.(load|unsafe_load)\s*\(",
    "requests.get/post": r"\brequests\.(get|post|put|delete)\s*\(",
    "urllib": r"\burllib\.(request|urlopen)",
    "socket": r"\bsocket\.(socket|connect)",
    "base64.decode": r"\bbase64\.(b64decode|decodebytes)",
    "cryptography": r"\b(AES|DES|RSA|encrypt|decrypt)\b",
    "sql_injection": r"(execute|cursor)\s*\(\s*[\"'].*%s",
    "command_injection": r"(subprocess|os\.system|shell)\s*\(.*\+",
}

SENSITIVE_PATTERNS = {
    "hardcoded_password": r"(password|passwd|pwd)\s*=\s*['\"][^'\"]{4,}['\"]",
    "hardcoded_secret": r"(secret|api_key|apikey|token|bearer)\s*=\s*['\"][^'\"]{8,}['\"]",
    "aws_key": r"AKIA[0-9A-Z]{16}",
    "private_key": r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
}

# Safe domains to preserve (documentation, major platforms, licenses)
SAFE_DOMAINS = {
    # Documentation
    "docs.python.org", "docs.ansible.com", "docs.docker.com", "docs.aws.amazon.com",
    "docs.microsoft.com", "learn.microsoft.com", "developer.mozilla.org",
    "kubernetes.io", "terraform.io", "readthedocs.io", "readthedocs.org",
    # Code platforms
    "github.com", "gitlab.com", "bitbucket.org", "codeberg.org",
    "raw.githubusercontent.com", "gist.github.com",
    # Package registries
    "pypi.org", "npmjs.com", "registry.npmjs.org", "crates.io", "rubygems.org",
    "hub.docker.com", "gcr.io", "quay.io",
    # Major vendors
    "google.com", "googleapis.com", "microsoft.com", "azure.com",
    "amazon.com", "amazonaws.com", "aws.amazon.com",
    "apple.com", "oracle.com", "redhat.com", "ubuntu.com", "debian.org",
    # Licenses and standards
    "gnu.org", "opensource.org", "creativecommons.org", "spdx.org",
    "ietf.org", "w3.org", "json.org", "yaml.org",
    # Stack Overflow and forums
    "stackoverflow.com", "stackexchange.com", "serverfault.com",
    # Cloud providers
    "cloudflare.com", "digitalocean.com", "linode.com", "heroku.com",
    # Security/crypto
    "letsencrypt.org", "hashicorp.com",
    # Other common safe domains
    "wikipedia.org", "wikimedia.org", "archive.org",
    "example.com", "example.org", "example.net",  # RFC 2606 reserved
}

# Suspicious TLDs that are commonly used for malware/phishing
SUSPICIOUS_TLDS = {"ru", "cn", "xyz", "top", "tk", "ml", "ga", "cf", "gq", "pw", "cc", "su", "ws"}

def is_safe_domain(url: str) -> bool:
    """Check if URL domain is in the safe list"""
    import re
    match = re.match(r"https?://([^/]+)", url)
    if not match:
        return False
    domain = match.group(1).lower()
    # Check exact match or subdomain match
    for safe in SAFE_DOMAINS:
        if domain == safe or domain.endswith("." + safe):
            return True
    return False

def has_suspicious_tld(url: str) -> bool:
    """Check if URL has a suspicious TLD"""
    import re
    match = re.match(r"https?://[^/]+\.([a-z]+)(?:/|$)", url.lower())
    if match:
        return match.group(1) in SUSPICIOUS_TLDS
    return False

# Patterns to replace
REPLACE_PATTERNS = {
    # Suspicious TLD URLs -> redacted
    "suspicious_url": {
        "pattern": r"https?://([a-zA-Z0-9][-a-zA-Z0-9]*\.)+(?:ru|cn|xyz|top|tk|ml|ga|cf|gq|pw|cc|su|ws)(/[^\s\"']*)?",
        "replacement": "[UNKNOWN_URL]",
    },
}

# Audit log for redactions
AUDIT_LOG = "redaction_audit.log"

def log_redaction(file_path: str, redaction_type: str, original: str, replacement: str):
    """Log redaction with UTC timestamp for auditing"""
    from datetime import datetime, timezone
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(f"{timestamp}|{redaction_type}|{file_path}|{original}|{replacement}\n")

def is_public_ip(ip_str: str) -> bool:
    """Check if IP is public (not private, localhost, or version number)"""
    parts = ip_str.split('.')
    if len(parts) != 4:
        return False
    try:
        octets = [int(p) for p in parts]
    except ValueError:
        return False
    # Check valid range
    if not all(0 <= o <= 255 for o in octets):
        return False
    first = octets[0]
    # Skip version numbers (first octet 0-9)
    if first < 10:
        return False
    # Skip private ranges
    if first == 10:  # 10.0.0.0/8
        return False
    if first == 127:  # localhost
        return False
    if first == 172 and 16 <= octets[1] <= 31:  # 172.16.0.0/12
        return False
    if first == 192 and octets[1] == 168:  # 192.168.0.0/16
        return False
    if first == 169 and octets[1] == 254:  # link-local
        return False
    if first >= 224:  # multicast and reserved
        return False
    return True

# Simple IP pattern - filtering done in is_public_ip()
IP_PATTERN = re.compile(r'(?<![.\d])(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?![.\d])')

# File extensions to scan
SCAN_EXTENSIONS = {
    ".py", ".js", ".ts", ".go", ".rb", ".php", ".java", ".scala", ".kt",
    ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd",
    ".yaml", ".yml", ".json", ".xml", ".toml", ".ini", ".cfg", ".conf",
    ".md", ".txt", ".rst",
    ".html", ".htm", ".css", ".sql",
    ".dockerfile", ".tf", ".hcl",
}

# Directories to skip
SKIP_DIRS = {
    ".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".eggs", "*.egg-info", ".tox", ".pytest_cache",
}


class SecurityScanner:
    def __init__(self, target_path: str, fix: bool = False, log_file: str = None):
        self.target_path = Path(target_path)
        self.fix = fix
        self.log_file = log_file or f"security_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self.findings = []
        self.replacements = []
        self.stats = {"files_scanned": 0, "findings": 0, "replacements": 0}

    def log(self, message: str):
        """Log to console and file"""
        print(message)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} {message}\n")

    def should_scan_file(self, path: Path) -> bool:
        """Check if file should be scanned"""
        if path.suffix.lower() not in SCAN_EXTENSIONS:
            # Check for extensionless files like Dockerfile, Makefile
            if path.name.lower() not in {"dockerfile", "makefile", "jenkinsfile", "vagrantfile"}:
                return False
        return True

    def should_skip_dir(self, dirname: str) -> bool:
        """Check if directory should be skipped"""
        return dirname in SKIP_DIRS or dirname.startswith(".")

    def scan_file(self, file_path: Path) -> tuple:
        """Scan a single file for vulnerabilities and sensitive data"""
        findings = []
        replacements = []

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                original_content = f.read()
                lines = original_content.split("\n")
        except Exception as e:
            return [], [], None

        modified_content = original_content

        # Check vulnerability patterns
        for i, line in enumerate(lines, 1):
            for name, pattern in VULN_PATTERNS.items():
                if re.search(pattern, line, re.IGNORECASE):
                    snippet = line.strip()[:100]
                    findings.append({
                        "file": str(file_path),
                        "line": i,
                        "type": "vulnerability",
                        "category": name,
                        "snippet": snippet,
                    })

            # Check sensitive patterns
            for name, pattern in SENSITIVE_PATTERNS.items():
                if re.search(pattern, line, re.IGNORECASE):
                    # Mask the actual value
                    snippet = re.sub(r"(['\"])[^'\"]+\1", r"\1***MASKED***\1", line.strip()[:100])
                    findings.append({
                        "file": str(file_path),
                        "line": i,
                        "type": "sensitive",
                        "category": name,
                        "snippet": snippet,
                    })

        # Find and replace suspicious URL patterns
        for name, config in REPLACE_PATTERNS.items():
            matches = list(re.finditer(config["pattern"], modified_content))
            for match in matches:
                original = match.group(0)
                replacement = config["replacement"]

                replacements.append({
                    "file": str(file_path),
                    "type": name,
                    "original": original,
                    "replacement": replacement,
                })

                if self.fix:
                    modified_content = modified_content.replace(original, replacement, 1)
                    log_redaction(str(file_path), name, original, replacement)

        # Find and replace public IP addresses
        for match in IP_PATTERN.finditer(modified_content):
            ip = match.group(1)
            if is_public_ip(ip):
                replacement = "[PUBLIC_IP]"
                replacements.append({
                    "file": str(file_path),
                    "type": "public_ip",
                    "original": ip,
                    "replacement": replacement,
                })
                if self.fix:
                    modified_content = modified_content.replace(ip, replacement, 1)
                    log_redaction(str(file_path), "public_ip", ip, replacement)

        return findings, replacements, modified_content if self.fix else None

    def scan(self) -> dict:
        """Scan target path recursively"""
        self.log(f"=" * 60)
        self.log(f"Security Scan Started: {self.target_path}")
        self.log(f"Mode: {'FIX (replacing)' if self.fix else 'SCAN ONLY'}")
        self.log(f"Log file: {self.log_file}")
        self.log(f"=" * 60)

        if self.target_path.is_file():
            files_to_scan = [self.target_path]
        else:
            files_to_scan = []
            for root, dirs, files in os.walk(self.target_path):
                # Skip directories
                dirs[:] = [d for d in dirs if not self.should_skip_dir(d)]
                for f in files:
                    file_path = Path(root) / f
                    if self.should_scan_file(file_path):
                        files_to_scan.append(file_path)

        self.log(f"\nScanning {len(files_to_scan)} files...")

        for file_path in files_to_scan:
            self.stats["files_scanned"] += 1
            findings, replacements, modified_content = self.scan_file(file_path)

            if findings:
                self.findings.extend(findings)
                self.stats["findings"] += len(findings)
                for f in findings:
                    self.log(f"\n[{f['type'].upper()}] {f['file']}:{f['line']}")
                    self.log(f"  Category: {f['category']}")
                    self.log(f"  Snippet: {f['snippet']}")

            if replacements:
                self.replacements.extend(replacements)
                self.stats["replacements"] += len(replacements)
                for r in replacements:
                    self.log(f"\n[REPLACE] {r['file']}")
                    self.log(f"  Type: {r['type']}")
                    self.log(f"  Original: {r['original']}")
                    self.log(f"  Replacement: {r['replacement']}")

            # Write modified content if fixing
            if self.fix and modified_content:
                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(modified_content)
                    self.log(f"  [FIXED] {file_path}")
                except Exception as e:
                    self.log(f"  [ERROR] Failed to write {file_path}: {e}")

        # Summary
        self.log(f"\n{'=' * 60}")
        self.log("SCAN SUMMARY")
        self.log(f"{'=' * 60}")
        self.log(f"Files scanned: {self.stats['files_scanned']}")
        self.log(f"Findings: {self.stats['findings']}")
        self.log(f"Replacements: {self.stats['replacements']}")

        if self.findings:
            self.log("\nFindings by category:")
            categories = {}
            for f in self.findings:
                cat = f["category"]
                categories[cat] = categories.get(cat, 0) + 1
            for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
                self.log(f"  {cat}: {count}")

        if self.replacements:
            self.log("\nReplacements by type:")
            types = {}
            for r in self.replacements:
                t = r["type"]
                types[t] = types.get(t, 0) + 1
            for t, count in sorted(types.items(), key=lambda x: -x[1]):
                self.log(f"  {t}: {count}")

        return {
            "stats": self.stats,
            "findings": self.findings,
            "replacements": self.replacements,
            "log_file": self.log_file,
        }


def main():
    parser = argparse.ArgumentParser(description="Security Scanner")
    parser.add_argument("path", help="Path to scan (file or directory)")
    parser.add_argument("--fix", action="store_true", help="Replace suspicious patterns")
    parser.add_argument("--log", help="Log file path")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    scanner = SecurityScanner(args.path, fix=args.fix, log_file=args.log)
    result = scanner.scan()

    if args.json:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
