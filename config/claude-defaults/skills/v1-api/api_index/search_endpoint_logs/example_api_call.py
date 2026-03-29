#!/usr/bin/env python3
"""
search_endpoint_logs - Search endpoint activity logs (process, file, network events)

Run this script to test the API directly.
"""

import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

BASE_URL = "https://api.xdr.trendmicro.com"
API_KEY = os.environ.get("V1_API_KEY")

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    # "TMV1-Filter": "field eq 'value'",  # Uncomment to filter
}

end = datetime.utcnow()
start = end - timedelta(hours=7)

params = {
    "startDateTime": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "endDateTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "top": "50",}

response = requests.get(
    f"{BASE_URL}/v3.0/search/endpointActivities",
    headers=headers,
    params=params
)

print(f"Status: {response.status_code}")
if response.status_code == 200:
    import json
    data = response.json()
    items = data.get("items", data.get("data", []))
    print(f"Items: {len(items) if isinstance(items, list) else 'N/A'}")
else:
    print(f"Error: {response.text[:500]}")
