#!/usr/bin/env python3
"""Fetch Polymarket API docs."""
import json, urllib.request, re

urls = [
    "https://docs.polymarket.com/api-reference/introduction",
    "https://docs.polymarket.com/api-reference",
    "https://docs.polymarket.com/",
]

for url in urls:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", errors="replace")
            print(f"=== {url} ===")
            print(f"Status: {r.status}")
            content_type = r.headers.get("Content-Type", "")
            print(f"Type: {content_type}")
            print(f"Size: {len(html)} chars")
            print(f"First 2000 chars:")
            print(html[:2000])
            print()
    except Exception as e:
        print(f"{url}: {e}")
        print()
