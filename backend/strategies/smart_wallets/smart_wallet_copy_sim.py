#!/usr/bin/env python3
"""Simulate copy-following selected crypto short-window Polymarket wallets.

Read-only. Watches public activity for selected wallets and simulates small
copy BUYs on BTC/ETH/SOL/XRP Up/Down markets.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from portfolio_risk import portfolio_open_exposure
from trade_audit import ensure_audit_open, order_snapshot, signal_time_from_epoch, update_audit_marks


WATCH_WALLETS = {
    "0x8dxd": "0x63ce342161250d705dc0b16df89036c8e5f9ba9a",
    "0xe1d6": "0xe1d6b51521bd4365769199f392f9818661bd907c",
    "xuanxuan008": "0xcfb103c37c0234f524c632d964ed31f117b5f694",
    "ohanism": "0x89b5cdaaa4866c1e738406712012a630b4078beb",
    "creamcream_crypto": "0xce25e214d5cfe4f459cf67f08df581885aae7fdc",
    "creamcream_btc_5m": "0x04b6d7e930cf9e493c5e6ef24b496294f95594c8",
}


def http_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Connection": "close"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            time.sleep(0.4 * (attempt + 1))
    raise last_error or RuntimeError(f"request failed: {url}")


def fnum(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def fetch_recent(wallet: str, limit: int) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"user": wallet, "limit": limit, "offset": 0})
    data = http_json(f"https://data-api.polymarket.com/activity?{query}")
    return data if isinstance(data, list) else []


def is_crypto_updown(row: dict[str, Any]) -> bool:
    text = f"{row.get('title', '')} {row.get('slug', '')} {row.get('eventSlug', '')}".lower()
    names = ["bitcoin up or down", "ethereum up or down", "solana up or down", "xrp up or down"]
    slugs = ["btc-updown", "eth-updown", "sol-updown", "xrp-updown"]
    return any(name in text for name in names) or any(slug in text for slug in slugs)


def window_type(row: dict[str, Any]) -> str:
    text = f"{row.get('slug', '')} {row.get('eventSlug', '')}".lower()
    if "5m" in text:
        return "5m"
    if "15m" in text:
        return "15m"
    if "4h" in text:
        return "4h"
    return "other"


def asset_type(row: dict[str, Any]) -> str:
    text = f"{row.get('title', '')} {row.get('slug', '')} {row.get('eventSlug', '')}".lower()
    if "ethereum" in text or "eth-updown" in text:
        return "ETH"
    if "bitcoin" in text or "btc-updown" in text:
        return "BTC"
    if "solana" in text or "sol-updown" in text:
        return "SOL"
    if "xrp" in text or "xrp-updown" in text:
        return "XRP"
    return "OTHER"


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
            str(row.get("usdcSize") or row.get("size") or ""),
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
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            rows[row["id"]] = row
    return rows


def append_row(path: Path, row: dict[str, Any]) -> None:
    fields = [
        "ts",
        "id",
        "wallet_name",
        "source_ts",
        "side",
        "outcome",
        "window",
        "source_price",
        "source_usdc",
        "sim_entry_price",
        "stake",
        "shares",
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
    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in fields})


def market_by_slug(slug: str) -> dict[str, Any] | None:
    query = urllib.parse.urlencode({"slug": slug})
    data = http_json(f"https://gamma-api.polymarket.com/markets?{query}")
    if isinstance(data, list) and data:
        return data[0]
    data = http_json(f"https://gamma-api.polymarket.com/events?{query}")
    if isinstance(data, list) and data:
        markets = data[0].get("markets") or []
        if markets:
            return markets[0]
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
            return float(price)
    return None


def should_copy(row: dict[str, Any], args: argparse.Namespace) -> bool:
    if row.get("type") != "TRADE":
        return False
    if row.get("side") != "BUY":
        return False
    if row.get("outcome") not in {"Up", "Down"}:
        return False
    if args.allowed_outcome and row.get("outcome") not in args.allowed_outcome:
        return False
    if not is_crypto_updown(row):
        return False
    if args.allowed_asset and asset_type(row) not in args.allowed_asset:
        return False
    if window_type(row) not in args.windows:
        return False
    signal_age = time.time() - fnum(row.get("timestamp"))
    if signal_age < 0 or signal_age > args.max_source_age_sec:
        return False
    price = fnum(row.get("price"))
    usdc = fnum(row.get("usdcSize"))
    return args.min_price <= price <= args.max_price and usdc >= args.min_source_usdc


def price_bucket(price: float) -> str:
    if price < 0.10:
        return "00-10"
    if price < 0.25:
        return "10-25"
    if price < 0.50:
        return "25-50"
    if price < 0.75:
        return "50-75"
    if price < 0.90:
        return "75-90"
    return "90-100"


def wallet_bucket_stats(audit_path: Path, wallet_name: str, bucket: str) -> tuple[int, float | None]:
    rows = read_latest_rows(audit_path)
    matched = [
        row
        for row in rows.values()
        if row.get("wallet_name") == wallet_name and row.get("price_bucket") == bucket and row.get("price_1h")
    ]
    if not matched:
        return 0, None
    wins = [row for row in matched if fnum(row.get("slippage_pnl_1h")) > 0]
    return len(matched), len(wins) / len(matched)


def market_exposure(log_path: Path, slug: str, wallet_name: str, outcome: str) -> tuple[float, int]:
    rows = read_latest_rows(log_path)
    market_stake = 0.0
    wallet_market_count = 0
    for row in rows.values():
        if row.get("slug") != slug:
            continue
        if row.get("status") not in {"OPEN", "MARK"}:
            continue
        market_stake += fnum(row.get("stake"))
        if row.get("wallet_name") == wallet_name and row.get("outcome") == outcome:
            wallet_market_count += 1
    return market_stake, wallet_market_count


def open_exposure(log_path: Path) -> tuple[int, float]:
    rows = read_latest_rows(log_path)
    count = 0
    stake = 0.0
    for row in rows.values():
        if row.get("status") not in {"OPEN", "MARK"}:
            continue
        count += 1
        stake += fnum(row.get("stake"))
    return count, stake


def recommended_stake(base: float, ev: float, sample_size: int, fill_price: float, args: argparse.Namespace) -> float:
    if ev <= 0:
        return 0.0
    confidence = min(1.0, sample_size / 50.0) if sample_size else 0.10
    multiplier = min(2.0, max(0.25, ev * 3.0 * confidence))
    stake = base * multiplier
    if fill_price < args.low_price_reduce_below:
        stake *= args.low_price_stake_factor
    return min(stake, args.max_stake_usdc)


def open_copy(wallet_name: str, row: dict[str, Any], args: argparse.Namespace) -> bool:
    price = fnum(row.get("price"))
    sid = source_id(wallet_name, row)
    slug = str(row.get("slug") or "")
    outcome = str(row.get("outcome") or "")
    open_count, open_stake = open_exposure(args.log)
    portfolio_count, portfolio_stake = portfolio_open_exposure()
    if portfolio_stake >= args.bankroll_usdc:
        print(
            f"跳过聪明钱包信号：模拟仓总本金已满 {portfolio_stake:.2f}U/{args.bankroll_usdc:.2f}U "
            f"({portfolio_count}笔未结算) | {wallet_name} | {row.get('title')}",
            flush=True,
        )
        return False
    if open_stake >= args.bankroll_usdc:
        print(f"跳过聪明钱包信号：模拟本金已满 {open_stake:.2f}U/{args.bankroll_usdc:.2f}U | {wallet_name} | {row.get('title')}", flush=True)
        return False
    if open_count >= args.max_open_positions:
        print(f"跳过聪明钱包信号：全局未结算仓位已满 {open_count}笔/{open_stake:.2f}U | {wallet_name} | {row.get('title')}", flush=True)
        return False
    market_stake, wallet_market_count = market_exposure(args.log, slug, wallet_name, outcome)
    if market_stake >= args.max_market_stake_usdc:
        print(f"跳过聪明钱包信号：单市场模拟暴露已满 {market_stake:.2f}U | {wallet_name} | {row.get('title')}", flush=True)
        return False
    if wallet_market_count >= args.max_wallet_market_entries:
        print(f"跳过聪明钱包信号：同钱包同市场重复过多 {wallet_market_count}次 | {wallet_name} | {row.get('title')}", flush=True)
        return False
    market = market_by_slug(slug)
    stake = args.stake_usdc
    try:
        snapshot = order_snapshot(market, str(row.get("outcome") or ""), stake) if market else {}
    except Exception:
        snapshot = {}
    fill_price = fnum(snapshot.get("sim_fill_price")) or price
    best_ask = fnum(snapshot.get("best_ask"))
    ask_depth_usdc = fnum(snapshot.get("ask_depth_usdc"))
    would_live_fill = bool(snapshot.get("would_live_fill"))
    slippage_bps = ((fill_price - price) / price * 10000) if price > 0 else 0.0
    source_to_ask_gap = best_ask - price if best_ask > 0 and price > 0 else 999.0
    if args.require_live_fill and not would_live_fill:
        print(f"跳过聪明钱包信号：盘口深度不足 | {wallet_name} | {row.get('title')}", flush=True)
        return False
    if ask_depth_usdc < args.min_ask_depth_usdc:
        print(f"跳过聪明钱包信号：ask深度不足 {ask_depth_usdc:.2f}U | {wallet_name} | {row.get('title')}", flush=True)
        return False
    if slippage_bps > args.max_slippage_bps:
        print(f"跳过聪明钱包信号：滑点过高 {slippage_bps:.0f}bps | {wallet_name} | {row.get('title')}", flush=True)
        return False
    if source_to_ask_gap > args.max_source_to_ask_gap:
        print(f"跳过聪明钱包信号：源价到ask差距 {source_to_ask_gap:.3f} | {wallet_name} | {row.get('title')}", flush=True)
        return False
    if fill_price < args.low_price_reduce_below and ask_depth_usdc < args.min_low_price_ask_depth_usdc:
        print(
            f"跳过聪明钱包信号：低价票深度不足 {ask_depth_usdc:.2f}U @ {fill_price:.3f} | {wallet_name} | {row.get('title')}",
            flush=True,
        )
        return False
    bucket = price_bucket(fill_price)
    sample_size, win_rate = wallet_bucket_stats(args.audit_log, wallet_name, bucket)
    has_calibrated_sample = win_rate is not None and sample_size >= args.min_ev_sample
    if not has_calibrated_sample and args.require_positive_ev:
        if fill_price < args.default_q_min_price or fill_price > args.default_q_max_price:
            print(
                f"跳过聪明钱包信号：样本不足且价格不在默认概率区间 "
                f"sample={sample_size} price={fill_price:.3f} | {wallet_name} | {row.get('title')}",
                flush=True,
            )
            return False
    estimated_q = win_rate if has_calibrated_sample else fnum(args.default_q)
    ev = estimated_q / fill_price - 1 if fill_price > 0 else -1
    stake = recommended_stake(args.stake_usdc, ev, sample_size, fill_price, args)
    stake = min(
        stake,
        max(0.0, args.bankroll_usdc - portfolio_stake),
        max(0.0, args.bankroll_usdc - open_stake),
        max(0.0, args.max_market_stake_usdc - market_stake),
    )
    if args.require_positive_ev and ev < args.min_ev:
        print(f"跳过聪明钱包信号：EV不足 {ev:.3f} | q={estimated_q:.3f} price={fill_price:.3f} | {wallet_name}", flush=True)
        return False
    if stake <= 0:
        return False
    shares = fnum(snapshot.get("sim_shares")) or (stake / fill_price if fill_price else 0.0)
    ensure_audit_open(
        args.audit_log,
        trade_id=sid,
        strategy="smart_wallet_copy",
        wallet_name=wallet_name,
        signal_time=signal_time_from_epoch(row.get("timestamp")),
        title=str(row.get("title") or ""),
        slug=str(row.get("slug") or ""),
        event_slug=str(row.get("eventSlug") or ""),
        outcome=str(row.get("outcome") or ""),
        stake=stake,
        source_price=price,
        market=market,
        extra={
            "estimated_q": f"{estimated_q:.6f}",
            "ev": f"{ev:.6f}",
            "price_bucket": bucket,
            "wallet_sample_size": str(sample_size),
            "wallet_win_rate_1h": f"{win_rate:.6f}" if win_rate is not None else "",
            "recommended_stake": f"{stake:.4f}",
        },
    )
    append_row(
        args.log,
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "id": sid,
            "wallet_name": wallet_name,
            "source_ts": row.get("timestamp"),
            "side": row.get("side"),
            "outcome": row.get("outcome"),
            "window": window_type(row),
            "source_price": f"{price:.6f}",
            "source_usdc": row.get("usdcSize"),
            "sim_entry_price": f"{fill_price:.6f}",
            "stake": f"{stake:.4f}",
            "shares": f"{shares:.4f}",
            "title": row.get("title"),
            "slug": row.get("slug"),
            "event_slug": row.get("eventSlug"),
            "status": "OPEN",
            "url": f"https://polymarket.com/event/{row.get('eventSlug')}",
        },
    )
    alert = (
        f"SMART WALLET COPY SIM\n"
        f"time: {datetime.now(timezone.utc).isoformat()}\n"
        f"wallet: {wallet_name}\n"
        f"outcome: {row.get('outcome')}\n"
        f"window: {window_type(row)}\n"
        f"entry_price: {fill_price:.4f}\n"
        f"estimated_q: {estimated_q:.4f}\n"
        f"ev: {ev:.4f}\n"
        f"stake: {stake:.2f}U\n"
        f"market: {row.get('title')}\n"
        f"url: https://polymarket.com/event/{row.get('eventSlug')}\n"
    )
    args.alert_file.write_text(alert, encoding="utf-8")
    print(
        f"聪明钱包跟单模拟：{wallet_name} BUY {row.get('outcome')} {stake:.2f}U @ {fill_price:.3f} EV {ev:.3f} | {row.get('title')}",
        flush=True,
    )
    return True


def mark_open(args: argparse.Namespace) -> None:
    rows = read_latest_rows(args.log)
    for row in rows.values():
        if row.get("status") != "OPEN":
            continue
        current = latest_price(row["slug"], row["outcome"])
        if current is None:
            continue
        stake = fnum(row.get("stake"))
        shares = fnum(row.get("shares"))
        pnl = shares * current - stake
        append_row(
            args.log,
            {
                **row,
                "ts": datetime.now(timezone.utc).isoformat(),
                "status": "MARK",
                "result": "MARK",
                "current_price": f"{current:.6f}",
                "pnl": f"{pnl:.4f}",
            },
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--stake-usdc", type=float, default=5.0)
    parser.add_argument("--bankroll-usdc", type=float, default=1000.0)
    parser.add_argument("--min-source-usdc", type=float, default=3.0)
    parser.add_argument("--min-price", type=float, default=0.05)
    parser.add_argument("--max-price", type=float, default=0.75)
    parser.add_argument("--max-slippage-bps", type=float, default=500.0)
    parser.add_argument("--min-ask-depth-usdc", type=float, default=20.0)
    parser.add_argument("--max-source-to-ask-gap", type=float, default=0.05)
    parser.add_argument("--require-live-fill", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--max-source-age-sec", type=float, default=8.0)
    parser.add_argument("--default-q", type=float, default=0.50)
    parser.add_argument("--default-q-min-price", type=float, default=0.35)
    parser.add_argument("--default-q-max-price", type=float, default=0.65)
    parser.add_argument("--min-ev-sample", type=int, default=20)
    parser.add_argument("--min-ev", type=float, default=0.0)
    parser.add_argument("--max-stake-usdc", type=float, default=5.0)
    parser.add_argument("--max-market-stake-usdc", type=float, default=20.0)
    parser.add_argument("--max-wallet-market-entries", type=int, default=2)
    parser.add_argument("--low-price-reduce-below", type=float, default=0.15)
    parser.add_argument("--low-price-stake-factor", type=float, default=0.25)
    parser.add_argument("--min-low-price-ask-depth-usdc", type=float, default=100.0)
    parser.add_argument("--require-positive-ev", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--windows", default="5m,15m")
    parser.add_argument("--allowed-outcome", action="append", default=[])
    parser.add_argument("--allowed-asset", action="append", default=[])
    parser.add_argument("--max-open-positions", type=int, default=100)
    parser.add_argument("--log", type=Path, default=Path("smart_wallet_copy_sim.csv"))
    parser.add_argument("--audit-log", type=Path, default=Path("smart_wallet_trade_audit.csv"))
    parser.add_argument("--seen", type=Path, default=Path("smart_wallet_seen.json"))
    parser.add_argument("--alert-file", type=Path, default=Path("latest_smart_wallet_copy_alert.txt"))
    parser.add_argument("--live-only", action="store_true", help="Initialize seen set without opening historical trades.")
    parser.add_argument("--max-audit-updates", type=int, default=50)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.windows = {item.strip() for item in args.windows.split(",") if item.strip()}
    args.allowed_outcome = {item.strip() for item in args.allowed_outcome if item.strip()}
    args.allowed_asset = {item.strip().upper() for item in args.allowed_asset if item.strip()}
    seen = read_seen(args.seen)
    initialized = bool(seen)
    while True:
        try:
            copied = read_latest_rows(args.log)
            opened = 0
            fresh_seen = set(seen)
            for name, wallet in WATCH_WALLETS.items():
                try:
                    rows = fetch_recent(wallet, args.limit)
                except Exception as exc:
                    print(f"smart wallet activity error: {name} | {exc}", flush=True)
                    continue
                for row in reversed(rows):
                    sid = source_id(name, row)
                    fresh_seen.add(sid)
                    if sid in copied or sid in seen:
                        continue
                    if args.live_only and not initialized:
                        continue
                    if should_copy(row, args):
                        if open_copy(name, row, args):
                            copied[sid] = row
                            opened += 1
            seen = fresh_seen
            write_seen(args.seen, seen)
            initialized = True
            mark_open(args)
            update_audit_marks(args.audit_log, market_by_slug, max_rows=args.max_audit_updates)
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 聪明钱包跟单扫描 | 新开仓 {opened} 条",
                flush=True,
            )
        except KeyboardInterrupt:
            return 130
        except Exception as exc:
            print(f"聪明钱包跟单错误：{exc}", flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
