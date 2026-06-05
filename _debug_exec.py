#!/usr/bin/env python3
import csv, json, urllib.request, time, sys

sys.stdout.reconfigure(encoding="utf-8")

path = r"C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket\btc_directional_trade_audit.csv"
rows = list(csv.DictReader(open(path, encoding="utf-8")))
open_trades = [
    r for r in rows
    if r.get("status", "").strip().upper() == "OPEN"
    and r.get("strategy", "").startswith("btc_directional_copy")
]
print(f"Total OPEN & btc_directional_copy: {len(open_trades)}")

t = open_trades[0]
slug = t["slug"]
token_id = t.get("token_id", "").strip()
print(f"\n--- First trade ---")
print(f"  strategy: {t['strategy']}")
print(f"  slug: {slug}")
print(f"  outcome: {t['outcome']}")
print(f"  stake: {t['stake']}")
print(f"  token_id: {token_id}")

# Try Gamma API
if not token_id:
    print("\nNo token_id - fetching from Gamma...")
    start = time.time()
    try:
        url = (
            "https://gamma-api.polymarket.com/markets?slug="
            + urllib.request.quote(slug)
            + "&limit=1"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            print(f"  Gamma OK in {time.time()-start:.1f}s - {len(data)} markets")
            if data:
                m = data[0]
                print(f"  Market title: {m.get('title','?')}")
                print(f"  Closed: {m.get('closed','?')}")
                print(f"  Outcomes: {len(m.get('outcomes',[]))}")
                for o in m.get("outcomes", []):
                    print(f"    - {o.get('outcome','')} -> token_id={o.get('token_id','')}")
    except Exception as e:
        print(f"  Gamma FAILED after {time.time()-start:.1f}s: {e}")
else:
    print("\nHas token_id - checking CLOB...")
    # Try CLOB
    start = time.time()
    try:
        url = "https://clob.polymarket.com/book?token_id=" + token_id
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            book = json.loads(resp.read())
            print(f"  CLOB OK in {time.time()-start:.1f}s")
            if book.get("asks"):
                print(f"  Best ask: {book['asks'][0]['price']}")
            else:
                print(f"  No asks - book: {str(book)[:200]}")
    except Exception as e:
        print(f"  CLOB FAILED after {time.time()-start:.1f}s: {e}")

# Count how many have token_ids
with_token = sum(1 for t in open_trades if t.get("token_id", "").strip())
print(f"\nOPEN trades with token_id: {with_token}/{len(open_trades)}")
