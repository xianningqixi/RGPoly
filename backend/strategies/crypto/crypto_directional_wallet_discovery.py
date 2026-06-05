#!/usr/bin/env python3
"""Discover wallets trading non-BTC directional crypto price-level markets.

Report-only. It searches public active Polymarket markets for an asset, mines
recent BUY trades from matching markets, enriches each wallet with recent
activity, and writes a candidate CSV compatible with btc_directional_wallet_copy_sim.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path.cwd()

FIELDS = [
    "wallet",
    "alias",
    "score",
    "recommendation",
    "reason",
    "asset",
    "seed_trade_count",
    "seed_markets",
    "observed_volume_usdc",
    "no_buy_count",
    "yes_buy_count",
    "avg_price",
    "last_seen",
    "activity_asset_directional",
    "activity_weather",
    "activity_short_window",
    "example_markets",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def parse_dt(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def http_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Connection": "close"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            time.sleep(0.5 * (attempt + 1))
    raise last_error or RuntimeError(f"request failed: {url}")


def text_for(row: dict[str, Any]) -> str:
    return f"{row.get('title', '')} {row.get('question', '')} {row.get('slug', '')} {row.get('eventSlug', '')}".lower()


def matches_asset_directional(row: dict[str, Any], keywords: list[str]) -> bool:
    text = text_for(row)
    if "up or down" in text or "updown" in text:
        return False
    if not any(keyword in text for keyword in keywords):
        return False
    markers = ["above", "below", "between", "reach", "dip", "price of", "$"]
    return any(marker in text for marker in markers)


def public_search_slugs(args: argparse.Namespace) -> list[str]:
    by_slug: dict[str, dict[str, Any]] = {}
    queries = args.query or [
        f"{args.asset_name} above",
        f"{args.asset_name} between",
        f"{args.asset_name} price",
        f"{args.asset_name} reach",
        f"{args.asset_name} dip",
    ]
    for query_text in queries:
        query = urllib.parse.urlencode(
            {
                "q": query_text,
                "limit_per_type": args.public_search_limit,
                "events_status": "active",
                "keep_closed_markets": 0,
            }
        )
        try:
            data = http_json(f"https://gamma-api.polymarket.com/public-search?{query}")
        except Exception:
            continue
        events = data.get("events") if isinstance(data, dict) else []
        if not isinstance(events, list):
            continue
        for event in events:
            markets = event.get("markets") if isinstance(event, dict) else []
            if not isinstance(markets, list):
                continue
            for market in markets:
                if not matches_asset_directional(market, args.keyword):
                    continue
                slug = str(market.get("slug") or "")
                if not slug:
                    continue
                volume = fnum(market.get("volume") or market.get("volumeNum"))
                liquidity = fnum(market.get("liquidity") or market.get("liquidityNum"))
                if volume < args.min_volume or liquidity < args.min_liquidity:
                    continue
                by_slug[slug] = {"slug": slug, "volume": volume, "liquidity": liquidity}
        time.sleep(args.sleep_sec)
    ranked = sorted(by_slug.values(), key=lambda item: (float(item["volume"]), float(item["liquidity"])), reverse=True)
    return [str(item["slug"]) for item in ranked[: args.max_markets]]


def market_by_slug(slug: str) -> dict[str, Any] | None:
    query = urllib.parse.urlencode({"slug": slug})
    data = http_json(f"https://gamma-api.polymarket.com/markets?{query}")
    if isinstance(data, list) and data:
        return data[0]
    data = http_json(f"https://gamma-api.polymarket.com/events?{query}")
    if isinstance(data, list) and data:
        for market in data[0].get("markets") or []:
            if market.get("slug") == slug:
                return market
    return None


def trades_for_condition(condition_id: str, limit: int) -> list[dict[str, Any]]:
    if not condition_id:
        return []
    query = urllib.parse.urlencode({"market": condition_id, "side": "BUY", "limit": limit, "takerOnly": "false"})
    data = http_json(f"https://data-api.polymarket.com/trades?{query}")
    return data if isinstance(data, list) else []


def activity_for_wallet(wallet: str, limit: int) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"user": wallet, "limit": limit, "offset": 0})
    data = http_json(f"https://data-api.polymarket.com/activity?{query}")
    return data if isinstance(data, list) else []


def empty_wallet(wallet: str, alias: str, asset: str) -> dict[str, Any]:
    return {
        "wallet": wallet,
        "alias": alias or wallet[:12],
        "asset": asset,
        "seed_trade_count": 0,
        "seed_markets": set(),
        "observed_volume_usdc": 0.0,
        "no_buy_count": 0,
        "yes_buy_count": 0,
        "prices": [],
        "last_seen": datetime.min.replace(tzinfo=timezone.utc),
        "activity_asset_directional": 0,
        "activity_weather": 0,
        "activity_short_window": 0,
        "example_markets": [],
    }


def add_trade(stats: dict[str, Any], trade: dict[str, Any]) -> None:
    slug = str(trade.get("slug") or "")
    stats["seed_trade_count"] += 1
    stats["seed_markets"].add(slug)
    stats["observed_volume_usdc"] += fnum(trade.get("usdcSize") or trade.get("size"))
    outcome = str(trade.get("outcome") or "")
    if outcome == "No":
        stats["no_buy_count"] += 1
    elif outcome == "Yes":
        stats["yes_buy_count"] += 1
    price = fnum(trade.get("price"))
    if price:
        stats["prices"].append(price)
    stats["last_seen"] = max(stats["last_seen"], parse_dt(trade.get("timestamp")))
    title = str(trade.get("title") or slug)
    if title and title not in stats["example_markets"]:
        stats["example_markets"].append(title[:90])


def enrich(stats: dict[str, Any], args: argparse.Namespace) -> None:
    try:
        rows = activity_for_wallet(str(stats["wallet"]), args.activity_limit)
    except Exception as exc:
        stats["reason"] = f"activity_error: {exc}"
        return
    for row in rows:
        text = text_for(row)
        if "highest temperature" in text or "lowest temperature" in text or "weather" in text:
            stats["activity_weather"] += 1
        if "up or down" in text or "updown" in text:
            stats["activity_short_window"] += 1
        if matches_asset_directional(row, args.keyword):
            stats["activity_asset_directional"] += 1


def score(stats: dict[str, Any], args: argparse.Namespace) -> tuple[float, str, str]:
    trades = int(stats["seed_trade_count"])
    no_ratio = int(stats["no_buy_count"]) / max(1, int(stats["no_buy_count"]) + int(stats["yes_buy_count"]))
    activity = int(stats["activity_asset_directional"])
    bad_mix = int(stats["activity_weather"]) + int(stats["activity_short_window"])
    avg_price = sum(stats["prices"]) / len(stats["prices"]) if stats["prices"] else 0.0
    value = trades * 4.0 + min(activity, 50) * 1.5 + fnum(stats["observed_volume_usdc"]) / 50.0
    value += no_ratio * 10.0
    value -= bad_mix * 0.4
    if avg_price > args.max_avg_price:
        value -= 15.0
    if trades >= args.high_min_trades and activity >= args.high_min_activity and value > 20:
        return value, "OBSERVE_HIGH", "same-asset directional wallet; add only as isolated simulation"
    if trades >= args.small_min_trades and value > 8:
        return value, "OBSERVE_SMALL", "sample is small; observation only"
    return value, "WATCH_ONLY", "not enough evidence for simulated copy yet"


def discover(args: argparse.Namespace) -> list[dict[str, Any]]:
    slugs = list(dict.fromkeys((args.slug or []) + public_search_slugs(args)))
    print(f"{args.asset_name} directional discovery seeds: manual={len(args.slug or [])} public={len(slugs) - len(args.slug or [])} unique={len(slugs)}")
    wallets: dict[str, dict[str, Any]] = {}
    for slug in slugs:
        try:
            market = market_by_slug(slug)
            condition_id = str((market or {}).get("conditionId") or "")
            trades = trades_for_condition(condition_id, args.trades_per_market)
        except Exception:
            continue
        for trade in trades:
            wallet = str(trade.get("proxyWallet") or "").lower()
            if not wallet:
                continue
            alias = str(trade.get("name") or trade.get("pseudonym") or wallet[:12])
            item = wallets.setdefault(wallet, empty_wallet(wallet, alias, args.asset_name.upper()))
            add_trade(item, trade)
        time.sleep(args.sleep_sec)
    top = sorted(wallets.values(), key=lambda row: (int(row["seed_trade_count"]), float(row["observed_volume_usdc"])), reverse=True)
    for item in top[: args.enrich_top]:
        enrich(item, args)
        time.sleep(args.sleep_sec)
    rows = []
    for item in wallets.values():
        value, recommendation, reason = score(item, args)
        prices = item["prices"]
        rows.append(
            {
                "wallet": item["wallet"],
                "alias": re.sub(r"[^A-Za-z0-9_]+", "_", str(item["alias"])).strip("_") or item["wallet"][:12],
                "score": value,
                "recommendation": recommendation,
                "reason": reason if not item.get("reason") else item["reason"],
                "asset": item["asset"],
                "seed_trade_count": item["seed_trade_count"],
                "seed_markets": len(item["seed_markets"]),
                "observed_volume_usdc": item["observed_volume_usdc"],
                "no_buy_count": item["no_buy_count"],
                "yes_buy_count": item["yes_buy_count"],
                "avg_price": sum(prices) / len(prices) if prices else 0.0,
                "last_seen": item["last_seen"].isoformat() if item["last_seen"].year > 1970 else "",
                "activity_asset_directional": item["activity_asset_directional"],
                "activity_weather": item["activity_weather"],
                "activity_short_window": item["activity_short_window"],
                "example_markets": " | ".join(item["example_markets"][:3]),
            }
        )
    return sorted(rows, key=lambda row: (float(row["score"]), float(row["observed_volume_usdc"])), reverse=True)


def write_outputs(rows: list[dict[str, Any]], args: argparse.Namespace) -> None:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in ["score", "observed_volume_usdc", "avg_price"]:
                out[key] = f"{fnum(out.get(key)):.6f}"
            writer.writerow({field: out.get(field, "") for field in FIELDS})
    md = args.output.with_suffix(".md")
    lines = [
        f"# {args.asset_name.upper()} Directional Wallet Candidates",
        "",
        f"Generated: {now_utc()}",
        "",
        "Simulation candidates only. No live trading.",
        "",
        "| rank | rec | score | alias | wallet | trades | no/yes | vol | avg price | activity asset/weather/short | reason |",
        "|---:|---|---:|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for idx, row in enumerate(rows[:50], 1):
        lines.append(
            f"| {idx} | {row['recommendation']} | {fnum(row['score']):.1f} | {row['alias']} | {row['wallet']} | "
            f"{row['seed_trade_count']} | {row['no_buy_count']}/{row['yes_buy_count']} | "
            f"{fnum(row['observed_volume_usdc']):.2f}U | {fnum(row['avg_price']):.3f} | "
            f"{row['activity_asset_directional']}/{row['activity_weather']}/{row['activity_short_window']} | {row['reason']} |"
        )
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-name", required=True)
    parser.add_argument("--keyword", action="append", required=True)
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--slug", action="append", default=[])
    parser.add_argument("--public-search-limit", type=int, default=16)
    parser.add_argument("--max-markets", type=int, default=30)
    parser.add_argument("--min-volume", type=float, default=100.0)
    parser.add_argument("--min-liquidity", type=float, default=20.0)
    parser.add_argument("--trades-per-market", type=int, default=200)
    parser.add_argument("--enrich-top", type=int, default=50)
    parser.add_argument("--activity-limit", type=int, default=120)
    parser.add_argument("--high-min-trades", type=int, default=6)
    parser.add_argument("--high-min-activity", type=int, default=3)
    parser.add_argument("--small-min-trades", type=int, default=2)
    parser.add_argument("--max-avg-price", type=float, default=0.98)
    parser.add_argument("--sleep-sec", type=float, default=0.15)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.keyword = [item.lower() for item in args.keyword]
    rows = discover(args)
    write_outputs(rows, args)
    print(f"Wrote {args.output} ({len(rows)} wallets)")
    for idx, row in enumerate(rows[:10], 1):
        print(f"{idx}. {row['recommendation']} {row['alias']} {row['wallet']} score={fnum(row['score']):.1f} trades={row['seed_trade_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
