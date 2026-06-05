#!/usr/bin/env python3
"""Backfill pending audit rows in small, safe batches.

The running simulators update their own audit marks, but paused/downweighted
strategies can leave old pending rows behind. This script improves final-data
coverage without opening new trades or changing strategy parameters.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from trade_audit import latest_audit_rows, update_audit_marks

import ai_signal_simulator
import btc_directional_wallet_copy_sim
import creamcream_copy_sim
import smart_wallet_copy_sim
import weather_wallet_copy_sim


ROOT = Path(__file__).resolve().parent

JOBS: list[dict[str, Any]] = [
    {
        "strategy": "weather_direction_retest",
        "path": ROOT / "weather_direction_retest_trade_audit.csv",
        "loader": weather_wallet_copy_sim.market_by_slug,
    },
    {
        "strategy": "creamcream_copy",
        "path": ROOT / "creamcream_trade_audit.csv",
        "loader": creamcream_copy_sim.market_by_slug,
    },
    {
        "strategy": "smart_wallet_copy",
        "path": ROOT / "smart_wallet_trade_audit.csv",
        "loader": smart_wallet_copy_sim.market_by_slug,
    },
    {
        "strategy": "btc_directional_copy",
        "path": ROOT / "btc_directional_trade_audit.csv",
        "loader": btc_directional_wallet_copy_sim.market_by_slug,
    },
    {
        "strategy": "btc_directional_candidate_copy",
        "path": ROOT / "btc_directional_candidate_trade_audit.csv",
        "loader": btc_directional_wallet_copy_sim.market_by_slug,
    },
    {
        "strategy": "weather_wallet_copy",
        "path": ROOT / "weather_wallet_trade_audit.csv",
        "loader": weather_wallet_copy_sim.market_by_slug,
    },
    {
        "strategy": "ai_signal_copy",
        "path": ROOT / "ai_signal_trade_audit.csv",
        "loader": ai_signal_simulator.market_loader,
    },
]

FIELDS = [
    "ts",
    "strategy",
    "before_pending",
    "after_pending",
    "before_final",
    "after_final",
    "new_final",
    "batch_limit",
    "status",
]


def is_final(row: dict[str, str]) -> bool:
    return row.get("final_result") in {"WIN", "LOSS"} and row.get("slippage_final_pnl") not in {"", None}


def counts(path: Path) -> tuple[int, int]:
    rows = latest_audit_rows(path)
    final = sum(1 for row in rows.values() if is_final(row))
    pending = len(rows) - final
    return final, pending


def append_summary(path: Path, row: dict[str, Any]) -> None:
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in FIELDS})


def run_job(strategy: str, path: Path, loader: Callable[[str], dict[str, Any] | None], batch_limit: int) -> dict[str, Any]:
    before_final, before_pending = counts(path)
    status = "OK"
    try:
        if before_pending > 0:
            update_audit_marks(path, loader, max_rows=batch_limit)
    except Exception as exc:
        status = f"ERROR: {exc}"
    after_final, after_pending = counts(path)
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "strategy": strategy,
        "before_pending": before_pending,
        "after_pending": after_pending,
        "before_final": before_final,
        "after_final": after_final,
        "new_final": max(0, after_final - before_final),
        "batch_limit": batch_limit,
        "status": status,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-limit", type=int, default=80, help="Max pending rows to inspect per strategy")
    parser.add_argument("--summary-log", type=Path, default=ROOT / "audit_backfill_summary.csv")
    parser.add_argument("--once", action="store_true", help="Run one backfill pass and exit")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    for job in JOBS:
        row = run_job(job["strategy"], job["path"], job["loader"], args.batch_limit)
        append_summary(args.summary_log, row)
        print(
            f"{row['strategy']}: pending {row['before_pending']} -> {row['after_pending']}, "
            f"final +{row['new_final']} ({row['status']})",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
