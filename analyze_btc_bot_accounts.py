#!/usr/bin/env python3
"""Analyze public Polymarket accounts for BTC Up/Down bot behavior."""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any


PROFILE_URLS = [
    "https://polymarket.com/@0x8dxd?r=ecosystem",
    "https://polymarket.com/profile/0xf705fa045201391d9632b7f3cde06a5e24453ca7?r=ecosystem",
    "https://polymarket.com/@k9q2mx4l8a7zp3r?r=ecosystem",
    "https://polymarket.com/@justdance?r=ecosystem",
    "https://polymarket.com/@0x1979ae6b7e6534de9c4539d0c205e582ca637c9d-1769439463256?r=ecosystem",
]


def http_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45) as response:
        return response.read().decode("utf-8", "replace")


def http_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def profile_next_data(url: str) -> dict[str, Any]:
    html = http_text(url)
    start = html.find("__NEXT_DATA__")
    if start < 0:
        raise RuntimeError(f"__NEXT_DATA__ not found for {url}")
    start = html.find(">", start) + 1
    end = html.find("</script>", start)
    return json.loads(html[start:end])


def queries(next_data: dict[str, Any]) -> list[dict[str, Any]]:
    return next_data["props"]["pageProps"]["dehydratedState"]["queries"]


def find_profile(next_data: dict[str, Any]) -> dict[str, Any]:
    for query in queries(next_data):
        key = str(query.get("queryKey"))
        data = query.get("state", {}).get("data")
        if "/api/profile/userData" in key and isinstance(data, dict) and data.get("proxyWallet"):
            return data
    raise RuntimeError("profile userData query not found")


def find_volume(next_data: dict[str, Any]) -> dict[str, Any]:
    for query in queries(next_data):
        key = str(query.get("queryKey"))
        data = query.get("state", {}).get("data")
        if "/api/profile/volume" in key and isinstance(data, dict):
            return data
    return {}


def find_stats(next_data: dict[str, Any]) -> dict[str, Any]:
    for query in queries(next_data):
        key = str(query.get("queryKey"))
        data = query.get("state", {}).get("data")
        if "user-stats" in key and isinstance(data, dict):
            return data
    return {}


