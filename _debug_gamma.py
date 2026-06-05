#!/usr/bin/env python3
import json, urllib.request, sys, time

sys.stdout.reconfigure(encoding="utf-8")

# Test several slugs: expired, today, future
slugs = [
    "bitcoin-above-78k-on-may-22-2026",
    "bitcoin-above-70k-on-june-2-2026",
    "bitcoin-above-66k-on-june-3-2026",
    "will-the-price-of-bitcoin-be-less-than-68000-on-june-2-2026",
]

for slug in slugs:
    print(f"\n=== {slug} ===")
    url = "https://gamma-api.polymarket.com/markets?slug=" + urllib.request.quote(slug) + "&limit=1"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        print(f"  took {time.time()-t0:.2f}s")
        if not data:
            print("  [NO RESULTS]")
            continue
        m = data[0]
        print(f"  title: {m.get('title','?')}")
        print(f"  closed: {m.get('closed','?')}")
        print(f"  end_date_iso: {m.get('end_date_iso','?')}")
        outcomes = m.get("outcomes", [])
        print(f"  outcomes (type={type(outcomes).__name__}): {str(outcomes)[:200]}")
        print(f"  token_ids: {json.dumps(m.get('token_ids',[]))}")
        print(f"  outcomes_zid: {json.dumps(m.get('outcomes_zid',[]))}")
        print(f"  outcomes_out: {json.dumps(m.get('outcomes_out',{}))}")
        
        for k in ["condition_id", "neg_risk_out", "neg_risk_mirror", "clobTokenIds", "clobtokenids"]:
            v = m.get(k)
            if v:
                print(f"  {k}: {json.dumps(v)[:200]}")
                
    except Exception as e:
        print(f"  ERROR: {e}")
