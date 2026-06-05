#!/usr/bin/env python3
"""Analyze a public Polymarket account profile and recent activity."""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.parse
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any


DEFAULT_USER = "creamcream1215"
DEFAULT_WALLET = "0x01ced860d8dca5d7987579d2a2635df8520d27a2"


def http_json(url: str) -> Any:
    last_error: Exception | None = None
    for attempt in range(3):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Connection": "close"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionResetError, TimeoutError) as exc:
            last_error = exc
            time.sleep(0.7 * (attempt + 1))
    raise last_error or RuntimeError(f"request failed: {url}")


def data_api(path: str, **params: Any) -> Any:
    query = urllib.parse.urlencode(params)
    return http_json(f"https://data-api.polymarket.com/{path}?{query}")


def fetch_activity(wallet: str, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    page_size = min(500, limit)
    while len(rows) < limit:
        batch = data_api("activity", user=wallet, limit=page_size, offset=offset)
        if not isinstance(batch, list) or not batch:
            break
        rows.extend(batch)
        offset += len(batch)
        time.sleep(0.1)
    return rows[:limit]


def fetch_profile_html(username: str | None = None, profile_url: str | None = None) -> dict[str, Any]:
    url = profile_url or f"https://polymarket.com/zh/@{username}?tab=activity"
    html = None
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            html = urllib.request.urlopen(
                urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Connection": "close"}),
                timeout=30,
            ).read().decode("utf-8", "replace")
            break
        except (urllib.error.URLError, ConnectionResetError, TimeoutError) as exc:
            last_error = exc
            time.sleep(0.7 * (attempt + 1))
    if html is None:
        raise last_error or RuntimeError(f"profile fetch failed: {url}")
    start = html.find("__NEXT_DATA__")
    start = html.find(">", start) + 1
    end = html.find("</script>", start)
    return json.loads(html[start:end])


def find_query_data(next_data: dict[str, Any], key_part: str) -> Any:
    queries = next_data["props"]["pageProps"]["dehydratedState"]["queries"]
    for query in queries:
        key = str(query.get("queryKey", ""))
        if key_part in key:
            return query.get("state", {}).get("data")
    return None


def money(value: Any) -> str:
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "n/a"


def summarize_activity(rows: list[dict[str, Any]]) -> dict[str, Any]:
    trades = [row for row in rows if row.get("type") == "TRADE"]
    by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in trades:
        by_market[str(row.get("slug") or row.get("title"))].append(row)

    titles = Counter(str(row.get("title", "")) for row in trades)
    event_slugs = Counter(str(row.get("eventSlug", "")) for row in trades)
    sides = Counter(str(row.get("side", "")) for row in trades)
    outcomes = Counter(str(row.get("outcome", "")) for row in trades)
    prices = [float(row["price"]) for row in trades if row.get("price") is not None]
    sizes = [float(row["usdcSize"]) for row in trades if row.get("usdcSize") is not None]

    grouped = []
    for slug, items in by_market.items():
        total = sum(float(item.get("usdcSize") or 0) for item in items)
        first_ts = min(int(item.get("timestamp") or 0) for item in items)
        last_ts = max(int(item.get("timestamp") or 0) for item in items)
        prices_for_market = [float(item["price"]) for item in items if item.get("price") is not None]
        grouped.append(
            {
                "slug": slug,
                "title": str(items[0].get("title", "")),
                "trades": len(items),
                "usdc": total,
                "side": Counter(str(item.get("side", "")) for item in items).most_common(1)[0][0],
                "outcome": Counter(str(item.get("outcome", "")) for item in items).most_common(1)[0][0],
                "avg_price": statistics.mean(prices_for_market) if prices_for_market else 0,
                "first": first_ts,
                "last": last_ts,
            }
        )

    grouped.sort(key=lambda item: item["usdc"], reverse=True)
    return {
        "trade_count": len(trades),
        "unique_markets": len(by_market),
        "side_counts": sides,
        "outcome_counts": outcomes,
        "top_titles": titles.most_common(10),
        "top_events": event_slugs.most_common(10),
        "price_avg": statistics.mean(prices) if prices else 0,
        "price_median": statistics.median(prices) if prices else 0,
        "usdc_avg": statistics.mean(sizes) if sizes else 0,
        "usdc_median": statistics.median(sizes) if sizes else 0,
        "grouped": grouped,
    }


def dt(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default=DEFAULT_USER)
    parser.add_argument("--wallet", default=DEFAULT_WALLET)
    parser.add_argument("--profile-url", default=None)
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()

    next_data = fetch_profile_html(args.username, args.profile_url)
    user_data = find_query_data(next_data, "/api/profile/userData") or {}
    if args.wallet == DEFAULT_WALLET and user_data.get("proxyWallet"):
        args.wallet = user_data["proxyWallet"]
    if user_data.get("name"):
        args.username = user_data["name"]
    volume = find_query_data(next_data, "/api/profile/volume") or {}
    user_stats = find_query_data(next_data, "user-stats") or {}
    current_positions = find_query_data(next_data, "profile', 'positions") or {}
    biggest_wins = find_query_data(next_data, "profile-biggest-wins") or {}
    activity = fetch_activity(args.wallet, args.limit)
    summary = summarize_activity(activity)

    print(f"Account: {args.username}")
    print(f"Wallet: {args.wallet}")
    print(f"Volume: {money(volume.get('amount'))} USDC")
    print(f"PnL: {money(volume.get('pnl'))} USDC")
    print(f"Markets traded: {user_stats.get('trades', 'n/a')}")
    print(f"Largest win: {money(user_stats.get('largestWin'))} USDC")
    print()
    print(f"Recent analyzed trades: {summary['trade_count']} across {summary['unique_markets']} markets")
    print(f"Side mix: {dict(summary['side_counts'])}")
    print(f"Outcome mix: {dict(summary['outcome_counts'])}")
    print(f"Median trade price: {summary['price_median']:.4f}")
    print(f"Median trade size: {summary['usdc_median']:.2f} USDC")
    print()
    print("Top recent market clusters:")
    for item in summary["grouped"][:10]:
        print(
            f"- {money(item['usdc'])}U / {item['trades']} trades / {item['side']} {item['outcome']} "
            f"@avg {item['avg_price']:.3f} / {dt(item['first'])} -> {dt(item['last'])}"
        )
        print(f"  {item['title']}")

    print()
    print("Current positions:")
    pages = current_positions.get("pages", []) if isinstance(current_positions, dict) else []
    positions = pages[0] if pages else []
    for pos in positions[:10]:
        print(
            f"- value {money(pos.get('currentValue'))}U, PnL {money(pos.get('cashPnl'))}U "
            f"({money(pos.get('percentPnl'))}%), {pos.get('outcome')} @avg {pos.get('avgPrice')}, cur {pos.get('curPrice')}"
        )
        print(f"  {pos.get('title')}")

    print()
    print("Biggest wins:")
    for win in (biggest_wins.get("biggestWins") or [])[:10]:
        print(
            f"- PnL {money(win.get('pnl'))}U, outcome {win.get('outcome')}, buyPrice {win.get('buyPrice')}"
        )
        print(f"  {win.get('marketTitle')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
