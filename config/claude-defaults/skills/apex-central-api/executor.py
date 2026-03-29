#!/usr/bin/env python3
"""
Apex Central API Executor

Handles authentication and API calls to Trend Micro Apex Central.
Uses JWT tokens generated from Application ID and API Key.
"""

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def load_env():
    """Load environment variables from .env file if exists."""
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"'))

load_env()


class ApexCentralAPI:
    """Apex Central API client with JWT authentication."""

    def __init__(self, base_url=None, app_id=None, api_key=None):
        self.base_url = base_url or os.environ.get("APEX_CENTRAL_URL", "")
        self.app_id = app_id or os.environ.get("APEX_CENTRAL_APP_ID", "")
        self.api_key = api_key or os.environ.get("APEX_CENTRAL_API_KEY", "")

        if not all([self.base_url, self.app_id, self.api_key]):
            raise ValueError(
                "Missing Apex Central credentials. Set environment variables:\n"
                "  APEX_CENTRAL_URL\n"
                "  APEX_CENTRAL_APP_ID\n"
                "  APEX_CENTRAL_API_KEY"
            )

    def _create_checksum(self, http_method, raw_url, headers, request_body):
        """Create HMAC-SHA256 checksum for request."""
        string_to_hash = (
            http_method.upper() + "|" +
            raw_url.lower() + "|" +
            headers.get("x-posix-time", "") + "|" +
            (request_body if request_body else "")
        )
        return base64.b64encode(
            hmac.new(
                self.api_key.encode("utf-8"),
                string_to_hash.encode("utf-8"),
                hashlib.sha256
            ).digest()
        ).decode("utf-8")

    def _create_jwt(self, http_method, raw_url, headers, request_body=None):
        """Create JWT token for authentication."""
        # JWT Header
        jwt_header = {"typ": "JWT", "alg": "HS256"}
        jwt_header_b64 = base64.urlsafe_b64encode(
            json.dumps(jwt_header).encode("utf-8")
        ).decode("utf-8").rstrip("=")

        # JWT Payload
        checksum = self._create_checksum(http_method, raw_url, headers, request_body)
        jwt_payload = {
            "appid": self.app_id,
            "iat": int(time.time()),
            "version": "V1",
            "checksum": checksum
        }
        jwt_payload_b64 = base64.urlsafe_b64encode(
            json.dumps(jwt_payload).encode("utf-8")
        ).decode("utf-8").rstrip("=")

        # JWT Signature
        signing_input = f"{jwt_header_b64}.{jwt_payload_b64}"
        signature = base64.urlsafe_b64encode(
            hmac.new(
                self.api_key.encode("utf-8"),
                signing_input.encode("utf-8"),
                hashlib.sha256
            ).digest()
        ).decode("utf-8").rstrip("=")

        return f"{jwt_header_b64}.{jwt_payload_b64}.{signature}"

    def _request(self, method, endpoint, data=None, params=None):
        """Make authenticated API request."""
        # Build URL
        url = urljoin(self.base_url, endpoint)
        if params:
            url += "?" + "&".join(f"{k}={v}" for k, v in params.items())

        # Parse URL for checksum
        parsed = urlparse(url)
        raw_url = parsed.path
        if parsed.query:
            raw_url += "?" + parsed.query

        # Prepare headers
        posix_time = str(int(time.time()))
        headers = {
            "Content-Type": "application/json;charset=utf-8",
            "x-posix-time": posix_time
        }

        # Prepare body
        body = json.dumps(data) if data else None

        # Create JWT
        jwt = self._create_jwt(method, raw_url, headers, body)
        headers["Authorization"] = f"Bearer {jwt}"

        # Make request
        req = Request(url, method=method, headers=headers)
        if body:
            req.data = body.encode("utf-8")

        try:
            with urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            raise Exception(f"API Error {e.code}: {error_body}")
        except URLError as e:
            raise Exception(f"Connection Error: {e.reason}")

    # === Agent Operations ===

    def list_agents(self, limit=100):
        """List all Security Agents."""
        return self._request("GET", "/WebApp/API/AgentResource/ProductAgents", params={"top": limit})

    def get_agent(self, guid):
        """Get specific agent by GUID."""
        return self._request("GET", f"/WebApp/API/AgentResource/ProductAgents/{guid}")

    def isolate_endpoint(self, guid, reason="Security investigation"):
        """Isolate an endpoint from the network."""
        return self._request("POST", "/WebApp/API/SuspiciousObjects/ActionRequest/Isolate", data={
            "entity_id": guid,
            "description": reason
        })

    def restore_endpoint(self, guid):
        """Restore an isolated endpoint."""
        return self._request("POST", "/WebApp/API/SuspiciousObjects/ActionRequest/RestoreIsolation", data={
            "entity_id": guid
        })

    def scan_endpoint(self, guid, scan_type="quick"):
        """Trigger scan on endpoint."""
        return self._request("POST", "/WebApp/API/AgentResource/ProductAgents/Scan", data={
            "entity_id": guid,
            "scan_type": scan_type
        })

    # === Server Operations ===

    def list_servers(self, limit=100):
        """List managed servers."""
        return self._request("GET", "/WebApp/API/ServerResource/ProductServers", params={"top": limit})

    def get_server(self, server_id):
        """Get specific server."""
        return self._request("GET", f"/WebApp/API/ServerResource/ProductServers/{server_id}")

    # === Suspicious Objects ===

    def list_suspicious_objects(self, obj_type=None, limit=100):
        """List suspicious objects (IOCs)."""
        params = {"top": limit}
        if obj_type:
            params["type"] = obj_type
        return self._request("GET", "/WebApp/API/SuspiciousObjects/UserDefinedSO", params=params)

    def add_suspicious_object(self, obj_type, value, description="", scan_action="log", notes=""):
        """Add suspicious object to blocklist."""
        return self._request("POST", "/WebApp/API/SuspiciousObjects/UserDefinedSO", data={
            "type": obj_type,
            "content": value,
            "description": description,
            "scan_action": scan_action,
            "notes": notes
        })

    def delete_suspicious_object(self, obj_type, value):
        """Remove suspicious object from list."""
        return self._request("DELETE", "/WebApp/API/SuspiciousObjects/UserDefinedSO", data={
            "type": obj_type,
            "content": value
        })

    # === Logs ===

    def query_logs(self, log_type="Detection", start_time=None, end_time=None, limit=100):
        """Query security logs."""
        params = {"type": log_type, "top": limit}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        return self._request("GET", "/WebApp/API/LogResource/Logs", params=params)

    # === Investigations ===

    def create_investigation(self, name, description="", iocs=None):
        """Create new investigation task."""
        data = {"name": name, "description": description}
        if iocs:
            data["indicators"] = iocs
        return self._request("POST", "/WebApp/API/InvestigationResource/Investigations", data=data)

    def list_investigations(self, limit=100):
        """List investigation tasks."""
        return self._request("GET", "/WebApp/API/InvestigationResource/Investigations", params={"top": limit})

    def get_investigation(self, investigation_id):
        """Get investigation details."""
        return self._request("GET", f"/WebApp/API/InvestigationResource/Investigations/{investigation_id}")


