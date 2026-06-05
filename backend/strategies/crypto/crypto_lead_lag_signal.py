#!/usr/bin/env python3
"""Generate crypto lead-lag candidates for Polymarket Up/Down simulations."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scan_polymarket_arbitrage import fetch_books, normalize_levels, parse_json_list


GAMMA_EVENTS = "https://gamma-api.polymarket.com/events"
DURATIONS = {"5m": 300, "15m": 900}
ASSETS = {
    "BTC": {
        "page": "https://polymarket.com/crypto/bitcoin",
        "slug_prefix": "btc",
        "binance": "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
        "coinbase": "https://api.exchange.coinbase.com/products/BTC-USD/ticker",
        "okx": "https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT",
    },
    "ETH": {
        "page": "https://polymarket.com/crypto/ethereum",
        "slug_prefix": "eth",
        "binance": "https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT",
        "coinbase": "https://api.exchange.coinbase.com/products/ETH-USD/ticker",
        "okx": "https://www.okx.com/api/v5/market/ticker?instId=ETH-USDT",
    },
}


FIELDS = [
    "ts",
    "candidate_id",
    "signal_bucket",
    "asset",
    "slug",
    "event_slug",
    "question",
    "direction",
    "duration",
    "start_ts",
    "end_ts",
    "seconds_since_start",
    "seconds_to_end",
    "start_price",
    "consensus_price",
    "move_bps",
    "source_spread_bps",
    "estimated_q",
    "best_bid",
    "best_ask",
    "ask_depth_shares",
    "ask_depth_usdc",
    "sim_fill_price",
    "sim_shares",
    "would_live_fill",
    "slippage_bps",
    "source_to_ask_gap",
    "expected_edge_bps",
    "prices_json",
    "url",
]


@dataclass
class CryptoMarket:
    asset: str
    slug: str
    question: str
    start_ts: int
    end_ts: int
    duration: str
    up_token: str
    down_token: str
    market: dict[str, Any]


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def http_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Connection": "close"})
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            last_error = exc
            time.sleep(0.6 * (attempt + 1))
    raise last_error or RuntimeError(f"request failed: {url}")


def http_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Connection": "close"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            time.sleep(0.5 * (attempt + 1))
    raise last_error or RuntimeError(f"request failed: {url}")


def parse_slug(asset: str, slug: str) -> tuple[str, int, int] | None:
    prefix = ASSETS[asset]["slug_prefix"]
    match = re.match(rf"{prefix}-updown-(5m|15m)-(\d+)$", slug)
    if not match:
        return None
    duration = match.group(1)
    start_ts = int(match.group(2))
    return duration, start_ts, start_ts + DURATIONS[duration]


def discover_slugs(asset: str) -> list[str]:
    prefix = ASSETS[asset]["slug_prefix"]
    found: set[str] = set()
    try:
        html = http_text(str(ASSETS[asset]["page"]))
        found.update(re.findall(rf"{prefix}-updown-(?:5m|15m)-\d+", html))
    except Exception as exc:
        print(f"lead-lag page discovery failed, using generated slugs | {asset} | {exc}", flush=True)
    now = int(time.time())
    for duration, seconds in DURATIONS.items():
        aligned = now - (now % seconds)
        for offset in range(-2, 5):
            found.add(f"{prefix}-updown-{duration}-{aligned + offset * seconds}")
    return sorted(found)


def event_for_slug(slug: str) -> dict[str, Any] | None:
    url = f"{GAMMA_EVENTS}?{urllib.parse.urlencode({'slug': slug})}"
    data = http_json(url)
    if isinstance(data, list) and data:
        return data[0]
    return None


def market_from_event(asset: str, slug: str, event: dict[str, Any]) -> CryptoMarket | None:
    parsed = parse_slug(asset, slug)
    if not parsed:
        return None
    duration, start_ts, end_ts = parsed
    markets = event.get("markets") or []
    if not markets:
        return None
    market = markets[0]
    if not market.get("active") or market.get("closed") or market.get("acceptingOrders") is False:
        return None
    outcomes = [str(item) for item in parse_json_list(market.get("outcomes"))]
    token_ids = [str(item) for item in parse_json_list(market.get("clobTokenIds"))]
    if outcomes != ["Up", "Down"] or len(token_ids) != 2:
        return None
    return CryptoMarket(
        asset=asset,
        slug=slug,
        question=str(market.get("question") or event.get("title") or slug),
        start_ts=start_ts,
        end_ts=end_ts,
        duration=duration,
        up_token=token_ids[0],
        down_token=token_ids[1],
        market=market,
    )


def discover_markets(assets: list[str], lookahead_seconds: int, durations: set[str]) -> list[CryptoMarket]:
    now = int(time.time())
    out: list[CryptoMarket] = []
    for asset in assets:
        try:
            slugs = discover_slugs(asset)
        except Exception as exc:
            print(f"skip lead-lag asset: slug discovery failed | {asset} | {exc}", flush=True)
            continue
        for slug in slugs:
            parsed = parse_slug(asset, slug)
            if not parsed:
                continue
            duration, start_ts, end_ts = parsed
            if duration not in durations:
                continue
            if start_ts > now + lookahead_seconds or end_ts < now - 900:
                continue
            try:
                event = event_for_slug(slug)
            except Exception as exc:
                print(f"skip lead-lag market: event fetch failed | {slug} | {exc}", flush=True)
                continue
            if not event:
                continue
            market = market_from_event(asset, slug, event)
            if market:
                out.append(market)
    return sorted(out, key=lambda item: item.start_ts)


def price_sources(asset: str) -> dict[str, float]:
    cfg = ASSETS[asset]
    prices: dict[str, float] = {}
    try:
        prices["binance"] = fnum(http_json(str(cfg["binance"])).get("price"))
    except Exception:
        pass
    try:
        prices["coinbase"] = fnum(http_json(str(cfg["coinbase"])).get("price"))
    except Exception:
        pass
    try:
        data = http_json(str(cfg["okx"]))
        prices["okx"] = fnum(data["data"][0]["last"])
    except Exception:
        pass
    return {key: value for key, value in prices.items() if value > 0}


def consensus(prices: dict[str, float]) -> tuple[float, float]:
    values = list(prices.values())
    if len(values) >= 3:
        pairs: list[tuple[float, float]] = []
        for idx, left in enumerate(values):
            for right in values[idx + 1 :]:
                mid_pair = (left + right) / 2
                spread_pair = (max(left, right) - min(left, right)) / mid_pair * 10000 if mid_pair else 999.0
                pairs.append((spread_pair, mid_pair))
        spread, mid = min(pairs, key=lambda item: item[0])
        return mid, spread
    mid = sum(values) / len(values)
    spread_bps = (max(values) - min(values)) / mid * 10000 if mid else 999.0
    return mid, spread_bps


def open_price(asset: str, ts: int) -> float | None:
    symbol = "BTCUSDT" if asset == "BTC" else "ETHUSDT"
    params = urllib.parse.urlencode({"symbol": symbol, "interval": "1m", "startTime": ts * 1000, "limit": 1})
    rows = http_json(f"https://api.binance.com/api/v3/klines?{params}")
    if not rows:
        return None
    return fnum(rows[0][1])


def token_snapshot(token_id: str, stake: float) -> dict[str, Any]:
    books = fetch_books([token_id], chunk_size=1)
    book = books.get(token_id, {})
    asks = normalize_levels(book, "asks")
    bids = normalize_levels(book, "bids")
    best_ask = asks[0].price if asks else 0.0
    best_bid = bids[0].price if bids else 0.0
    depth_shares = sum(level.size for level in asks)
    depth_usdc = sum(level.price * level.size for level in asks)
    remaining = stake
    shares = 0.0
    spent = 0.0
    for level in asks:
        max_usdc = level.price * level.size
        use_usdc = min(remaining, max_usdc)
        if use_usdc <= 0:
            continue
        shares += use_usdc / level.price
        spent += use_usdc
        remaining -= use_usdc
        if remaining <= 1e-9:
            break
    fill = spent / shares if shares > 0 else 0.0
    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "ask_depth_shares": depth_shares,
        "ask_depth_usdc": depth_usdc,
        "sim_fill_price": fill,
        "sim_shares": shares,
        "would_live_fill": remaining <= 1e-9,
    }


def estimated_probability(move_bps: float, min_move_bps: float, seconds_to_end: int, duration_seconds: int) -> float:
    time_factor = max(0.7, min(1.4, seconds_to_end / max(1, duration_seconds) + 0.45))
    raw = 0.5 + math.tanh(move_bps / max(1.0, min_move_bps * 2.5)) * 0.34 / time_factor
    return max(0.05, min(0.95, raw))


def build_candidates(args: argparse.Namespace) -> list[dict[str, Any]]:
    assets = [item.strip().upper() for item in args.assets.split(",") if item.strip()]
    durations = {item.strip() for item in args.durations.split(",") if item.strip()}
    markets = discover_markets(assets, args.lookahead_seconds, durations)
    rows: list[dict[str, Any]] = []
    now = int(time.time())
    for market in markets:
        if now < market.start_ts + args.min_seconds_after_start:
            continue
        if now > market.end_ts - args.min_seconds_before_end:
            continue
        try:
            start = open_price(market.asset, market.start_ts)
        except Exception as exc:
            print(f"skip lead-lag market: open price failed | {market.slug} | {exc}", flush=True)
            continue
        if not start:
            continue
        try:
            prices = price_sources(market.asset)
        except Exception as exc:
            print(f"skip lead-lag market: price sources failed | {market.slug} | {exc}", flush=True)
            continue
        if len(prices) < args.min_price_sources:
            continue
        current, source_spread = consensus(prices)
        if source_spread > args.max_source_spread_bps:
            continue
        move_bps = (current / start - 1.0) * 10000
        if abs(move_bps) < args.min_move_bps:
            continue
        direction = "Up" if move_bps > 0 else "Down"
        token_id = market.up_token if direction == "Up" else market.down_token
        q_up = estimated_probability(move_bps, args.min_move_bps, market.end_ts - now, DURATIONS[market.duration])
        estimated_q = q_up if direction == "Up" else 1.0 - q_up
        try:
            snap = token_snapshot(token_id, args.stake_usdc)
        except Exception as exc:
            print(f"skip lead-lag market: order book failed | {market.slug} | {exc}", flush=True)
            continue
        best_ask = fnum(snap.get("best_ask"))
        fill = fnum(snap.get("sim_fill_price"))
        if best_ask <= 0 or best_ask > args.max_entry_price:
            continue
        source_to_ask_gap = best_ask - estimated_q
        expected_edge_bps = (estimated_q - fill) * 10000
        slippage_bps = ((fill - best_ask) / best_ask * 10000) if best_ask > 0 else 9999.0
        if expected_edge_bps < args.min_expected_edge_bps:
            continue
        if source_to_ask_gap > args.max_source_to_ask_gap:
            continue
        bucket = now // max(1, args.signal_bucket_seconds)
        candidate_id = f"{market.asset}:{market.slug}:{direction}:{bucket}"
        rows.append(
            {
                "ts": now_iso(),
                "candidate_id": candidate_id,
                "signal_bucket": str(bucket),
                "asset": market.asset,
                "slug": market.slug,
                "event_slug": market.slug,
                "question": market.question,
                "direction": direction,
                "duration": market.duration,
                "start_ts": market.start_ts,
                "end_ts": market.end_ts,
                "seconds_since_start": now - market.start_ts,
                "seconds_to_end": market.end_ts - now,
                "start_price": f"{start:.6f}",
                "consensus_price": f"{current:.6f}",
                "move_bps": f"{move_bps:.4f}",
                "source_spread_bps": f"{source_spread:.4f}",
                "estimated_q": f"{estimated_q:.6f}",
                "best_bid": f"{fnum(snap.get('best_bid')):.6f}",
                "best_ask": f"{best_ask:.6f}",
                "ask_depth_shares": f"{fnum(snap.get('ask_depth_shares')):.4f}",
                "ask_depth_usdc": f"{fnum(snap.get('ask_depth_usdc')):.4f}",
                "sim_fill_price": f"{fill:.6f}",
                "sim_shares": f"{fnum(snap.get('sim_shares')):.4f}",
                "would_live_fill": "YES" if snap.get("would_live_fill") else "NO",
                "slippage_bps": f"{slippage_bps:.4f}",
                "source_to_ask_gap": f"{source_to_ask_gap:.6f}",
                "expected_edge_bps": f"{expected_edge_bps:.4f}",
                "prices_json": json.dumps(prices, sort_keys=True),
                "url": f"https://polymarket.com/event/{market.slug}",
            }
        )
    return rows


def write_candidates(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDS})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", default="BTC,ETH")
    parser.add_argument("--durations", default="5m,15m")
    parser.add_argument("--lookahead-seconds", type=int, default=1200)
    parser.add_argument("--stake-usdc", type=float, default=1.0)
    parser.add_argument("--min-move-bps", type=float, default=8.0)
    parser.add_argument("--min-expected-edge-bps", type=float, default=25.0)
    parser.add_argument("--min-price-sources", type=int, default=2)
    parser.add_argument("--max-source-spread-bps", type=float, default=8.0)
    parser.add_argument("--max-source-to-ask-gap", type=float, default=0.015)
    parser.add_argument("--max-entry-price", type=float, default=0.70)
    parser.add_argument("--min-seconds-after-start", type=int, default=15)
    parser.add_argument("--min-seconds-before-end", type=int, default=35)
    parser.add_argument("--signal-bucket-seconds", type=int, default=60)
    parser.add_argument("--output", type=Path, default=Path("crypto_lead_lag_candidates.csv"))
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = build_candidates(args)
    write_candidates(rows, args.output)
    print(f"Wrote {args.output} candidates={len(rows)}")
    for row in rows[:20]:
        print(
            f"{row['asset']} {row['direction']} {row['duration']} edge={row['expected_edge_bps']}bps "
            f"ask={row['best_ask']} q={row['estimated_q']} {row['slug']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
