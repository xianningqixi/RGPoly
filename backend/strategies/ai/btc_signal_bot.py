#!/usr/bin/env python3
"""BTC Up/Down Polymarket signal simulator.

This bot does not place orders. It discovers BTC Up/Down events, watches
Binance BTCUSDT as a fast reference price, simulates entries when the reference
price has moved enough while the Polymarket ask is still acceptable, and marks
simulated positions after the event window ends.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scan_polymarket_arbitrage import fetch_books, parse_json_list


CRYPTO_PAGE = "https://polymarket.com/crypto/bitcoin"
GAMMA_EVENTS = "https://gamma-api.polymarket.com/events"
BINANCE_PRICE = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
COINBASE_PRICE = "https://api.exchange.coinbase.com/products/BTC-USD/ticker"
OKX_PRICE = "https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT"
DURATIONS = {"5m": 300, "15m": 900, "4h": 14400}


@dataclass
class BtcMarket:
    slug: str
    question: str
    start_ts: int
    end_ts: int
    duration_label: str
    up_token: str
    down_token: str
    url: str


@dataclass
class SimPosition:
    id: str
    slug: str
    question: str
    direction: str
    token_id: str
    stake: float
    entry_ask: float
    shares: float
    start_price: float
    entry_price_btc: float
    start_ts: int
    end_ts: int
    opened_at: int
    status: str = "OPEN"


def http_json(url: str, timeout: float = 20.0) -> Any:
    last_error: Exception | None = None
    for attempt in range(3):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json,text/plain,*/*",
                "Connection": "close",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, ConnectionResetError, TimeoutError) as exc:
            last_error = exc
            time.sleep(0.5 * (attempt + 1))
    raise last_error or RuntimeError(f"request failed: {url}")


def btc_price() -> float:
    return float(http_json(BINANCE_PRICE)["price"])


def coinbase_btc_price() -> float:
    return float(http_json(COINBASE_PRICE)["price"])


def okx_btc_price() -> float:
    data = http_json(OKX_PRICE)
    return float(data["data"][0]["last"])


def reference_prices() -> dict[str, float]:
    prices = {"binance": btc_price()}
    try:
        prices["coinbase"] = coinbase_btc_price()
    except Exception:
        pass
    try:
        prices["okx"] = okx_btc_price()
    except Exception:
        pass
    return prices


def consensus_price(prices: dict[str, float]) -> tuple[float, float]:
    values = list(prices.values())
    mid = sum(values) / len(values)
    spread_bps = (max(values) - min(values)) / mid * 10000 if mid else 0.0
    return mid, spread_bps


def binance_open_price(ts: int) -> float | None:
    params = urllib.parse.urlencode(
        {
            "symbol": "BTCUSDT",
            "interval": "1m",
            "startTime": ts * 1000,
            "limit": 1,
        }
    )
    rows = http_json(f"{BINANCE_KLINES}?{params}")
    if not rows:
        return None
    return float(rows[0][1])


def discover_slugs() -> list[str]:
    html = None
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            html = urllib.request.urlopen(
                urllib.request.Request(
                    CRYPTO_PAGE,
                    headers={"User-Agent": "Mozilla/5.0", "Connection": "close"},
                ),
                timeout=60,
            ).read().decode("utf-8", "replace")
            break
        except (urllib.error.URLError, ConnectionResetError, TimeoutError) as exc:
            last_error = exc
            time.sleep(0.8 * (attempt + 1))
    if html is None:
        raise last_error or RuntimeError("failed to fetch crypto page")
    slugs = []
    seen = set()
    for match in re.finditer(r"/event/((?:btc-updown|bitcoin-up-or-down)[^\"?#<]+)", html, re.I):
        slug = match.group(1)
        if slug not in seen:
            seen.add(slug)
            slugs.append(slug)
    return slugs


def parse_slug_window(slug: str) -> tuple[str, int, int] | None:
    match = re.match(r"btc-updown-(5m|15m|4h)-(\d+)$", slug)
    if not match:
        return None
    label = match.group(1)
    start_ts = int(match.group(2))
    return label, start_ts, start_ts + DURATIONS[label]


def event_for_slug(slug: str) -> dict[str, Any] | None:
    events = http_json(f"{GAMMA_EVENTS}?{urllib.parse.urlencode({'slug': slug})}")
    if isinstance(events, list) and events:
        return events[0]
    return None


def market_from_event(slug: str, event: dict[str, Any]) -> BtcMarket | None:
    parsed = parse_slug_window(slug)
    if parsed is None:
        return None
    label, start_ts, end_ts = parsed
    markets = event.get("markets") or []
    if not markets:
        return None
    market = markets[0]
    if not market.get("active") or market.get("closed"):
        return None
    if market.get("acceptingOrders") is False:
        return None
    outcomes = [str(item) for item in parse_json_list(market.get("outcomes"))]
    token_ids = [str(item) for item in parse_json_list(market.get("clobTokenIds"))]
    if outcomes != ["Up", "Down"] or len(token_ids) != 2:
        return None
    return BtcMarket(
        slug=slug,
        question=str(market.get("question") or event.get("title") or slug),
        start_ts=start_ts,
        end_ts=end_ts,
        duration_label=label,
        up_token=token_ids[0],
        down_token=token_ids[1],
        url=f"https://polymarket.com/event/{slug}",
    )


def discover_markets(
    lookahead_seconds: int,
    include_open: bool = True,
    durations: set[str] | None = None,
) -> list[BtcMarket]:
    now = int(time.time())
    markets = []
    slugs = []
    for slug in discover_slugs():
        parsed = parse_slug_window(slug)
        if parsed is None:
            continue
        label, start_ts, end_ts = parsed
        if durations and label not in durations:
            continue
        if end_ts < now and not include_open:
            continue
        if start_ts > now + lookahead_seconds:
            continue
        if end_ts < now - 3600:
            continue
        slugs.append(slug)

    for slug in sorted(set(slugs), key=lambda item: parse_slug_window(item)[1]):
        event = event_for_slug(slug)
        if event is None:
            continue
        market = market_from_event(slug, event)
        if market:
            markets.append(market)
    return sorted(markets, key=lambda item: item.start_ts)


def best_asks(market: BtcMarket) -> tuple[float | None, float | None]:
    books = fetch_books([market.up_token, market.down_token], chunk_size=2)
    asks = []
    for token_id in [market.up_token, market.down_token]:
        book = books.get(token_id, {})
        levels = book.get("asks") or []
        prices = [float(level["price"]) for level in levels if float(level.get("size", 0)) > 0]
        asks.append(min(prices) if prices else None)
    return asks[0], asks[1]


def position_key(slug: str, direction: str) -> str:
    return f"{slug}:{direction}:{int(time.time())}"


def append_csv(path: Path, row: dict[str, Any]) -> None:
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(row.keys()))
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def load_open_positions(path: Path) -> dict[str, SimPosition]:
    if not path.exists():
        return {}
    latest_rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            row_id = row.get("id")
            if not row_id:
                continue
            latest_rows[row_id] = row

    positions = {}
    for row in latest_rows.values():
        if row.get("status") != "OPEN":
            continue
        try:
            pos = SimPosition(
                id=row["id"],
                slug=row["slug"],
                question=row["question"],
                direction=row["direction"],
                token_id=row["token_id"],
                stake=float(row["stake"]),
                entry_ask=float(row["entry_ask"]),
                shares=float(row["shares"]),
                start_price=float(row["start_price"]),
                entry_price_btc=float(row["entry_price_btc"]),
                start_ts=int(row["start_ts"]),
                end_ts=int(row["end_ts"]),
                opened_at=int(row["opened_at"]),
                status=row["status"],
            )
            positions[pos.id] = pos
        except (KeyError, ValueError):
            continue
    return positions


def write_position(path: Path, pos: SimPosition, extra: dict[str, Any] | None = None) -> None:
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "id": pos.id,
        "slug": pos.slug,
        "question": pos.question,
        "direction": pos.direction,
        "token_id": pos.token_id,
        "stake": f"{pos.stake:.4f}",
        "entry_ask": f"{pos.entry_ask:.4f}",
        "shares": f"{pos.shares:.4f}",
        "start_price": f"{pos.start_price:.2f}",
        "entry_price_btc": f"{pos.entry_price_btc:.2f}",
        "start_ts": str(pos.start_ts),
        "end_ts": str(pos.end_ts),
        "opened_at": str(pos.opened_at),
        "status": pos.status,
        "result": "",
        "exit_price_btc": "",
        "pnl": "",
        "url": f"https://polymarket.com/event/{pos.slug}",
    }
    if extra:
        row.update(extra)
    append_csv(path, row)


def mark_resolutions(args: argparse.Namespace, positions: dict[str, SimPosition]) -> None:
    now = int(time.time())
    for pos in list(positions.values()):
        if now <= pos.end_ts + args.resolve_delay:
            continue
        exit_price = binance_open_price(pos.end_ts) or btc_price()
        winning_direction = "UP" if exit_price >= pos.start_price else "DOWN"
        win = pos.direction == winning_direction
        pnl = pos.shares - pos.stake if win else -pos.stake
        pos.status = "RESOLVED"
        write_position(
            args.trades_log,
            pos,
            {
                "status": "RESOLVED",
                "result": "WIN" if win else "LOSS",
                "exit_price_btc": f"{exit_price:.2f}",
                "pnl": f"{pnl:.4f}",
            },
        )
        del positions[pos.id]
        print(
            f"BTC模拟结算：{pos.direction} {'赢' if win else '输'} | "
            f"盈亏 {pnl:.2f}U | {pos.question}",
            flush=True,
        )


def maybe_open_position(args: argparse.Namespace, market: BtcMarket, positions: dict[str, SimPosition]) -> None:
    now = int(time.time())
    if now < market.start_ts + args.min_seconds_after_start:
        return
    if now > market.end_ts - args.min_seconds_before_end:
        return

    start_price = binance_open_price(market.start_ts)
    if start_price is None:
        return
    prices = reference_prices()
    if len(prices) < args.min_price_sources:
        return
    current, source_spread_bps = consensus_price(prices)
    if source_spread_bps > args.max_source_spread_bps:
        return
    move_bps = (current / start_price - 1.0) * 10000

    up_ask, down_ask = best_asks(market)
    if up_ask is None or down_ask is None:
        return
    pm_edge_bps = abs(move_bps) - abs((up_ask - down_ask) * 100)
    if pm_edge_bps < args.min_pm_lag_bps:
        return
    direction = None
    ask = None
    token_id = None
    if move_bps >= args.min_move_bps and up_ask <= args.max_entry_price:
        direction, ask, token_id = "UP", up_ask, market.up_token
    elif move_bps <= -args.min_move_bps and down_ask <= args.max_entry_price:
        direction, ask, token_id = "DOWN", down_ask, market.down_token
    else:
        return

    same_market = [pos for pos in positions.values() if pos.slug == market.slug]
    if any(pos.direction != direction for pos in same_market):
        return
    same_direction = [pos for pos in same_market if pos.direction == direction]
    if len(same_direction) >= args.max_entries_per_market:
        return
    if same_direction and now - max(pos.opened_at for pos in same_direction) < args.entry_cooldown:
        return
    required_move = args.min_move_bps + len(same_direction) * args.add_entry_move_bps
    if abs(move_bps) < required_move:
        return

    key = position_key(market.slug, direction)
    stake = min(args.stake_usdc, args.bankroll_usdc)
    shares = stake / ask
    pos = SimPosition(
        id=key,
        slug=market.slug,
        question=market.question,
        direction=direction,
        token_id=token_id,
        stake=stake,
        entry_ask=ask,
        shares=shares,
        start_price=start_price,
        entry_price_btc=current,
        start_ts=market.start_ts,
        end_ts=market.end_ts,
        opened_at=now,
    )
    positions[key] = pos
    write_position(args.trades_log, pos)
    alert = (
        f"BTC SIGNAL\n"
        f"time: {datetime.now(timezone.utc).isoformat()}\n"
        f"direction: {direction}\n"
        f"stake: {stake:.2f} USDC\n"
        f"entry_ask: {ask:.4f}\n"
        f"move_bps: {move_bps:.2f}\n"
        f"source_spread_bps: {source_spread_bps:.2f}\n"
        f"pm_edge_bps: {pm_edge_bps:.2f}\n"
        f"sources: {json.dumps(prices)}\n"
        f"start_price: {start_price:.2f}\n"
        f"current_price: {current:.2f}\n"
        f"market: {market.question}\n"
        f"url: {market.url}\n"
    )
    args.alert_file.write_text(alert, encoding="utf-8")
    print(
        f"BTC模拟开仓：{direction} | {stake:.2f}U @ {ask:.3f} | "
        f"BTC波动 {move_bps:.1f} bps | 源价差 {source_spread_bps:.1f} bps | "
        f"盘口滞后 {pm_edge_bps:.1f} bps | {market.question}",
        flush=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--lookahead-seconds", type=int, default=1800)
    parser.add_argument("--durations", default="5m,15m,4h")
    parser.add_argument("--min-move-bps", type=float, default=8.0)
    parser.add_argument("--min-price-sources", type=int, default=2)
    parser.add_argument("--max-source-spread-bps", type=float, default=8.0)
    parser.add_argument("--min-pm-lag-bps", type=float, default=0.0)
    parser.add_argument("--max-entry-price", type=float, default=0.68)
    parser.add_argument("--stake-usdc", type=float, default=5.0)
    parser.add_argument("--bankroll-usdc", type=float, default=1000.0)
    parser.add_argument("--max-entries-per-market", type=int, default=5)
    parser.add_argument("--entry-cooldown", type=int, default=30)
    parser.add_argument("--add-entry-move-bps", type=float, default=4.0)
    parser.add_argument("--min-seconds-after-start", type=int, default=20)
    parser.add_argument("--min-seconds-before-end", type=int, default=35)
    parser.add_argument("--resolve-delay", type=int, default=20)
    parser.add_argument("--refresh-markets-every", type=int, default=12)
    parser.add_argument("--max-scans", type=int, default=0)
    parser.add_argument("--trades-log", type=Path, default=Path("btc_signal_trades.csv"))
    parser.add_argument("--alert-file", type=Path, default=Path("latest_btc_signal.txt"))
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    durations = {item.strip() for item in args.durations.split(",") if item.strip()}
    positions = load_open_positions(args.trades_log)
    markets: list[BtcMarket] = []
    scan = 0
    while True:
        scan += 1
        try:
            if not markets or scan % args.refresh_markets_every == 1:
                markets = discover_markets(args.lookahead_seconds, durations=durations)
            now = int(time.time())
            active = [m for m in markets if m.start_ts <= now <= m.end_ts]
            upcoming = [m for m in markets if now < m.start_ts <= now + args.lookahead_seconds]
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] BTC第{scan}次扫描 | "
                f"当前窗口 {len(active)} 个 | 即将开始 {len(upcoming)} 个 | 持仓 {len(positions)} 个",
                flush=True,
            )
            for market in active:
                maybe_open_position(args, market, positions)
            mark_resolutions(args, positions)
        except KeyboardInterrupt:
            print("Stopped.", flush=True)
            return 130
        except Exception as exc:
            print(f"BTC模拟错误：{exc}", file=sys.stderr, flush=True)
        if args.max_scans and scan >= args.max_scans:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
