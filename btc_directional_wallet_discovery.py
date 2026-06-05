#!/usr/bin/env python3
"""Discover BTC directional wallets similar to the profitable copy bucket.

This is report-only. It mines public Polymarket trades from BTC directional
markets seen locally plus current public BTC directional markets, then ranks
wallets for observation. It never edits the live copy wallet list.
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


ROOT = Path(__file__).resolve().parent
AUDIT = ROOT / "btc_directional_trade_audit.csv"
OUTPUT_CSV = ROOT / "btc_directional_wallet_candidates.csv"
OUTPUT_MD = ROOT / "btc_directional_wallet_candidates.md"

FIELDS = [
    "wallet",
    "alias",
    "score",
    "recommendation",
    "reason",
    "seed_trade_count",
    "seed_markets",
    "observed_volume_usdc",
    "no_buy_count",
    "yes_buy_count",
    "above_count",
    "range_count",
    "reach_dip_count",
    "avg_price",
    "last_seen",
    "activity_btc_directional",
    "activity_reach_dip",
    "activity_weather",
    "activity_crypto_short",
    "example_markets",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def http_json(url: str, timeout: int = 20) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Connection": "close"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            time.sleep(0.5 * (attempt + 1))
    raise last_error or RuntimeError(f"request failed: {url}")


def market_by_slug(slug: str) -> dict[str, Any] | None:
    if not slug:
        return None
    query = urllib.parse.urlencode({"slug": slug})
    data = http_json(f"https://gamma-api.polymarket.com/markets?{query}")
    if isinstance(data, list) and data:
        return data[0]
    return None


def trades_for_condition(condition_id: str, limit: int) -> list[dict[str, Any]]:
    if not condition_id:
        return []
    query = urllib.parse.urlencode({"market": condition_id, "side": "BUY", "limit": limit, "takerOnly": "false"})
    data = http_json(f"https://data-api.polymarket.com/trades?{query}")
    return data if isinstance(data, list) else []


def active_markets_page(limit: int, offset: int) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(
        {
            "limit": limit,
            "offset": offset,
            "active": "true",
            "closed": "false",
            "archived": "false",
            "order": "volume",
            "ascending": "false",
        }
    )
    data = http_json(f"https://gamma-api.polymarket.com/markets?{query}")
    return data if isinstance(data, list) else []


def activity_for_wallet(wallet: str, limit: int) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"user": wallet, "limit": limit, "offset": 0})
    data = http_json(f"https://data-api.polymarket.com/activity?{query}")
    return data if isinstance(data, list) else []


def classify_market(title: str, slug: str) -> str:
    text = f"{title} {slug}".lower()
    if "up or down" in text or "updown" in text:
        return "crypto_short"
    if "highest temperature" in text or "lowest temperature" in text or "weather" in text:
        return "weather"
    if ("bitcoin" in text or "btc" in text) and ("reach" in text or "dip" in text):
        return "reach_dip"
    if ("bitcoin" in text or "btc" in text) and ("between" in text or re.search(r"\$[\d,]+.*\$[\d,]+", text)):
        return "range"
    if ("bitcoin" in text or "btc" in text) and ("above" in text or "below" in text or "price of bitcoin" in text):
        return "above"
    if "bitcoin" in text or "btc" in text:
        return "btc_other"
    return "other"


def seed_slugs(max_markets: int) -> list[str]:
    rows = read_csv(AUDIT)
    by_slug: dict[str, dict[str, Any]] = {}
    for row in rows:
        slug = row.get("slug") or ""
        if not slug:
            continue
        title = row.get("title") or ""
        market_type = classify_market(title, slug)
        if market_type not in {"above", "range"}:
            continue
        if row.get("outcome") != "No":
            continue
        price = fnum(row.get("source_price"))
        if price <= 0 or price > 0.80:
            continue
        item = by_slug.setdefault(
            slug,
            {
                "slug": slug,
                "title": title,
                "count": 0,
                "pnl": 0.0,
                "latest": datetime.min.replace(tzinfo=timezone.utc),
            },
        )
        item["count"] += 1
        if row.get("final_result") in {"WIN", "LOSS"}:
            item["pnl"] += fnum(row.get("slippage_final_pnl"))
        item["latest"] = max(item["latest"], parse_dt(row.get("detected_time") or row.get("signal_time") or row.get("audit_ts")))
    seeds = sorted(by_slug.values(), key=lambda item: (float(item["pnl"]), item["latest"], int(item["count"])), reverse=True)
    return [str(item["slug"]) for item in seeds[:max_markets]]


def public_btc_directional_slugs(args: argparse.Namespace) -> list[str]:
    """Find currently active BTC above/range markets from public market pages."""
    if args.public_market_pages <= 0:
        return []
    by_slug: dict[str, dict[str, Any]] = {}
    for page in range(args.public_market_pages):
        try:
            markets = active_markets_page(args.public_market_page_size, page * args.public_market_page_size)
        except Exception:
            break
        if not markets:
            break
        for market in markets:
            slug = str(market.get("slug") or "")
            title = str(market.get("question") or market.get("title") or "")
            market_type = classify_market(title, slug)
            if market_type not in {"above", "range"}:
                continue
            volume = fnum(market.get("volume"))
            liquidity = fnum(market.get("liquidity"))
            if volume < args.min_public_market_volume or liquidity < args.min_public_market_liquidity:
                continue
            by_slug[slug] = {
                "slug": slug,
                "volume": volume,
                "liquidity": liquidity,
                "endDate": str(market.get("endDate") or ""),
            }
        time.sleep(args.sleep_sec)
    ranked = sorted(by_slug.values(), key=lambda item: (float(item["volume"]), float(item["liquidity"])), reverse=True)
    return [str(item["slug"]) for item in ranked[: args.max_public_markets]]


def public_search_btc_directional_slugs(args: argparse.Namespace) -> list[str]:
    """Find active BTC directional markets through Polymarket public search."""
    if args.public_search_limit <= 0:
        return []
    by_slug: dict[str, dict[str, Any]] = {}
    queries = args.public_search_query or ["bitcoin above", "bitcoin between"]
    for text in queries:
        query = urllib.parse.urlencode(
            {
                "q": text,
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
                slug = str(market.get("slug") or "")
                title = str(market.get("question") or market.get("title") or "")
                market_type = classify_market(title, slug)
                if market_type not in {"above", "range"}:
                    continue
                volume = fnum(market.get("volume") or market.get("volumeNum"))
                liquidity = fnum(market.get("liquidity") or market.get("liquidityNum"))
                if volume < args.min_public_market_volume or liquidity < args.min_public_market_liquidity:
                    continue
                by_slug[slug] = {
                    "slug": slug,
                    "volume": volume,
                    "liquidity": liquidity,
                }
        time.sleep(args.sleep_sec)
    ranked = sorted(by_slug.values(), key=lambda item: (float(item["volume"]), float(item["liquidity"])), reverse=True)
    return [str(item["slug"]) for item in ranked[: args.max_public_markets]]


def empty_wallet(wallet: str, alias: str) -> dict[str, Any]:
    return {
        "wallet": wallet,
        "alias": alias or wallet[:12],
        "seed_trade_count": 0,
        "seed_markets": set(),
        "observed_volume_usdc": 0.0,
        "no_buy_count": 0,
        "yes_buy_count": 0,
        "above_count": 0,
        "range_count": 0,
        "reach_dip_count": 0,
        "prices": [],
        "last_seen": datetime.min.replace(tzinfo=timezone.utc),
        "activity_btc_directional": 0,
        "activity_reach_dip": 0,
        "activity_weather": 0,
        "activity_crypto_short": 0,
        "example_markets": [],
    }


def add_trade(stats: dict[str, Any], trade: dict[str, Any]) -> None:
    title = str(trade.get("title") or "")
    slug = str(trade.get("slug") or "")
    market_type = classify_market(title, slug)
    stats["seed_trade_count"] += 1
    stats["seed_markets"].add(slug)
    stats["observed_volume_usdc"] += fnum(trade.get("size")) * fnum(trade.get("price"))
    if str(trade.get("outcome") or "").lower() == "no":
        stats["no_buy_count"] += 1
    elif str(trade.get("outcome") or "").lower() == "yes":
        stats["yes_buy_count"] += 1
    if market_type == "above":
        stats["above_count"] += 1
    elif market_type == "range":
        stats["range_count"] += 1
    elif market_type == "reach_dip":
        stats["reach_dip_count"] += 1
    price = fnum(trade.get("price"))
    if price > 0:
        stats["prices"].append(price)
    if title and title not in stats["example_markets"]:
        stats["example_markets"].append(title)
    ts = fnum(trade.get("timestamp"))
    if ts > 0:
        stats["last_seen"] = max(stats["last_seen"], datetime.fromtimestamp(ts, tz=timezone.utc))


def enrich_activity(stats: dict[str, Any], limit: int) -> None:
    if limit <= 0:
        return
    try:
        rows = activity_for_wallet(str(stats["wallet"]), limit)
    except Exception:
        return
    for row in rows:
        if row.get("type") != "TRADE":
            continue
        market_type = classify_market(str(row.get("title") or ""), str(row.get("slug") or ""))
        if market_type in {"above", "range", "btc_other"}:
            stats["activity_btc_directional"] += 1
        elif market_type == "reach_dip":
            stats["activity_reach_dip"] += 1
            stats["activity_btc_directional"] += 1
        elif market_type == "weather":
            stats["activity_weather"] += 1
        elif market_type == "crypto_short":
            stats["activity_crypto_short"] += 1


def score(stats: dict[str, Any], args: argparse.Namespace) -> tuple[float, str, str]:
    if str(stats["wallet"]).lower() == "0x6e1d5040d0ac73709b0621f620d2a60b80d2d0fa":
        return 0.0, "CURRENT_REFERENCE", "already running as the reference BTC directional copy wallet"
    trade_count = int(stats["seed_trade_count"])
    volume = float(stats["observed_volume_usdc"])
    no_count = int(stats["no_buy_count"])
    yes_count = int(stats["yes_buy_count"])
    no_ratio = no_count / trade_count if trade_count else 0.0
    good_type = int(stats["above_count"]) + int(stats["range_count"])
    reach_dip = int(stats["reach_dip_count"]) + int(stats["activity_reach_dip"])
    avg_price = sum(stats["prices"]) / len(stats["prices"]) if stats["prices"] else 0.0
    activity_btc = int(stats["activity_btc_directional"])
    activity_bad_mix = int(stats["activity_weather"]) + int(stats["activity_crypto_short"])

    value = 0.0
    value += min(trade_count, 20) * 4
    value += min(volume, 500.0) / 10
    value += no_count * 7
    value += good_type * 4
    value += min(activity_btc, 40) * 1.5
    value -= yes_count * 5
    value -= reach_dip * 10
    value -= activity_bad_mix * 0.5
    if no_ratio >= 0.70:
        value += 35
    elif no_ratio >= 0.60:
        value += 15
    elif no_ratio < 0.50:
        value -= 45
    if 0.10 <= avg_price <= 0.80:
        value += 15
    elif avg_price > 0.80 or 0 < avg_price < 0.10:
        value -= 20
    if trade_count < 3:
        value -= 30
    if volume < 10:
        value -= 20

    if (
        value >= 90
        and trade_count >= 20
        and no_ratio >= args.min_no_ratio_high
        and reach_dip == 0
        and 0.10 <= avg_price <= 0.80
        and int(stats["activity_weather"]) <= 5
        and int(stats["activity_crypto_short"]) <= 30
    ):
        return value, "OBSERVE_HIGH", "same-market BTC directional behavior is close to current profitable bucket"
    if (
        value >= 55
        and trade_count >= 5
        and good_type >= 5
        and no_ratio >= args.min_no_ratio_small
        and reach_dip <= 5
        and 0.10 <= avg_price <= 0.85
        and activity_bad_mix <= 80
    ):
        return value, "OBSERVE_SMALL", "No-leaning possible match; keep small observation only"
    return value, "REJECT_FOR_NOW", "insufficient No-dominance, similarity, or too much bad bucket exposure"


def discover(args: argparse.Namespace) -> list[dict[str, Any]]:
    local_slugs = seed_slugs(args.max_seed_markets)
    public_slugs = public_btc_directional_slugs(args)
    search_slugs = public_search_btc_directional_slugs(args)
    slugs = list(dict.fromkeys((args.slug or []) + local_slugs + public_slugs + search_slugs))
    print(
        "BTC discovery seeds: "
        f"manual={len(args.slug or [])} local={len(local_slugs)} public={len(public_slugs)} "
        f"search={len(search_slugs)} unique={len(slugs)}"
    )
    wallet_stats: dict[str, dict[str, Any]] = {}
    for slug in slugs:
        market = market_by_slug(slug)
        if not market:
            continue
        condition_id = str(market.get("conditionId") or "")
        try:
            trades = trades_for_condition(condition_id, args.trades_per_market)
        except Exception:
            continue
        for trade in trades:
            wallet = str(trade.get("proxyWallet") or "").lower()
            if not wallet:
                continue
            alias = str(trade.get("name") or trade.get("pseudonym") or wallet[:12])
            item = wallet_stats.setdefault(wallet, empty_wallet(wallet, alias))
            add_trade(item, trade)
        time.sleep(args.sleep_sec)

    top = sorted(wallet_stats.values(), key=lambda row: (int(row["seed_trade_count"]), float(row["observed_volume_usdc"])), reverse=True)
    for item in top[: args.enrich_top]:
        enrich_activity(item, args.activity_limit)
        time.sleep(args.sleep_sec)

    rows: list[dict[str, Any]] = []
    for item in wallet_stats.values():
        value, recommendation, reason = score(item, args)
        prices = item["prices"]
        last_seen = item["last_seen"]
        rows.append(
            {
                "wallet": item["wallet"],
                "alias": item["alias"],
                "score": value,
                "recommendation": recommendation,
                "reason": reason,
                "seed_trade_count": item["seed_trade_count"],
                "seed_markets": len(item["seed_markets"]),
                "observed_volume_usdc": item["observed_volume_usdc"],
                "no_buy_count": item["no_buy_count"],
                "yes_buy_count": item["yes_buy_count"],
                "above_count": item["above_count"],
                "range_count": item["range_count"],
                "reach_dip_count": item["reach_dip_count"],
                "avg_price": sum(prices) / len(prices) if prices else 0.0,
                "last_seen": last_seen.isoformat() if last_seen.year > 1970 else "",
                "activity_btc_directional": item["activity_btc_directional"],
                "activity_reach_dip": item["activity_reach_dip"],
                "activity_weather": item["activity_weather"],
                "activity_crypto_short": item["activity_crypto_short"],
                "example_markets": " | ".join(item["example_markets"][:3]),
            }
        )
    return sorted(rows, key=lambda row: (float(row["score"]), float(row["observed_volume_usdc"])), reverse=True)


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in ["score", "observed_volume_usdc", "avg_price"]:
                out[key] = f"{fnum(out.get(key)):.6f}"
            writer.writerow({field: out.get(field, "") for field in FIELDS})


def render(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# BTC Directional Wallet Candidates",
        "",
        f"Generated: {now_utc()}",
        "",
        "Report-only observation candidates. No wallet is automatically added to a live or simulated copy list.",
        "",
        "| rank | rec | score | alias | wallet | trades | no/yes | above/range/reach | vol | avg price | activity btc/reach/weather/short | reason |",
        "|---:|---|---:|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for idx, row in enumerate(rows[:50], 1):
        lines.append(
            f"| {idx} | {row['recommendation']} | {fnum(row['score']):.1f} | {row['alias']} | {row['wallet']} | "
            f"{row['seed_trade_count']} | {row['no_buy_count']}/{row['yes_buy_count']} | "
            f"{row['above_count']}/{row['range_count']}/{row['reach_dip_count']} | "
            f"{fnum(row['observed_volume_usdc']):.2f}U | {fnum(row['avg_price']):.3f} | "
            f"{row['activity_btc_directional']}/{row['activity_reach_dip']}/{row['activity_weather']}/{row['activity_crypto_short']} | "
            f"{row['reason']} |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--slug", action="append", default=[], help="Extra BTC directional market slug to mine")
    parser.add_argument("--max-seed-markets", type=int, default=25)
    parser.add_argument("--public-market-pages", type=int, default=6)
    parser.add_argument("--public-market-page-size", type=int, default=100)
    parser.add_argument("--max-public-markets", type=int, default=25)
    parser.add_argument("--public-search-limit", type=int, default=12)
    parser.add_argument("--public-search-query", action="append", default=[])
    parser.add_argument("--min-public-market-volume", type=float, default=500.0)
    parser.add_argument("--min-public-market-liquidity", type=float, default=100.0)
    parser.add_argument("--trades-per-market", type=int, default=200)
    parser.add_argument("--enrich-top", type=int, default=40)
    parser.add_argument("--activity-limit", type=int, default=100)
    parser.add_argument("--min-no-ratio-high", type=float, default=0.60)
    parser.add_argument("--min-no-ratio-small", type=float, default=0.50)
    parser.add_argument("--sleep-sec", type=float, default=0.15)
    parser.add_argument("--output", type=Path, default=OUTPUT_CSV)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = discover(args)
    write_csv(rows, args.output)
    text = render(rows)
    OUTPUT_MD.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
