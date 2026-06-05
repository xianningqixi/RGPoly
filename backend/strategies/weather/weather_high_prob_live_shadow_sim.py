#!/usr/bin/env python3
"""Mirror weather high-probability copy entries as a pre-live shadow validator.

Simulation only. This script does not scan wallets, read private keys, or place
orders. It watches the main weather high-probability audit log and mirrors each
new main-strategy entry with a larger live-like stake to test depth, slippage,
and final-only PnL.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from portfolio_risk import portfolio_open_exposure
from trade_audit import ensure_audit_open, order_snapshot, update_audit_marks
from realistic_execution_audit import ensure_execution_open, update_execution_marks

import weather_wallet_copy_sim as base


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


def mirror_id(source_id: str) -> str:
    return f"weather_live_shadow_mirror:{source_id}"


def append_reject(args: argparse.Namespace, source: dict[str, str], reason: str, extra: dict[str, Any] | None = None) -> None:
    fields = [
        "ts",
        "source_id",
        "shadow_id",
        "reason",
        "slug",
        "title",
        "outcome",
        "source_price",
        "main_fill_price",
        "main_stake",
        "shadow_stake",
        "source_age_sec",
        "best_ask",
        "ask_depth_usdc",
        "slippage_bps",
        "source_to_ask_gap",
    ]
    exists = args.reject_log.exists()
    extra = extra or {}
    detected = base.parse_ts(source.get("detected_time")) or base.parse_ts(source.get("audit_ts"))
    age = ""
    if detected:
        age = f"{(datetime.now(timezone.utc) - detected.astimezone(timezone.utc)).total_seconds():.2f}"
    with args.reject_log.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "ts": base.now_utc(),
                "source_id": source.get("id", ""),
                "shadow_id": mirror_id(source.get("id", "")),
                "reason": reason,
                "slug": source.get("slug", ""),
                "title": source.get("title", ""),
                "outcome": source.get("outcome", ""),
                "source_price": source.get("source_price", ""),
                "main_fill_price": source.get("sim_fill_price", ""),
                "main_stake": source.get("stake", ""),
                "shadow_stake": f"{args.stake_usdc:.4f}",
                "source_age_sec": age,
                "best_ask": extra.get("best_ask", ""),
                "ask_depth_usdc": extra.get("ask_depth_usdc", ""),
                "slippage_bps": extra.get("slippage_bps", ""),
                "source_to_ask_gap": extra.get("source_to_ask_gap", ""),
            }
        )


def eligible_source_rows(args: argparse.Namespace) -> list[dict[str, str]]:
    latest = base.read_latest_rows(args.source_audit_log)
    cutoff = base.latest_strategy_cutoff(args.strategy_key)
    rows: list[dict[str, str]] = []
    for row in latest.values():
        if row.get("strategy") not in args.source_strategy:
            continue
        ts = base.parse_ts(row.get("detected_time")) or base.parse_ts(row.get("audit_ts"))
        if cutoff and ts and ts < cutoff:
            continue
        rows.append(row)
    rows.sort(key=lambda row: base.parse_ts(row.get("detected_time")) or base.parse_ts(row.get("audit_ts")) or datetime.min.replace(tzinfo=timezone.utc))
    return rows


def open_exposure(args: argparse.Namespace) -> tuple[int, float]:
    return base.open_exposure(args.audit_log, base.latest_strategy_cutoff(args.strategy_key))


def market_event_exposure(args: argparse.Namespace, slug: str, event_slug: str) -> tuple[float, float]:
    latest = base.read_latest_rows(args.log)
    cutoff = base.latest_strategy_cutoff(args.strategy_key)
    market_stake = 0.0
    event_stake = 0.0
    for row in latest.values():
        if row.get("status") not in {"OPEN", "MARK"}:
            continue
        ts = base.row_time(row)
        if cutoff and ts and ts < cutoff:
            continue
        if row.get("slug") == slug:
            market_stake += base.fnum(row.get("stake"))
        if event_slug and row.get("event_slug") == event_slug:
            event_stake += base.fnum(row.get("stake"))
    return market_stake, event_stake


def mirror_source(source: dict[str, str], args: argparse.Namespace) -> bool:
    source_id = source.get("id", "")
    trade_id = mirror_id(source_id)
    slug = source.get("slug", "")
    event_slug = source.get("event_slug", "")
    outcome = source.get("outcome", "")
    if outcome not in {"Yes", "No"}:
        append_reject(args, source, "bad_outcome")
        return False
    stake = args.stake_usdc

    market = base.market_by_slug(slug)
    try:
        snapshot = order_snapshot(market, outcome, stake, fee_rate=args.fee_rate) if market else {}
    except Exception:
        snapshot = {}
    snapshot["intended_stake_usdc"] = stake
    source_price = base.fnum(source.get("source_price")) or base.fnum(source.get("sim_fill_price"))
    fill_price = base.fnum(snapshot.get("sim_fill_price")) or source_price
    best_ask = base.fnum(snapshot.get("best_ask"))
    ask_depth_usdc = base.fnum(snapshot.get("ask_depth_usdc"))
    would_live_fill = bool(snapshot.get("would_live_fill"))
    slippage_bps = ((fill_price - source_price) / source_price * 10000) if source_price > 0 else 0.0
    source_to_ask_gap = best_ask - source_price if best_ask > 0 and source_price > 0 else 999.0
    shares = base.fnum(snapshot.get("sim_shares")) or (stake / fill_price if fill_price > 0 else 0.0)
    ensure_audit_open(
        args.audit_log,
        trade_id=trade_id,
        strategy=args.strategy_key,
        wallet_name=source.get("wallet_name", ""),
        signal_time=source.get("signal_time", ""),
        title=source.get("title", ""),
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
            "would_live_fill": would_live_fill,
            "slippage_bps": slippage_bps,
            "estimated_q": source.get("estimated_q", ""),
            "ev": source.get("ev", ""),
            "price_bucket": source.get("price_bucket", ""),
            "recommended_stake": f"{stake:.4f}",
        },
    )
    ensure_execution_open(
        args.execution_audit_log,
        trade_id=trade_id,
        strategy=args.strategy_key,
        source_strategy="weather_high_prob_wallet_copy",
        source_id=source_id,
        source={**source, "shadow_stake": f"{stake:.4f}"},
        snapshot=snapshot,
        fee_model="polymarket_taker_weather_fee",
    )
    base.append_row(
        args.log,
        {
            "ts": base.now_utc(),
            "id": trade_id,
            "wallet_name": source.get("wallet_name", ""),
            "wallet": "",
            "source_timestamp": source.get("signal_time", ""),
            "action": "SHADOW_MIRROR_BUY",
            "outcome": outcome,
            "source_side": "BUY",
            "source_price": f"{source_price:.6f}",
            "sim_entry_price": f"{fill_price:.6f}",
            "stake": f"{stake:.4f}",
            "shares": f"{shares:.4f}",
            "source_usdc": source.get("stake", ""),
            "title": source.get("title", ""),
            "slug": slug,
            "event_slug": event_slug,
            "status": "OPEN",
            "url": source.get("url", ""),
        },
    )
    args.alert_file.write_text(
        (
            "WEATHER HIGH-PROB LIVE SHADOW MIRROR\n"
            f"time: {base.now_utc()}\n"
            f"source_id: {source_id}\n"
            f"wallet: {source.get('wallet_name', '')}\n"
            f"outcome: {outcome}\n"
            f"main_stake: {source.get('stake', '')}U\n"
            f"shadow_stake: {stake:.2f}U\n"
            f"shadow_entry_price: {fill_price:.4f}\n"
            f"source_price: {source_price:.4f}\n"
            f"slippage_bps: {slippage_bps:.0f}\n"
            f"market: {source.get('title', '')}\n"
            f"url: {source.get('url', '')}\n"
        ),
        encoding="utf-8",
    )
    print(
        f"Weather live shadow mirror: {source.get('wallet_name', '')} {outcome} "
        f"{stake:.2f}U @ {fill_price:.3f} | {source.get('title', '')}",
        flush=True,
    )
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--stake-usdc", type=float, default=30.0)
    parser.add_argument("--bankroll-usdc", type=float, default=900.0)
    parser.add_argument("--max-source-age-sec", type=float, default=60.0)
    parser.add_argument("--max-slippage-bps", type=float, default=150.0)
    parser.add_argument("--max-source-to-ask-gap", type=float, default=0.010)
    parser.add_argument("--min-ask-depth-usdc", type=float, default=30.0)
    parser.add_argument("--max-market-stake-usdc", type=float, default=30.0)
    parser.add_argument("--max-event-stake-usdc", type=float, default=60.0)
    parser.add_argument("--max-open-positions", type=int, default=30)
    parser.add_argument("--require-live-fill", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--source-audit-log", type=Path, default=Path("weather_high_prob_trade_audit.csv"))
    parser.add_argument("--source-strategy", action="append", default=["weather_high_prob_wallet_copy"])
    parser.add_argument("--log", type=Path, default=Path("weather_high_prob_live_shadow_sim.csv"))
    parser.add_argument("--audit-log", type=Path, default=Path("weather_high_prob_live_shadow_trade_audit.csv"))
    parser.add_argument("--execution-audit-log", type=Path, default=Path("weather_high_prob_live_shadow_execution_audit.csv"))
    parser.add_argument("--reject-log", type=Path, default=Path("weather_high_prob_live_shadow_rejects.csv"))
    parser.add_argument("--seen", type=Path, default=Path("weather_high_prob_live_shadow_mirror_seen.json"))
    parser.add_argument("--alert-file", type=Path, default=Path("latest_weather_high_prob_live_shadow_alert.txt"))
    parser.add_argument("--strategy-key", default="weather_high_prob_live_shadow")
    parser.add_argument("--max-audit-updates", type=int, default=100)
    parser.add_argument("--mark-every-scans", type=int, default=30)
    parser.add_argument("--live-only", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--isolated-portfolio-risk", action="store_true")
    parser.add_argument("--fee-rate", type=float, default=0.05)
    # Compatibility with the old launcher. The mirror uses source audit rows instead.
    parser.add_argument("--observation-stake-usdc", type=float, default=30.0)
    parser.add_argument("--activity-limit", type=int, default=100)
    parser.add_argument("--allowed-wallet", action="append", default=[])
    parser.add_argument("--allowed-price-bucket", action="append", default=[])
    parser.add_argument("--allowed-wallet-direction", action="append", default=[])
    parser.add_argument("--wallet-direction-q", action="append", default=[])
    parser.add_argument("--min-direction-edge", type=float, default=0.005)
    parser.add_argument("--min-source-usdc", type=float, default=1.0)
    parser.add_argument("--min-source-price", type=float, default=0.80)
    parser.add_argument("--max-source-price", type=float, default=0.995)
    parser.add_argument("--min-entry-price", type=float, default=0.80)
    parser.add_argument("--max-entry-price", type=float, default=0.995)
    parser.add_argument("--max-wallet-market-entries", type=int, default=1)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    seen = read_seen(args.seen)
    initialized = bool(seen)
    scan = 0
    while True:
        try:
            scan += 1
            opened = 0
            fresh_seen = set(seen)
            for source in eligible_source_rows(args):
                sid = source.get("id", "")
                mid = mirror_id(sid)
                if sid in seen or mid in base.read_latest_rows(args.log):
                    continue
                if args.live_only and not initialized:
                    fresh_seen.add(sid)
                    continue
                if mirror_source(source, args):
                    opened += 1
                fresh_seen.add(sid)
            seen = fresh_seen
            write_seen(args.seen, seen)
            initialized = True
            if args.mark_every_scans > 0 and scan % args.mark_every_scans == 0:
                base.update_open_rows(args)
                update_audit_marks(args.audit_log, base.market_by_slug, max_rows=args.max_audit_updates)
                update_execution_marks(args.execution_audit_log, base.market_by_slug, max_rows=args.max_audit_updates)
            if args.once:
                return 0
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Weather live shadow mirror scan | opened {opened}", flush=True)
        except KeyboardInterrupt:
            return 130
        except Exception as exc:
            print(f"Weather live shadow mirror error: {exc}", flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
