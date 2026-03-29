# v1-api

Claude Code skill for Trend Micro Vision One API.

## Features

- **280 API operations** covering all V1 domains
- YAML-driven configuration per operation
- Example API calls and responses for each operation
- Automatic credential scanning during setup

## Installation

```bash
cd .claude/skills/v1-api
python setup.py
```

## Usage

```python
from executor import execute

# List recent alerts
result = execute('list_alerts', {'days': 7, 'severity': 'critical'})

# Get endpoint details
result = execute('get_endpoint', {'endpoint_id': 'abc123'})

# Search logs
result = execute('search_endpoint_logs', {'hours': 24, 'limit': 100})
```

## API Categories

- **Workbench** - Alerts, investigations, insights
- **Endpoints** - Device management, response actions
- **ASRM** - Attack surface risk management
- **Cloud** - AWS, Azure, GCP account management
- **Container Security** - K8s, ECS clusters
- **Threat Intelligence** - IOCs, reports, feeds
- **Response** - Isolate, scan, collect files

## Configuration

Create `.env` with your Vision One API key:

```
V1_API_KEY=your-api-key-here
V1_REGION=us
```

## Repository

https://github.com/${TMEMU_ACCOUNT}/skill-v1-api

## License

Private - internal use only.
