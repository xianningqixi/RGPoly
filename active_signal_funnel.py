#!/usr/bin/env python3
"""Read-only funnel for recent source activity.

This explains why current activity is not producing new simulated entries,
including whether signals are already seen or fail strategy filters.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import btc_directional_wallet_copy_sim as btc
import weather_wallet_copy_sim as weather


ROOT = Path(__file__).resolve().parent
FIELDS = ["ts", "strategy", "reason", "count", "avg_signal_age_sec"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def btc_args() -> argparse.Namespace:
    return argparse.Namespace(
        max_source_age_sec=75.0,
        min_price=0.03,
        max_price=0.85,
        yes_max_price=0.65,
        min_source_usdc=5.0,
        allowed_outcome={"No", "Yes"},
        block_market_keyword=["reach", "dip"],
        seen=ROOT / "btc_directional_seen.json",
        log=ROOT / "btc_directional_wallet_copy_sim.csv",
    )


def weather_args() -> argparse.Namespace:
    return argparse.Namespace(
        max_source_age_sec=120.0,
        min_source_usdc=1.0,
        min_source_price=0.01,
        max_source_price=0.995,
        allowed_outcome=set(),
        allowed_price_bucket=set(),
        allowed_wallet_direction={},
        wallet_direction_q={},
        min_direction_edge=0.005,
        seen=ROOT / "weather_wallet_seen.json",
        log=ROOT / "weather_wallet_copy_sim.csv",
    )


def weather_direction_retest_args() -> argparse.Namespace:
    return argparse.Namespace(
        max_source_age_sec=90.0,
        min_source_usdc=1.0,
        min_source_price=0.80,
        max_source_price=0.995,
        min_entry_price=0.80,
        max_entry_price=0.995,
        max_slippage_bps=350.0,
        min_ask_depth_usdc=20.0,
        max_source_to_ask_gap=0.035,
        max_market_stake_usdc=10.0,
        max_event_stake_usdc=20.0,
        max_wallet_market_entries=1,
        max_open_positions=2,
        min_realized_pnl_buffer_usdc=10.0,
        allowed_outcome={"Yes", "No"},
        allowed_price_bucket={"0.8-0.9", "0.9-1.0"},
        allowed_wallet_direction={
            "Poligarch": {"No:0.9-1.0", "Yes:0.8-0.9", "Yes:0.9-1.0"},
            "Railbird": {"No:0.9-1.0"},
        },
        wallet_direction_q={
            "Poligarch": {"No:0.9-1.0": 0.9837, "Yes:0.8-0.9": 0.9492, "Yes:0.9-1.0": 1.0},
            "Railbird": {"No:0.9-1.0": 1.0},
        },
        min_direction_edge=0.005,
        strategy_key="weather_direction_retest",
        seen=ROOT / "weather_direction_retest_seen.json",
        log=ROOT / "weather_direction_retest_sim.csv",
        audit_log=ROOT / "weather_direction_retest_trade_audit.csv",
    )


def add_count(stats: dict[str, dict[str, float]], reason: str, age: float) -> None:
    item = stats.setdefault(reason, {"count": 0.0, "age_sum": 0.0})
    item["count"] += 1
    item["age_sum"] += max(0.0, age)


def count_btc(limit: int) -> dict[str, dict[str, float]]:
    args = btc_args()
    seen = btc.read_seen(args.seen)
    copied = btc.read_latest_rows(args.log)
    stats: dict[str, dict[str, float]] = {}
    for name, wallet in btc.WATCH_WALLETS.items():
        try:
            rows = btc.fetch_recent(wallet, limit)
        except Exception as exc:
            add_count(stats, f"fetch_error:{type(exc).__name__}", 0)
            continue
        for row in rows:
            sid = btc.source_id(name, row)
            reason = btc.should_copy_reason(row, args)
            age = btc.time.time() - btc.fnum(row.get("timestamp"))
            if sid in copied:
                add_count(stats, "already_copied", age)
            elif sid in seen:
                add_count(stats, f"seen:{reason}", age)
            else:
                add_count(stats, f"new:{reason}", age)
    return stats


def count_weather(limit: int, args: argparse.Namespace | None = None, allowed_wallets: set[str] | None = None) -> dict[str, dict[str, float]]:
    args = args or weather_args()
    seen = weather.read_seen(args.seen)
    copied = weather.read_latest_rows(args.log)
    cutoff = weather.latest_strategy_cutoff(getattr(args, "strategy_key", "weather_direction_retest"))
    exposure_path = getattr(args, "audit_log", args.log)
    open_count, _ = weather.open_exposure(exposure_path, cutoff)
    realized_buffer = weather.realized_pnl(exposure_path, cutoff)
    wallets = weather.active_wallets(
        weather.parse_wallets([]),
        argparse.Namespace(
            allowed_wallet=allowed_wallets or {"ColdMath", "NoonienSoong", "BeefSlayer"},
            blocked_wallet=set(weather.DEFAULT_BLOCKED_WALLETS),
        ),
    )
    stats: dict[str, dict[str, float]] = {}
    for name, wallet in wallets.items():
        try:
            rows = weather.fetch_activity(wallet, limit)
        except Exception as exc:
            add_count(stats, f"fetch_error:{type(exc).__name__}", 0)
            continue
        for row in rows:
            sid = weather.source_id(name, row)
            reason = weather.should_copy_reason(row, args)
            if reason == "TAKE" and open_count >= getattr(args, "max_open_positions", 1_000_000):
                reason = "open_position_cap_full"
            if reason == "TAKE" and realized_buffer < getattr(args, "min_realized_pnl_buffer_usdc", 0.0):
                reason = "realized_profit_buffer_low"
            age = weather.time.time() - weather.fnum(row.get("timestamp"))
            if sid in copied:
                add_count(stats, "already_copied", age)
            elif sid in seen:
                add_count(stats, f"seen:{reason}", age)
            else:
                add_count(stats, f"new:{reason}", age)
    return stats


def build_rows(limit: int) -> list[dict[str, Any]]:
    ts = now_iso()
    rows: list[dict[str, Any]] = []
    strategies = [
        ("btc_directional_copy", count_btc(limit)),
        (
            "weather_direction_retest",
            count_weather(limit, weather_direction_retest_args(), {"Poligarch", "Railbird"}),
        ),
        ("weather_wallet_copy", count_weather(limit)),
    ]
    for strategy, stats in strategies:
        ranked = sorted(stats.items(), key=lambda item: item[1]["count"], reverse=True)
        for reason, item in ranked:
            count = int(item["count"])
            rows.append(
                {
                    "ts": ts,
                    "strategy": strategy,
                    "reason": reason,
                    "count": count,
                    "avg_signal_age_sec": f"{(item['age_sum'] / count) if count else 0:.2f}",
                }
            )
    return rows


def write_csv(rows: list[dict[str, Any]], path: Path = ROOT / "active_signal_funnel.csv") -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in FIELDS} for row in rows)


def render(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Active Signal Funnel",
        "",
        "Read-only view of recent source activity. Reasons prefixed with seen: are already in the seen set.",
        "",
        "| strategy | reason | count | avg age |",
        "|---|---|---:|---:|",
    ]
    for row in rows:
        lines.append(f"| {row['strategy']} | {row['reason']} | {row['count']} | {float(row.get('avg_signal_age_sec') or 0):.1f}s |")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = build_rows(args.limit)
    write_csv(rows)
    text = render(rows)
    (ROOT / "active_signal_funnel.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
