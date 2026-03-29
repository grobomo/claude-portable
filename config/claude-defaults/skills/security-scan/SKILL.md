---



name: security-scan
description: Scan code for vulnerabilities, malware, and sensitive data. Optionally replace suspicious URLs/IPs with safe placeholders.
keywords:
  - security
  - vulnerability
  - malware
  - sensitive
  - sanitize
  - vulnerabilities


---

# Security Scanner Skill

Comprehensive security scanning for codebases with optional auto-fix capabilities.

## Features

- **Vulnerability Detection**: eval/exec, subprocess, os.system, shell=True, pickle, yaml.load, SQL/command injection
- **Sensitive Data Detection**: hardcoded passwords, API keys, AWS keys, private keys
- **URL Sanitization**: Replaces suspicious TLD URLs (.ru, .cn, .xyz, etc.) with safe placeholders
- **IP Sanitization**: Replaces public IP addresses with private 10.0.0.x addresses
- **Comprehensive Logging**: All detections and replacements logged with timestamps

## Usage

User says: `/security-scan` or "scan for vulnerabilities" or "check for malware"

Arguments:
- `<path>` - File or directory to scan (required)
- `--fix` - Replace suspicious patterns (optional)

## Workflow

### Step 1: Run in microsandbox (recommended for untrusted code)

```bash
# Start microsandbox server if not running
wsl -d Ubuntu -- bash -c "msb server start --dev" &
sleep 3

# Create sandbox
curl -s -X POST http://localhost:5555/mcp -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"sandbox_start","arguments":{"sandbox":"security-scan","namespace":"scan","config":{"image":"microsandbox/python"}}},"id":1}'

# Clone repo into sandbox
curl -s -X POST http://localhost:5555/mcp -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"sandbox_run_command","arguments":{"sandbox":"security-scan","namespace":"scan","command":"git","args":["clone","--depth","1","<REPO_URL>","/tmp/repo"]}},"id":1}'

# Run scanner
curl -s -X POST http://localhost:5555/mcp -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"sandbox_run_command","arguments":{"sandbox":"security-scan","namespace":"scan","command":"python3","args":["/path/to/scanner.py","/tmp/repo","--fix"]}},"id":1}'

# Stop sandbox when done
curl -s -X POST http://localhost:5555/mcp -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"sandbox_stop","arguments":{"sandbox":"security-scan","namespace":"scan"}},"id":1}'
```

### Step 2: Run locally (trusted code only)

```bash
# Scan only (no changes)
python .claude/skills/security-scan/scanner.py /path/to/code

# Scan and fix (replace suspicious URLs/IPs)
python .claude/skills/security-scan/scanner.py /path/to/code --fix

# With custom log file
python .claude/skills/security-scan/scanner.py /path/to/code --fix --log scan_results.log

# JSON output
python .claude/skills/security-scan/scanner.py /path/to/code --json
```

## What Gets Detected

### Vulnerabilities
| Pattern | Risk | Example |
|---------|------|---------|
| eval/exec | Code injection | `eval(user_input)` |
| subprocess | Command execution | `subprocess.call(cmd)` |
| os.system | Command execution | `os.system(cmd)` |
| shell=True | Shell injection | `subprocess.run(cmd, shell=True)` |
| pickle.load | Arbitrary code exec | `pickle.load(file)` |
| yaml.load | Code execution | `yaml.load(data)` |
| SQL injection | Data breach | `cursor.execute("SELECT * WHERE id=" + id)` |

### Sensitive Data
| Pattern | Example |
|---------|---------|
| Hardcoded password | `password = "secret123"` |
| API keys | `api_key = "sk-xxxxx"` |
| AWS access keys | `AKIAIOSFODNN7EXAMPLE` |
| Private keys | `-----BEGIN RSA PRIVATE KEY-----` |

## What Gets Replaced (with --fix)

| Type | Original | Replacement |
|------|----------|-------------|
| Suspicious URL | `http://malware.ru/payload` | `https://example.com/payload` |
| Public URL | `https://api.external.com/v1` | `https://example.com/v1` |
| Public IP | `203.0.113.50` | `10.0.0.1` |

Private IPs (10.x, 172.16-31.x, 192.168.x) and localhost are preserved.

## Log File Format

```
2025-01-04T12:00:00 ============================================================
2025-01-04T12:00:00 Security Scan Started: /path/to/code
2025-01-04T12:00:00 Mode: FIX (replacing)
2025-01-04T12:00:00 ============================================================

2025-01-04T12:00:01 [VULNERABILITY] /path/to/file.py:42
2025-01-04T12:00:01   Category: eval/exec
2025-01-04T12:00:01   Snippet: eval(user_input)

2025-01-04T12:00:01 [REPLACE] /path/to/config.yaml
2025-01-04T12:00:01   Type: suspicious_url
2025-01-04T12:00:01   Original: http://download.malware.ru/script.sh
2025-01-04T12:00:01   Replacement: https://example.com/script.sh
```

## Examples

```bash
# Scan a cloned GitHub repo
/security-scan ~/repos/suspicious-project

# Scan and sanitize before committing
/security-scan ./src --fix

# Scan specific file
/security-scan ./config/database.yaml
```

## Files

- `scanner.py` - Main scanner script (standalone, no dependencies)
- `SKILL.md` - This documentation
