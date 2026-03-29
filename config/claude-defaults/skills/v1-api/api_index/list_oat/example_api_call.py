#!/usr/bin/env python3
"""
list_oat - List Observed Attack Techniques

IMPORTANT: This API uses TMV1-Filter HEADER for filtering, NOT query params.
           Using filter as query param returns 400 "Unknown field".
"""

import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# --- CONFIG ---
BASE_URL = "https://api.xdr.trendmicro.com"
API_KEY = os.environ.get("V1_API_KEY")

# --- REQUEST ---
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    # Filter goes in HEADER, not query params
    "TMV1-Filter": "riskLevel eq 'high'"  # critical, high, medium, low
}

end = datetime.utcnow()
start = end - timedelta(days=7)

params = {
    # Date params are different from other APIs
    "detectedStartDateTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "detectedEndDateTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    # Pagination uses 'top' with enum values [50, 100, 200]
    "top": "50"
}

# --- EXECUTE ---
response = requests.get(
    f"{BASE_URL}/v3.0/oat/detections",
    headers=headers,
    params=params
)

print(f"Status: {response.status_code}")
print(f"Items: {len(response.json().get('items', []))}")

# --- EXAMPLE OUTPUT ---
# Status: 200
# Items: 1
# See response.json for full response structure
