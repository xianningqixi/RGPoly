#!/usr/bin/env python3
"""Find OpenAPI spec from Polymarket docs."""
import json, urllib.request, re

base = "https://docs.polymarket.com"
req = urllib.request.Request(base + "/api-reference/introduction",
    headers={"User-Agent": "Mozilla/5.0"})
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode("utf-8", "replace")
        
        # Find all URLs in the HTML
        urls = re.findall(r'https?://[^\s\"<>]+', html)
        json_urls = [u for u in urls if any(e in u.lower() for e in [".json", ".yaml", ".yml", "openapi", "spec"])]
        print(f"Found {len(json_urls)} potential JSON/Spec URLs:")
        for u in json_urls[:20]:
            print(f"  {u}")
        
        # Find S3 content URLs (Mintlify stores content on S3)
        s3_urls = [u for u in urls if "s3" in u and "content" in u.lower()]
        print(f"\nS3 content URLs: {len(s3_urls)}")
        for u in s3_urls[:5]:
            print(f"  {u}")
        
        # Try fetching mint.json
        try:
            req2 = urllib.request.Request(base + "/mint.json",
                headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req2, timeout=10) as r2:
                data = json.loads(r2.read())
                print(f"\nmint.json keys: {list(data.keys())}")
                if "openapi" in data:
                    print(f"  openapi: {data['openapi']}")
                if "versions" in data:
                    print(f"  versions: {str(data['versions'])[:200]}")
        except Exception as e:
            print(f"\nmint.json: {e}")
        
except Exception as e:
    print(f"Error: {e}")