def main():
    """Command-line interface."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python executor.py <operation> [args...]")
        print("\nOperations:")
        print("  list-agents              List all agents")
        print("  get-agent <guid>         Get agent details")
        print("  isolate <guid>           Isolate endpoint")
        print("  restore <guid>           Restore endpoint")
        print("  scan <guid>              Scan endpoint")
        print("  list-servers             List servers")
        print("  list-suspicious          List suspicious objects")
        print("  add-suspicious <t> <v>   Add suspicious object")
        print("  query-logs [type]        Query logs")
        return 1

    try:
        api = ApexCentralAPI()
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    op = sys.argv[1].lower().replace("_", "-")

    try:
        if op == "list-agents":
            result = api.list_agents()
        elif op == "get-agent" and len(sys.argv) > 2:
            result = api.get_agent(sys.argv[2])
        elif op == "isolate" and len(sys.argv) > 2:
            result = api.isolate_endpoint(sys.argv[2])
        elif op == "restore" and len(sys.argv) > 2:
            result = api.restore_endpoint(sys.argv[2])
        elif op == "scan" and len(sys.argv) > 2:
            result = api.scan_endpoint(sys.argv[2])
        elif op == "list-servers":
            result = api.list_servers()
        elif op == "list-suspicious":
            result = api.list_suspicious_objects()
        elif op == "add-suspicious" and len(sys.argv) > 3:
            result = api.add_suspicious_object(sys.argv[2], sys.argv[3])
        elif op == "query-logs":
            log_type = sys.argv[2] if len(sys.argv) > 2 else "Detection"
            result = api.query_logs(log_type)
        else:
            print(f"Unknown operation: {op}")
            return 1

        print(json.dumps(result, indent=2))
        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
