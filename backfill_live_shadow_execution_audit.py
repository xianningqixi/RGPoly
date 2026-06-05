#!/usr/bin/env python3
"""Backfill fee-aware execution audit rows from existing shadow trade audits.

Backfilled rows use the stored average fill price and shares from the shadow
audit. They are useful for fee-adjusted review, but they are not counted as
strict real-time order-book validation.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

from realistic_execution_audit import FIELDS, append_row, latest_rows, update_execution_marks
from trade_audit import fnum

import btc_directional_wallet_copy_sim as btc_base
import weather_wallet_copy_sim as weather_base


ROOT = Path(__file__).resolve().parent

CONFIGS = {
    "btc_directional_live_shadow": {
        "input": ROOT / "btc_directional_live_shadow_trade_audit.csv",
        "output": ROOT / "btc_directional_live_shadow_execution_audit.csv",
        "fee_rate": 0.07,
        "fee_model": "backfill_from_shadow_trade_audit_avg_price_crypto_fee",
        "source_strategy": "btc_directional_copy",
        "loader": btc_base.market_by_slug,
    },
    "weather_high_prob_live_shadow": {
        "input": ROOT / "weather_high_prob_live_shadow_trade_audit.csv",
        "output": ROOT / "weather_high_prob_live_shadow_execution_audit.csv",
        "fee_rate": 0.05,
        "fee_model": "backfill_from_shadow_trade_audit_avg_price_weather_fee",
        "source_strategy": "weather_high_prob_wallet_copy",
        "loader": weather_base.market_by_slug,
    },
}


def read_latest(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            if row.get("id"):
                rows[row["id"]] = row
    return rows


def fee_usdc(shares: float, price: float, fee_rate: float) -> float:
    return shares * fee_rate * price * (1.0 - price)


def backfill_one(strategy: str, *, final_only: bool = False) -> int:
    cfg = CONFIGS[strategy]
    input_path: Path = cfg["input"]  # type: ignore[assignment]
    output_path: Path = cfg["output"]  # type: ignore[assignment]
    existing = latest_rows(output_path)
    rows = read_latest(input_path)
    written = 0
    for row in rows.values():
        trade_id = row.get("id", "")
        if not trade_id or trade_id in existing:
            continue
        if final_only and row.get("final_result") not in {"WIN", "LOSS"}:
            continue
        stake = fnum(row.get("stake"))
        price = fnum(row.get("sim_fill_price")) or fnum(row.get("source_price"))
        shares = fnum(row.get("sim_shares")) or (stake / price if price > 0 else 0.0)
        spent = shares * price
        fee = fee_usdc(shares, price, float(cfg["fee_rate"]))
        status = row.get("status") or "OPEN"
        final_price = fnum(row.get("final_price"))
        fee_final_pnl = ""
        if row.get("final_result") in {"WIN", "LOSS"} and row.get("final_price") not in {"", None}:
            fee_final_pnl = f"{(shares * final_price - spent - fee):.4f}"
            status = "FINAL"
        append_row(
            output_path,
            {
                "ts": row.get("detected_time") or row.get("audit_ts"),
                "id": trade_id,
                "strategy": strategy,
                "execution_source": "BACKFILL_FROM_TRADE_AUDIT_AVG_PRICE",
                "source_strategy": cfg["source_strategy"],
                "source_id": trade_id,
                "wallet_name": row.get("wallet_name", ""),
                "signal_time": row.get("signal_time", ""),
                "title": row.get("title", ""),
                "slug": row.get("slug", ""),
                "event_slug": row.get("event_slug", ""),
                "outcome": row.get("outcome", ""),
                "intended_stake_usdc": f"{stake:.4f}",
                "source_price": row.get("source_price", ""),
                "best_bid": row.get("best_bid", ""),
                "best_ask": row.get("best_ask", ""),
                "ask_depth_shares": row.get("ask_depth_shares", ""),
                "ask_depth_usdc": row.get("ask_depth_usdc", ""),
                "fill_status": "FULL" if row.get("would_live_fill") == "YES" else "UNKNOWN",
                "would_live_fill": row.get("would_live_fill", ""),
                "spent_usdc": f"{spent:.4f}",
                "unfilled_usdc": "0.0000" if row.get("would_live_fill") == "YES" else "",
                "avg_fill_price": f"{price:.6f}",
                "shares": f"{shares:.4f}",
                "levels_used": "",
                "fee_model": cfg["fee_model"],
                "fee_rate": f"{float(cfg['fee_rate']):.6f}",
                "fee_usdc": f"{fee:.6f}",
                "total_cost_usdc": f"{(spent + fee):.6f}",
                "slippage_bps": row.get("slippage_bps", ""),
                "price_2m": row.get("price_2m", ""),
                "fee_adjusted_pnl_2m": "",
                "price_10m": row.get("price_10m", ""),
                "fee_adjusted_pnl_10m": "",
                "price_1h": row.get("price_1h", ""),
                "fee_adjusted_pnl_1h": "",
                "final_price": row.get("final_price", ""),
                "final_result": row.get("final_result", ""),
                "fee_adjusted_final_pnl": fee_final_pnl,
                "status": status,
                "url": row.get("url", ""),
            },
        )
        written += 1
    update_execution_marks(output_path, cfg["loader"], max_rows=200)  # type: ignore[arg-type]
    return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", action="append", choices=sorted(CONFIGS), default=[])
    parser.add_argument("--final-only", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    strategies = args.strategy or sorted(CONFIGS)
    for strategy in strategies:
        written = backfill_one(strategy, final_only=args.final_only)
        print(f"{strategy}: backfilled {written} execution audit row(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