def fetch_activity(wallet: str, limit: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    offset = 0
    while len(out) < limit:
        batch_size = min(500, limit - len(out))
        query = urllib.parse.urlencode({"user": wallet, "limit": batch_size, "offset": offset})
        data = http_json(f"https://data-api.polymarket.com/activity?{query}")
        if not isinstance(data, list) or not data:
            break
        out.extend(data)
        offset += len(data)
        time.sleep(0.1)
    return out


def is_btc_updown(row: dict[str, Any]) -> bool:
    text = f"{row.get('title', '')} {row.get('slug', '')} {row.get('eventSlug', '')}".lower()
    return "bitcoin up or down" in text or "btc-updown" in text


def window_type(row: dict[str, Any]) -> str:
    text = f"{row.get('slug', '')} {row.get('eventSlug', '')}".lower()
    if "btc-updown-5m" in text:
        return "5m"
    if "btc-updown-15m" in text:
        return "15m"
    if "btc-updown-4h" in text:
        return "4h"
    title = str(row.get("title", "")).lower()
    if "10:" in title or "11:" in title:
        return "unknown-short"
    return "other"


def dt(ts: Any) -> str:
    try:
        return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "n/a"


def money(value: Any) -> str:
    try:
        return f"{float(value):,.2f}"
    except Exception:
        return "n/a"


def summarize_account(url: str, limit: int) -> dict[str, Any]:
    nd = profile_next_data(url)
    profile = find_profile(nd)
    volume = find_volume(nd)
    stats = find_stats(nd)
    wallet = profile["proxyWallet"]
    rows = fetch_activity(wallet, limit)
    trades = [row for row in rows if row.get("type") == "TRADE"]
    btc = [row for row in trades if is_btc_updown(row)]
    by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in btc:
        by_market[str(row.get("slug") or row.get("eventSlug") or row.get("title"))].append(row)

    prices = [float(row["price"]) for row in btc if row.get("price") is not None]
    sizes = [float(row["usdcSize"]) for row in btc if row.get("usdcSize") is not None]
    grouped = []
    for slug, items in by_market.items():
        usdc = sum(float(item.get("usdcSize") or 0) for item in items)
        grouped.append(
            {
                "slug": slug,
                "title": str(items[0].get("title", "")),
                "trades": len(items),
                "usdc": usdc,
                "side": Counter(str(item.get("side")) for item in items).most_common(1)[0][0],
                "outcome": Counter(str(item.get("outcome")) for item in items).most_common(1)[0][0],
                "window": Counter(window_type(item) for item in items).most_common(1)[0][0],
                "avg_price": statistics.mean([float(item["price"]) for item in items if item.get("price") is not None]),
                "first": min(int(item.get("timestamp") or 0) for item in items),
                "last": max(int(item.get("timestamp") or 0) for item in items),
            }
        )
    grouped.sort(key=lambda item: item["usdc"], reverse=True)

    return {
        "url": url,
        "name": profile.get("name") or profile.get("pseudonym"),
        "wallet": wallet,
        "volume": volume.get("amount"),
        "pnl": volume.get("pnl"),
        "markets_traded": stats.get("trades"),
        "activity_rows": len(rows),
        "trade_rows": len(trades),
        "btc_trade_rows": len(btc),
        "btc_unique_markets": len(by_market),
        "side_counts": Counter(str(row.get("side")) for row in btc),
        "outcome_counts": Counter(str(row.get("outcome")) for row in btc),
        "window_counts": Counter(window_type(row) for row in btc),
        "price_median": statistics.median(prices) if prices else 0,
        "price_avg": statistics.mean(prices) if prices else 0,
        "size_median": statistics.median(sizes) if sizes else 0,
        "size_avg": statistics.mean(sizes) if sizes else 0,
        "grouped": grouped,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()

    summaries = []
    for url in PROFILE_URLS:
        print(f"\nFetching {url}")
        try:
            summary = summarize_account(url, args.limit)
        except Exception as exc:
            print(f"ERROR: {exc}")
            continue
        summaries.append(summary)
        print(f"Account: {summary['name']} | {summary['wallet']}")
        print(f"Volume: {money(summary['volume'])}U | PnL: {money(summary['pnl'])}U | Markets: {summary['markets_traded']}")
        print(
            f"Analyzed trades: {summary['trade_rows']} | BTC trades: {summary['btc_trade_rows']} "
            f"across {summary['btc_unique_markets']} markets"
        )
        print(f"Side mix: {dict(summary['side_counts'])}")
        print(f"Outcome mix: {dict(summary['outcome_counts'])}")
        print(f"Window mix: {dict(summary['window_counts'])}")
        print(f"Median price: {summary['price_median']:.3f} | median trade size: {summary['size_median']:.2f}U")
        print("Top BTC market clusters:")
        for item in summary["grouped"][:8]:
            print(
                f"- {money(item['usdc'])}U / {item['trades']} trades / {item['window']} / "
                f"{item['side']} {item['outcome']} @avg {item['avg_price']:.3f} / {dt(item['first'])} -> {dt(item['last'])}"
            )
            print(f"  {item['title']}")

    total_btc = sum(item["btc_trade_rows"] for item in summaries)
    total_markets = sum(item["btc_unique_markets"] for item in summaries)
    all_windows = Counter()
    all_sides = Counter()
    all_outcomes = Counter()
    for item in summaries:
        all_windows.update(item["window_counts"])
        all_sides.update(item["side_counts"])
        all_outcomes.update(item["outcome_counts"])
    print("\n=== Combined BTC bot sample ===")
    print(f"Accounts analyzed: {len(summaries)}")
    print(f"BTC trade rows: {total_btc} | BTC unique-market count sum: {total_markets}")
    print(f"Window mix: {dict(all_windows)}")
    print(f"Side mix: {dict(all_sides)}")
    print(f"Outcome mix: {dict(all_outcomes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
