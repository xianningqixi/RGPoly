#!/usr/bin/env python3
"""Simulate copy-following selected weather-specialist Polymarket wallets.

Read-only. This never places orders. It watches public activity from selected
wallets and creates small simulated copy trades for temperature/weather markets.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from portfolio_risk import portfolio_open_exposure
from trade_audit import ensure_audit_open, order_snapshot, signal_time_from_epoch, update_audit_marks


DATA_API = "https://data-api.polymarket.com/activity"
GAMMA_MARKETS = "https://gamma-api.polymarket.com/markets"

DEFAULT_WALLETS = {
    "ColdMath": "0x594edb9112f526fa6a80b8f858a6379c8a2c1c11",
    "HondaCivic": "0x15ceffed7bf820cd2d90f90ea24ae9909f5cd5fa",
    "NoonienSoong": "0x38cc1d1f95d12039324809d8bb6ca6da6cbef88e",
    "Railbird": "0x906f2454a777600aea6c506247566decef82371a",
    "BeefSlayer": "0x331bf91c132af9d921e1908ca0979363fc47193f",
    "dpnd": "0x5f211a24da4c005d9438a1ea269673b85ed0b376",
    "JoeTheMeteorologist": "0x1838cca016850ac7185a9b149fe7d0bd2d6629b4",
    "Poligarch": "0xb40e89677d59665d5188541ad860450a6e2a7cc9",
    "HenryTheAtmoPhD": "0x57ee70867b4e387de9de34fd62bc685aa02a8112",
    "neobrother": "0x6297b93ea37ff92a57fd636410f3b71ebf74517e",
}

DEFAULT_BLOCKED_WALLETS = {
    "Railbird",
    "Poligarch",
    "HenryTheAtmoPhD",
    "HondaCivic",
    "JoeTheMeteorologist",
    "dpnd",
    "neobrother",
}

DEFAULT_OBSERVATION_WALLETS = {
    "ColdMath",
    "NoonienSoong",
    "BeefSlayer",
}

CHANGE_POINTS = Path("strategy_change_points.csv")


def fnum(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def price_bucket(value: float) -> str:
    if value <= 0:
        return "unknown"
    low = int(value * 10) / 10
    return f"{low:.1f}-{low + 0.1:.1f}"


def parse_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def latest_strategy_cutoff(strategy: str) -> datetime | None:
    if not CHANGE_POINTS.exists():
        return None
    latest: datetime | None = None
    with CHANGE_POINTS.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            if row.get("strategy") != strategy:
                continue
            ts = parse_ts(row.get("cutoff_ts"))
            if ts and (latest is None or ts > latest):
                latest = ts
    return latest


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def http_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Connection": "close"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            time.sleep(0.6 * (attempt + 1))
    raise last_error or RuntimeError(f"request failed: {url}")


def fetch_activity(wallet: str, limit: int) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"user": wallet, "limit": limit, "offset": 0})
    data = http_json(f"{DATA_API}?{query}")
    return data if isinstance(data, list) else []


def market_by_slug(slug: str) -> dict[str, Any] | None:
    if not slug:
        return None
    query = urllib.parse.urlencode({"slug": slug})
    data = http_json(f"{GAMMA_MARKETS}?{query}")
    if isinstance(data, list) and data:
        return data[0]
    data = http_json(f"https://gamma-api.polymarket.com/events?{query}")
    if isinstance(data, list) and data:
        markets = data[0].get("markets") or []
        for market in markets:
            if market.get("slug") == slug:
                return market
    parts = slug.split("-")
    for idx in range(len(parts) - 1, 4, -1):
        event_slug = "-".join(parts[:idx])
        query = urllib.parse.urlencode({"slug": event_slug})
        data = http_json(f"https://gamma-api.polymarket.com/events?{query}")
        if not (isinstance(data, list) and data):
            continue
        for market in data[0].get("markets") or []:
            if market.get("slug") == slug:
                return market
    return None


def latest_price(slug: str, outcome: str) -> float | None:
    market = market_by_slug(slug)
    if not market:
        return None
    try:
        outcomes = json.loads(market.get("outcomes") or "[]")
        prices = json.loads(market.get("outcomePrices") or "[]")
    except json.JSONDecodeError:
        return None
    for name, price in zip(outcomes, prices):
        if str(name).lower() == outcome.lower():
            return fnum(price)
    return None


def is_weather_trade(row: dict[str, Any]) -> bool:
    text = f"{row.get('title', '')} {row.get('slug', '')} {row.get('eventSlug', '')}".lower()
    markers = [
        "highest temperature",
        "lowest temperature",
        "temperature in",
        "weather",
        "hottest",
        "coldest",
    ]
    return any(marker in text for marker in markers)


def source_id(wallet_name: str, row: dict[str, Any]) -> str:
    tx = row.get("tx") or row.get("transactionHash") or ""
    return ":".join(
        [
            wallet_name,
            str(tx),
            str(row.get("slug") or ""),
            str(row.get("side") or ""),
            str(row.get("outcome") or ""),
            str(row.get("timestamp") or ""),
            str(row.get("usdcSize") or ""),
        ]
    )


def read_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data if isinstance(data, list) else [])
    except Exception:
        return set()


def write_seen(path: Path, seen: set[str]) -> None:
    path.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")


def read_latest_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    latest: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            latest[row["id"]] = row
    return latest


def row_time(row: dict[str, str]) -> datetime | None:
    for key in ("ts", "detected_time", "audit_ts", "signal_time"):
        ts = parse_ts(row.get(key))
        if ts:
            return ts
    return None


def append_row(path: Path, row: dict[str, Any]) -> None:
    fields = [
        "ts",
        "id",
        "wallet_name",
        "wallet",
        "source_timestamp",
        "action",
        "outcome",
        "source_side",
        "source_price",
        "sim_entry_price",
        "stake",
        "shares",
        "source_usdc",
        "title",
        "slug",
        "event_slug",
        "status",
        "result",
        "current_price",
        "pnl",
        "url",
    ]
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in fields})


def append_reject(args: argparse.Namespace, wallet_name: str, row: dict[str, Any], reason: str, extra: dict[str, Any] | None = None) -> None:
    path = args.reject_log
    fields = [
        "ts",
        "wallet_name",
        "id",
        "reason",
        "slug",
        "title",
        "outcome",
        "source_price",
        "source_usdc",
        "signal_age_sec",
        "best_ask",
        "ask_depth_usdc",
        "slippage_bps",
        "source_to_ask_gap",
    ]
    exists = path.exists()
    data = extra or {}
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "ts": now_utc(),
                "wallet_name": wallet_name,
                "id": source_id(wallet_name, row),
                "reason": reason,
                "slug": row.get("slug") or "",
                "title": row.get("title") or "",
                "outcome": row.get("outcome") or "",
                "source_price": f"{fnum(row.get('price')):.6f}",
                "source_usdc": f"{fnum(row.get('usdcSize')):.4f}",
                "signal_age_sec": f"{time.time() - fnum(row.get('timestamp')):.2f}",
                "best_ask": data.get("best_ask", ""),
                "ask_depth_usdc": data.get("ask_depth_usdc", ""),
                "slippage_bps": data.get("slippage_bps", ""),
                "source_to_ask_gap": data.get("source_to_ask_gap", ""),
            }
        )


def should_copy_reason(row: dict[str, Any], args: argparse.Namespace) -> str:
    if row.get("type") != "TRADE":
        return "not_trade"
    if row.get("side") != "BUY":
        return "not_buy"
    if str(row.get("outcome") or "") not in {"Yes", "No"}:
        return "bad_outcome"
    if args.allowed_outcome and str(row.get("outcome") or "") not in args.allowed_outcome:
        return "outcome_not_allowed"
    if not is_weather_trade(row):
        return "not_weather"
    signal_age = time.time() - fnum(row.get("timestamp"))
    if signal_age < 0 or signal_age > args.max_source_age_sec:
        return "source_too_old"
    source_usdc = fnum(row.get("usdcSize"))
    source_price = fnum(row.get("price"))
    if source_usdc < args.min_source_usdc:
        return "source_size_too_small"
    if source_price < args.min_source_price or source_price > args.max_source_price:
        return "source_price_out_of_range"
    if args.allowed_price_bucket and price_bucket(source_price) not in args.allowed_price_bucket:
        return "price_bucket_not_allowed"
    return "TAKE"


def should_copy(row: dict[str, Any], args: argparse.Namespace) -> bool:
    return should_copy_reason(row, args) == "TAKE"


def market_exposure(
    log_path: Path,
    slug: str,
    event_slug: str,
    wallet_name: str,
    outcome: str,
    cutoff: datetime | None,
) -> tuple[float, float, int]:
    latest = read_latest_rows(log_path)
    market_stake = 0.0
    event_stake = 0.0
    wallet_market_count = 0
    for row in latest.values():
        if row.get("status") not in {"OPEN", "MARK"}:
            continue
        row_ts = row_time(row)
        if cutoff and row_ts and row_ts < cutoff:
            continue
        if event_slug and row.get("event_slug") == event_slug:
            event_stake += fnum(row.get("stake"))
        if row.get("slug") == slug:
            market_stake += fnum(row.get("stake"))
            if row.get("wallet_name") == wallet_name and row.get("outcome") == outcome:
                wallet_market_count += 1
    return market_stake, event_stake, wallet_market_count


def open_exposure(log_path: Path, cutoff: datetime | None) -> tuple[int, float]:
    latest = read_latest_rows(log_path)
    open_count = 0
    open_stake = 0.0
    for row in latest.values():
        if row.get("status") not in {"OPEN", "MARK"}:
            continue
        row_ts = row_time(row)
        if cutoff and row_ts and row_ts < cutoff:
            continue
        open_count += 1
        open_stake += fnum(row.get("stake"))
    return open_count, open_stake


def realized_pnl(log_path: Path, cutoff: datetime | None) -> float:
    latest = read_latest_rows(log_path)
    pnl = 0.0
    for row in latest.values():
        row_ts = row_time(row)
        if cutoff and row_ts and row_ts < cutoff:
            continue
        if (row.get("status") or "").upper() != "FINAL":
            continue
        pnl_value = row.get("slippage_final_pnl")
        pnl += fnum(pnl_value if pnl_value not in (None, "") else row.get("final_pnl"))
    return pnl


def wallet_allowed(wallet_name: str, args: argparse.Namespace) -> bool:
    if args.allowed_wallet and wallet_name not in args.allowed_wallet:
        print(f"skip weather signal: wallet not in allowlist | {wallet_name}", flush=True)
        return False
    if not args.allowed_wallet and wallet_name in args.blocked_wallet:
        print(f"skip weather signal: blocked wallet | {wallet_name}", flush=True)
        return False
    return True


def direction_allowed(wallet_name: str, outcome: str, source_price: float, args: argparse.Namespace) -> bool:
    if not args.allowed_wallet_direction:
        return True
    allowed = args.allowed_wallet_direction.get(wallet_name, set())
    if not allowed:
        return False
    return f"{outcome}:{price_bucket(source_price)}" in allowed


def wallet_stake(wallet_name: str, args: argparse.Namespace) -> float:
    if wallet_name in DEFAULT_OBSERVATION_WALLETS:
        return min(args.stake_usdc, args.observation_stake_usdc)
    return args.stake_usdc


def open_copy(wallet_name: str, wallet: str, row: dict[str, Any], args: argparse.Namespace) -> bool:
    if not wallet_allowed(wallet_name, args):
        return False
    cutoff = latest_strategy_cutoff(args.strategy_key)
    open_count, open_stake = open_exposure(args.audit_log, cutoff)
    portfolio_count, portfolio_stake = portfolio_open_exposure([args.audit_log]) if args.isolated_portfolio_risk else portfolio_open_exposure()
    if portfolio_stake >= args.bankroll_usdc:
        append_reject(args, wallet_name, row, "portfolio_bankroll_full")
        print(
            f"跳过天气钱包信号：模拟仓总本金已满 {portfolio_stake:.2f}U/{args.bankroll_usdc:.2f}U "
            f"({portfolio_count}笔未结算) | {wallet_name} | {row.get('title')}",
            flush=True,
        )
        return False
    if open_stake >= args.bankroll_usdc:
        append_reject(args, wallet_name, row, "bankroll_exposure_full")
        print(f"跳过天气钱包信号：模拟本金已满 {open_stake:.2f}U/{args.bankroll_usdc:.2f}U | {wallet_name} | {row.get('title')}", flush=True)
        return False
    if open_count >= args.max_open_positions:
        append_reject(args, wallet_name, row, "open_position_cap_full")
        print(f"跳过天气钱包信号：全局未结算仓位已满 {open_count}笔/{open_stake:.2f}U | {wallet_name} | {row.get('title')}", flush=True)
        return False
    source_price = fnum(row.get("price"))
    slug = str(row.get("slug") or "")
    outcome = str(row.get("outcome") or "")
    if not direction_allowed(wallet_name, outcome, source_price, args):
        append_reject(args, wallet_name, row, "wallet_direction_not_allowed")
        return False
    desired_stake = wallet_stake(wallet_name, args)
    realized_buffer = realized_pnl(args.audit_log, cutoff)
    required_buffer = max(0.0, args.min_realized_pnl_buffer_usdc)
    if required_buffer > 0 and realized_buffer < required_buffer:
        append_reject(
            args,
            wallet_name,
            row,
            "realized_profit_buffer_low",
            {"best_ask": "", "ask_depth_usdc": "", "slippage_bps": "", "source_to_ask_gap": ""},
        )
        print(
            f"跳过天气钱包信号：已落袋利润缓冲不足 {realized_buffer:.2f}U/{required_buffer:.2f}U "
            f"| {wallet_name} | {row.get('title')}",
            flush=True,
        )
        return False
    event_slug = str(row.get("eventSlug") or "")
    market_stake, event_stake, wallet_market_count = market_exposure(
        args.audit_log, slug, event_slug, wallet_name, outcome, cutoff
    )
    if market_stake >= args.max_market_stake_usdc:
        append_reject(args, wallet_name, row, "market_exposure_full")
        print(f"跳过天气钱包信号：单市场模拟暴露已满 {market_stake:.2f}U | {wallet_name} | {row.get('title')}", flush=True)
        return False
    if event_stake >= args.max_event_stake_usdc:
        append_reject(args, wallet_name, row, "event_exposure_full")
        print(f"skip weather signal: event exposure full {event_stake:.2f}U | {wallet_name} | {row.get('title')}", flush=True)
        return False
    if wallet_market_count >= args.max_wallet_market_entries:
        append_reject(args, wallet_name, row, "wallet_market_entries_full")
        print(f"跳过天气钱包信号：同钱包同市场重复过多 {wallet_market_count}次 | {wallet_name} | {row.get('title')}", flush=True)
        return False
    current = latest_price(slug, outcome)
    entry = current if current and current > 0 else source_price
    if entry <= 0:
        return False
    if entry < args.min_entry_price or entry > args.max_entry_price:
        append_reject(args, wallet_name, row, "entry_price_out_of_range")
        print(f"skip weather signal: entry price out of range {entry:.3f} | {wallet_name} | {row.get('title')}", flush=True)
        return False

    stake = min(
        desired_stake,
        args.bankroll_usdc,
        max(0.0, args.bankroll_usdc - portfolio_stake),
        max(0.0, args.bankroll_usdc - open_stake),
        max(0.0, args.max_market_stake_usdc - market_stake),
        max(0.0, args.max_event_stake_usdc - event_stake),
    )
    if stake <= 0:
        return False
    trade_id = source_id(wallet_name, row)
    url = f"https://polymarket.com/event/{event_slug}" if event_slug else ""
    market = market_by_slug(slug)
    try:
        snapshot = order_snapshot(market, outcome, stake) if market else {}
    except Exception:
        snapshot = {}
    fill_price = fnum(snapshot.get("sim_fill_price")) or entry
    best_ask = fnum(snapshot.get("best_ask"))
    ask_depth_usdc = fnum(snapshot.get("ask_depth_usdc"))
    would_live_fill = bool(snapshot.get("would_live_fill"))
    slippage_bps = ((fill_price - source_price) / source_price * 10000) if source_price > 0 else 0.0
    source_to_ask_gap = best_ask - source_price if best_ask > 0 and source_price > 0 else 999.0
    historical_q = direction_q(wallet_name, outcome, source_price, args)
    reject_extra = {
        "best_ask": f"{best_ask:.6f}",
        "ask_depth_usdc": f"{ask_depth_usdc:.4f}",
        "slippage_bps": f"{slippage_bps:.2f}",
        "source_to_ask_gap": f"{source_to_ask_gap:.6f}",
    }
    if historical_q is not None:
        reject_extra["historical_q"] = f"{historical_q:.6f}"
        reject_extra["direction_edge"] = f"{historical_q - fill_price:.6f}"
    if args.require_live_fill and not would_live_fill:
        append_reject(args, wallet_name, row, "insufficient_book_depth", reject_extra)
        print(f"跳过天气钱包信号：盘口深度不足 | {wallet_name} | {row.get('title')}", flush=True)
        return False
    if ask_depth_usdc < args.min_ask_depth_usdc:
        append_reject(args, wallet_name, row, "ask_depth_too_low", reject_extra)
        print(f"跳过天气钱包信号：ask深度不足 {ask_depth_usdc:.2f}U | {wallet_name} | {row.get('title')}", flush=True)
        return False
    if slippage_bps > args.max_slippage_bps:
        append_reject(args, wallet_name, row, "slippage_too_high", reject_extra)
        print(f"跳过天气钱包信号：滑点过高 {slippage_bps:.0f}bps | {wallet_name} | {row.get('title')}", flush=True)
        return False
    if source_to_ask_gap > args.max_source_to_ask_gap:
        append_reject(args, wallet_name, row, "source_to_ask_gap_too_wide", reject_extra)
        print(f"跳过天气钱包信号：源价到ask差距 {source_to_ask_gap:.3f} | {wallet_name} | {row.get('title')}", flush=True)
        return False
    if historical_q is not None and fill_price > historical_q - args.min_direction_edge:
        append_reject(args, wallet_name, row, "direction_edge_too_small", reject_extra)
        print(
            f"跳过天气方向信号：历史胜率边际不足 q={historical_q:.3f} fill={fill_price:.3f} | {wallet_name} | {row.get('title')}",
            flush=True,
        )
        return False
    entry = fill_price
    shares = fnum(snapshot.get("sim_shares")) or (stake / entry if entry > 0 else 0.0)
    ensure_audit_open(
        args.audit_log,
        trade_id=trade_id,
        strategy=args.strategy_key,
        wallet_name=wallet_name,
        signal_time=signal_time_from_epoch(row.get("timestamp")),
        title=str(row.get("title") or ""),
        slug=slug,
        event_slug=event_slug,
        outcome=outcome,
        stake=stake,
        source_price=source_price,
        market=market,
        extra={
            "best_bid": snapshot.get("best_bid"),
            "best_ask": snapshot.get("best_ask"),
            "ask_depth_shares": snapshot.get("ask_depth_shares"),
            "ask_depth_usdc": snapshot.get("ask_depth_usdc"),
            "sim_fill_price": fill_price,
            "sim_shares": shares,
            "would_live_fill": "YES" if would_live_fill else "NO",
            "estimated_q": f"{historical_q:.6f}" if historical_q is not None else "",
            "ev": f"{(historical_q - fill_price):.6f}" if historical_q is not None else "",
            "price_bucket": price_bucket(source_price),
            "recommended_stake": f"{stake:.4f}",
        },
    )
    append_row(
        args.log,
        {
            "ts": now_utc(),
            "id": trade_id,
            "wallet_name": wallet_name,
            "wallet": wallet,
            "source_timestamp": row.get("timestamp"),
            "action": "COPY_BUY",
            "outcome": outcome,
            "source_side": row.get("side"),
            "source_price": f"{source_price:.6f}",
            "sim_entry_price": f"{entry:.6f}",
            "stake": f"{stake:.4f}",
            "shares": f"{shares:.4f}",
            "source_usdc": f"{fnum(row.get('usdcSize')):.4f}",
            "title": row.get("title"),
            "slug": slug,
            "event_slug": event_slug,
            "status": "OPEN",
            "url": url,
        },
    )
    alert = (
        "WEATHER WALLET COPY SIM\n"
        f"time: {now_utc()}\n"
        f"wallet: {wallet_name}\n"
        f"stake: {stake:.2f}U\n"
        f"outcome: {outcome}\n"
        f"entry_price: {entry:.4f}\n"
        f"slippage_bps: {slippage_bps:.0f}\n"
        f"ask_depth_usdc: {ask_depth_usdc:.2f}U\n"
        f"source_usdc: {fnum(row.get('usdcSize')):.2f}U\n"
        f"market: {row.get('title')}\n"
        f"url: {url}\n"
    )
    args.alert_file.write_text(alert, encoding="utf-8")
    print(
        f"天气钱包跟单模拟开仓：{wallet_name} {outcome} {stake:.2f}U @ {entry:.3f} | {row.get('title')}",
        flush=True,
    )
    return True


def update_open_rows(args: argparse.Namespace) -> None:
    latest = read_latest_rows(args.log)
    for row in latest.values():
        if row.get("status") != "OPEN":
            continue
        current = latest_price(row.get("slug") or "", row.get("outcome") or "")
        if current is None:
            continue
        stake = fnum(row.get("stake"))
        shares = fnum(row.get("shares"))
        pnl = shares * current - stake
        append_row(
            args.log,
            {
                **row,
                "ts": now_utc(),
                "status": "MARK",
                "result": "MARK",
                "current_price": f"{current:.6f}",
                "pnl": f"{pnl:.4f}",
            },
        )


def parse_wallets(values: list[str]) -> dict[str, str]:
    wallets = dict(DEFAULT_WALLETS)
    for value in values:
        if "=" not in value:
            raise ValueError("--wallet must be Name=0x...")
        name, wallet = value.split("=", 1)
        wallets[name.strip()] = wallet.strip().lower()
    return wallets


def parse_wallet_directions(values: list[str]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--allowed-wallet-direction must be Name=Outcome:bucket")
        name, spec = value.split("=", 1)
        name = name.strip()
        spec = spec.strip()
        if not name or ":" not in spec:
            raise ValueError("--allowed-wallet-direction must be Name=Outcome:bucket")
        out.setdefault(name, set()).add(spec)
    return out


def parse_wallet_direction_q(values: list[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--wallet-direction-q must be Name=Outcome:bucket:q")
        name, spec = value.split("=", 1)
        parts = spec.strip().split(":")
        if len(parts) != 3:
            raise ValueError("--wallet-direction-q must be Name=Outcome:bucket:q")
        outcome, bucket, q_text = parts
        out[f"{name.strip()}={outcome}:{bucket}"] = fnum(q_text)
    return out


def direction_q(wallet_name: str, outcome: str, source_price: float, args: argparse.Namespace) -> float | None:
    key = f"{wallet_name}={outcome}:{price_bucket(source_price)}"
    value = args.wallet_direction_q.get(key)
    return value if value and value > 0 else None


def active_wallets(wallets: dict[str, str], args: argparse.Namespace) -> dict[str, str]:
    if args.allowed_wallet:
        return {name: wallet for name, wallet in wallets.items() if name in args.allowed_wallet}
    return {name: wallet for name, wallet in wallets.items() if name not in args.blocked_wallet}


PERMANENT_SEEN_REASONS = {
    "not_trade",
    "not_buy",
    "bad_outcome",
    "not_weather",
    "source_too_old",
    "source_size_too_small",
    "source_price_out_of_range",
    "outcome_not_allowed",
    "price_bucket_not_allowed",
    "wallet_direction_not_allowed",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wallet", action="append", default=[], help="Extra wallet as Name=0x...")
    parser.add_argument("--strategy-key", default="weather_wallet_copy")
    parser.add_argument("--interval", type=float, default=45.0)
    parser.add_argument("--activity-limit", type=int, default=80)
    parser.add_argument("--stake-usdc", type=float, default=5.0)
    parser.add_argument("--observation-stake-usdc", type=float, default=1.0)
    parser.add_argument("--bankroll-usdc", type=float, default=1000.0)
    parser.add_argument("--min-source-usdc", type=float, default=50.0)
    parser.add_argument("--min-source-price", type=float, default=0.01)
    parser.add_argument("--max-source-price", type=float, default=0.995)
    parser.add_argument("--allowed-outcome", action="append", default=[])
    parser.add_argument("--allowed-price-bucket", action="append", default=[])
    parser.add_argument("--allowed-wallet-direction", action="append", default=[])
    parser.add_argument("--wallet-direction-q", action="append", default=[])
    parser.add_argument("--min-direction-edge", type=float, default=0.005)
    parser.add_argument("--min-entry-price", type=float, default=0.01)
    parser.add_argument("--max-entry-price", type=float, default=0.995)
    parser.add_argument("--max-slippage-bps", type=float, default=300.0)
    parser.add_argument("--min-ask-depth-usdc", type=float, default=20.0)
    parser.add_argument("--max-source-to-ask-gap", type=float, default=0.03)
    parser.add_argument("--max-source-age-sec", type=float, default=15.0)
    parser.add_argument("--max-market-stake-usdc", type=float, default=5.0)
    parser.add_argument("--max-event-stake-usdc", type=float, default=5.0)
    parser.add_argument("--max-wallet-market-entries", type=int, default=1)
    parser.add_argument("--max-open-positions", type=int, default=100)
    parser.add_argument("--min-realized-pnl-buffer-usdc", type=float, default=0.0)
    parser.add_argument("--mark-every-scans", type=int, default=12)
    parser.add_argument("--blocked-wallet", action="append", default=sorted(DEFAULT_BLOCKED_WALLETS))
    parser.add_argument("--allowed-wallet", action="append", default=[])
    parser.add_argument("--require-live-fill", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--log", type=Path, default=Path("weather_wallet_copy_sim.csv"))
    parser.add_argument("--audit-log", type=Path, default=Path("weather_wallet_trade_audit.csv"))
    parser.add_argument("--reject-log", type=Path, default=Path("weather_wallet_rejects.csv"))
    parser.add_argument("--seen", type=Path, default=Path("weather_wallet_seen.json"))
    parser.add_argument("--alert-file", type=Path, default=Path("latest_weather_wallet_copy_alert.txt"))
    parser.add_argument("--live-only", action="store_true", help="Initialize seen set without opening historical trades.")
    parser.add_argument("--max-audit-updates", type=int, default=100)
    parser.add_argument("--once", action="store_true", help="Run one scan loop and exit.")
    parser.add_argument("--isolated-portfolio-risk", action="store_true", help="Use only this audit log for bankroll exposure checks.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.allowed_outcome = {item.strip() for item in args.allowed_outcome if item.strip()}
    args.allowed_price_bucket = {item.strip() for item in args.allowed_price_bucket if item.strip()}
    args.allowed_wallet_direction = parse_wallet_directions(args.allowed_wallet_direction)
    args.wallet_direction_q = parse_wallet_direction_q(args.wallet_direction_q)
    wallets = parse_wallets(args.wallet)
    args.blocked_wallet = set(args.blocked_wallet or [])
    args.allowed_wallet = set(args.allowed_wallet or [])
    wallets = active_wallets(wallets, args)
    seen = read_seen(args.seen)
    initialized = bool(seen)
    scan = 0

    while True:
        try:
            scan += 1
            opened = 0
            scanned = 0
            fresh_seen = set(seen)
            for wallet_name, wallet in wallets.items():
                try:
                    rows = fetch_activity(wallet, args.activity_limit)
                except Exception as exc:
                    print(f"weather wallet activity error: {wallet_name} | {exc}", flush=True)
                    continue
                scanned += len(rows)
                for row in rows:
                    sid = source_id(wallet_name, row)
                    if sid in seen:
                        continue
                    if args.live_only and not initialized:
                        fresh_seen.add(sid)
                        continue
                    reason = should_copy_reason(row, args)
                    if reason != "TAKE":
                        if reason not in {"not_trade", "not_buy", "bad_outcome", "not_weather"}:
                            append_reject(args, wallet_name, row, reason)
                        if reason in PERMANENT_SEEN_REASONS:
                            fresh_seen.add(sid)
                        continue
                    if open_copy(wallet_name, wallet, row, args):
                        fresh_seen.add(sid)
                        opened += 1
                time.sleep(0.15)
            seen = fresh_seen
            write_seen(args.seen, seen)
            initialized = True
            if args.mark_every_scans > 0 and scan % args.mark_every_scans == 0:
                update_open_rows(args)
                update_audit_marks(args.audit_log, market_by_slug, max_rows=args.max_audit_updates)
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 天气钱包模拟扫描 | 钱包 {len(wallets)} 个 | activity {scanned} 条 | 新开仓 {opened} 条",
                flush=True,
            )
            if args.once:
                return 0
        except KeyboardInterrupt:
            return 130
        except Exception as exc:
            print(f"天气钱包模拟错误：{exc}", flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
