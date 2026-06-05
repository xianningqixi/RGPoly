#!/usr/bin/env python3
"""Discover and summarize strong Polymarket wallets by public activity.

Uses the official Polymarket Data API leaderboard plus user activity endpoints.
The goal is strategy research, not blind copy trading.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_API = "https://data-api.polymarket.com"
LEADERBOARD_CATEGORIES = ["CRYPTO", "WEATHER", "OVERALL"]
TIME_PERIODS = ["DAY", "WEEK", "MONTH", "ALL"]


def http_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Connection": "close"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            time.sleep(0.7 * (attempt + 1))
    raise last_error or RuntimeError(f"request failed: {url}")


def data_api(path: str, **params: Any) -> Any:
    return http_json(f"{DATA_API}/{path}?{urllib.parse.urlencode(params)}")


def fetch_leaderboard(limit: int) -> list[dict[str, Any]]:
    wallets: dict[str, dict[str, Any]] = {}
    for category in LEADERBOARD_CATEGORIES:
        for period in TIME_PERIODS:
            for order in ["PNL", "VOL"]:
                rows = data_api(
                    "v1/leaderboard",
                    category=category,
                    timePeriod=period,
                    orderBy=order,
                    limit=min(limit, 50),
                    offset=0,
                )
                if not isinstance(rows, list):
                    continue
                for row in rows:
                    wallet = str(row.get("proxyWallet") or "").lower()
                    if not wallet.startswith("0x"):
                        continue
                    entry = wallets.setdefault(
                        wallet,
                        {
                            "proxyWallet": wallet,
                            "userName": row.get("userName"),
                            "bestPnl": float(row.get("pnl") or 0),
                            "bestVol": float(row.get("vol") or 0),
                            "sources": [],
                        },
                    )
                    entry["bestPnl"] = max(entry["bestPnl"], float(row.get("pnl") or 0))
                    entry["bestVol"] = max(entry["bestVol"], float(row.get("vol") or 0))
                    entry["sources"].append(f"{category}:{period}:{order}:rank{row.get('rank')}")
                time.sleep(0.05)
    return sorted(wallets.values(), key=lambda item: item["bestPnl"], reverse=True)


def fetch_activity(wallet: str, limit: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    offset = 0
    while len(out) < limit:
        batch_size = min(500, limit - len(out))
        rows = data_api("activity", user=wallet, limit=batch_size, offset=offset)
        if not isinstance(rows, list) or not rows:
            break
        out.extend(rows)
        offset += len(rows)
        time.sleep(0.08)
    return out


def classify(row: dict[str, Any]) -> str:
    text = f"{row.get('title', '')} {row.get('slug', '')} {row.get('eventSlug', '')}".lower()
    if "bitcoin up or down" in text or "btc-updown" in text:
        return "btc_updown"
    if "ethereum up or down" in text or "eth-updown" in text:
        return "eth_updown"
    if "solana up or down" in text or "xrp up or down" in text:
        return "alt_updown"
    if "highest temperature" in text or "lowest temperature" in text or "weather" in text:
        return "weather"
    if "nba" in text or "nhl" in text or "fifa" in text or "champions league" in text:
        return "sports"
    if "election" in text or "trump" in text or "president" in text:
        return "politics"
    return "other"


def window_type(row: dict[str, Any]) -> str:
    text = f"{row.get('slug', '')} {row.get('eventSlug', '')}".lower()
    if "5m" in text:
        return "5m"
    if "15m" in text:
        return "15m"
    if "4h" in text:
        return "4h"
    title = str(row.get("title") or "").lower()
    if "up or down" in title:
        return "other_updown"
    return "other"


def fnum(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def analyze_wallet(entry: dict[str, Any], activity_limit: int) -> dict[str, Any]:
    wallet = entry["proxyWallet"]
    rows = fetch_activity(wallet, activity_limit)
    trades = [row for row in rows if row.get("type") == "TRADE"]
    categories = Counter(classify(row) for row in trades)
    sides = Counter(str(row.get("side")) for row in trades)
    outcomes = Counter(str(row.get("outcome")) for row in trades)
    windows = Counter(window_type(row) for row in trades)
    prices = [fnum(row.get("price")) for row in trades if row.get("price") is not None]
    sizes = [fnum(row.get("usdcSize")) for row in trades if row.get("usdcSize") is not None]

    by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in trades:
        by_market[str(row.get("slug") or row.get("eventSlug") or row.get("title"))].append(row)
    top_clusters = []
    for slug, items in by_market.items():
        usdc = sum(fnum(item.get("usdcSize")) for item in items)
        top_clusters.append(
            {
                "slug": slug,
                "title": str(items[0].get("title") or ""),
                "category": classify(items[0]),
                "window": window_type(items[0]),
                "trades": len(items),
                "usdc": usdc,
                "side": Counter(str(item.get("side")) for item in items).most_common(1)[0][0],
                "outcome": Counter(str(item.get("outcome")) for item in items).most_common(1)[0][0],
                "avg_price": statistics.mean([fnum(item.get("price")) for item in items if item.get("price") is not None]),
            }
        )
    top_clusters.sort(key=lambda item: item["usdc"], reverse=True)

    crypto_short = categories["btc_updown"] + categories["eth_updown"] + categories["alt_updown"]
    buy_ratio = sides["BUY"] / len(trades) if trades else 0
    btc_share = categories["btc_updown"] / len(trades) if trades else 0
    weather_share = categories["weather"] / len(trades) if trades else 0
    short_window_share = (windows["5m"] + windows["15m"]) / len(trades) if trades else 0
    median_size = statistics.median(sizes) if sizes else 0
    median_price = statistics.median(prices) if prices else 0

    if crypto_short and short_window_share > 0.25:
        archetype = "crypto_short_window_bot"
    elif weather_share > 0.3:
        archetype = "weather_specialist"
    elif buy_ratio > 0.85 and len(trades) > 100:
        archetype = "buy_and_settle_directional"
    else:
        archetype = "mixed_or_unclear"

    return {
        **entry,
        "activityRows": len(rows),
        "tradeRows": len(trades),
        "categories": dict(categories),
        "sides": dict(sides),
        "outcomes": dict(outcomes),
        "windows": dict(windows),
        "buyRatio": buy_ratio,
        "btcShare": btc_share,
        "weatherShare": weather_share,
        "shortWindowShare": short_window_share,
        "medianSize": median_size,
        "avgSize": statistics.mean(sizes) if sizes else 0,
        "medianPrice": median_price,
        "avgPrice": statistics.mean(prices) if prices else 0,
        "uniqueMarkets": len(by_market),
        "archetype": archetype,
        "topClusters": top_clusters[:5],
    }


def write_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "proxyWallet",
        "userName",
        "bestPnl",
        "bestVol",
        "archetype",
        "tradeRows",
        "uniqueMarkets",
        "buyRatio",
        "btcShare",
        "weatherShare",
        "shortWindowShare",
        "medianSize",
        "medianPrice",
        "sources",
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: json.dumps(row[field], ensure_ascii=False) if field == "sources" else row.get(field) for field in fields})


def write_report(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Smart Wallet Research",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Main Findings",
        "",
        "- High-PnL crypto short-window wallets mostly buy, split entries into many small orders, and hold to resolution.",
        "- The recurring BTC pattern is 5m/15m Up/Down, not basket arbitrage.",
        "- Weather specialists are domain-specific; copy signals should stay observational until forecast edge is verified.",
        "- Do not blindly copy top PnL wallets: some PnL is concentrated in old windows or large one-off wins.",
        "",
        "## Wallets",
        "",
    ]
    for row in rows:
        lines.append(f"### {row.get('userName') or row['proxyWallet']}")
        lines.append(f"- wallet: `{row['proxyWallet']}`")
        lines.append(f"- archetype: `{row['archetype']}`")
        lines.append(f"- leaderboard pnl: {row['bestPnl']:.2f} U, volume: {row['bestVol']:.2f} U")
        lines.append(
            f"- analyzed trades: {row['tradeRows']}, markets: {row['uniqueMarkets']}, "
            f"buy ratio: {row['buyRatio']:.2%}, median size: {row['medianSize']:.2f} U, median price: {row['medianPrice']:.3f}"
        )
        lines.append(f"- categories: `{json.dumps(row['categories'], ensure_ascii=False)}`")
        lines.append(f"- windows: `{json.dumps(row['windows'], ensure_ascii=False)}`")
        lines.append("- top clusters:")
        for cluster in row["topClusters"]:
            lines.append(
                f"  - {cluster['usdc']:.2f}U / {cluster['trades']} trades / "
                f"{cluster['category']} {cluster['window']} / {cluster['side']} {cluster['outcome']} @ {cluster['avg_price']:.3f}: "
                f"{cluster['title']}"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--leaderboard-limit", type=int, default=20)
    parser.add_argument("--wallet-limit", type=int, default=25)
    parser.add_argument("--activity-limit", type=int, default=700)
    parser.add_argument("--csv", type=Path, default=Path("smart_wallet_summary.csv"))
    parser.add_argument("--report", type=Path, default=Path("smart_wallet_research.md"))
    args = parser.parse_args()

    candidates = fetch_leaderboard(args.leaderboard_limit)
    print(f"Discovered {len(candidates)} leaderboard wallets")
    analyzed = []
    for index, entry in enumerate(candidates[: args.wallet_limit], start=1):
        print(f"[{index}/{min(len(candidates), args.wallet_limit)}] {entry.get('userName')} {entry['proxyWallet']}")
        try:
            analyzed.append(analyze_wallet(entry, args.activity_limit))
        except Exception as exc:
            print(f"  ERROR: {exc}")
    analyzed.sort(key=lambda item: (item["archetype"] != "crypto_short_window_bot", -item["bestPnl"]))
    write_summary(args.csv, analyzed)
    write_report(args.report, analyzed)
    print(f"Wrote {args.csv}")
    print(f"Wrote {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
