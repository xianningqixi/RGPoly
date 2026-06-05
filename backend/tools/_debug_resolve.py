#!/usr/bin/env python3
"""Test resolve_token_id logic against a real Gamma market."""
import json, urllib.request, sys

sys.stdout.reconfigure(encoding="utf-8")

def fetch_market(slug):
    url = "https://gamma-api.polymarket.com/markets?slug=" + urllib.request.quote(slug) + "&limit=1"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    return data[0] if data else None

def _parse_json_field(val):
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
    return val

# Test a few slugs that the executor should handle
test_slugs = [
    ("bitcoin-above-70k-on-june-2-2026", "Yes"),
    ("bitcoin-above-66k-on-june-3-2026", "No"),
    ("will-the-price-of-bitcoin-be-less-than-68000-on-june-2-2026", "Yes"),
    ("bitcoin-above-70k-on-june-1-2026", "Yes"),
]

for slug, desired_outcome in test_slugs:
    print(f"\n=== {slug} → outcome: {desired_outcome} ===")
    market = fetch_market(slug)
    if not market:
        print("  [NO MARKET]")
        continue

    closed = market.get("closed", "?")
    print(f"  closed={closed}")

    outcomes_raw = _parse_json_field(market.get("outcomes", []))
    print(f"  outcomes (type={type(outcomes_raw).__name__}): {str(outcomes_raw)[:100]}")

    clob_ids_raw = _parse_json_field(market.get("clobTokenIds", market.get("clobtokenids", [])))
    print(f"  clobTokenIds (type={type(clob_ids_raw).__name__}): {str(clob_ids_raw)[:100]}")

    outcomes_out = _parse_json_field(market.get("outcomes_out", {}))
    print(f"  outcomes_out: {str(outcomes_out)[:100]}")

    target = desired_outcome.strip().lower()
    for i, outcome in enumerate(outcomes_raw):
        if isinstance(outcome, dict):
            name = (outcome.get("outcome") or outcome.get("name") or "").strip().lower()
        else:
            name = str(outcome).strip().lower()
        token_id = None
        if i < len(clob_ids_raw) and clob_ids_raw[i]:
            token_id = str(clob_ids_raw[i])
        print(f"  outcome[{i}]: '{name}' → token_id={'...' + token_id[-12:] if token_id else 'NONE'}")

