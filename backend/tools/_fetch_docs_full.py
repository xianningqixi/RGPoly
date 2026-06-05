#!/usr/bin/env python3
"""Fetch Polymarket docs - try multiple approaches."""
import json, urllib.request, re

# Try the CLOB spec endpoint
urls = [
    "https://docs.polymarket.com/api-reference/rest/",
    "https://docs.polymarket.com/api-reference/rest/order/create-order",
    "https://docs.polymarket.com/api-reference/rest/wallet",
    "https://docs.polymarket.com/developer-docs",
]

for url in urls:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", "replace")
            # Extract text-only content
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text)
            # Look for relevant keywords
            keywords = ["deposit", "maker", "funder", "wallet", "allowance", "proxy"]
            found = {k: text.count(k) for k in keywords}
            print(f"\n=== {url} ({len(html)} chars) ===")
            print(f"Keywords: {found}")
            # Show relevant sections
            for kw in keywords:
                idx = text.lower().find(kw)
                if idx > -1:
                    context = text[max(0,idx-100):idx+200]
                    print(f"  [{kw}]: ...{context.strip()}...")
            print()
    except Exception as e:
        print(f"{url}: {e}")
