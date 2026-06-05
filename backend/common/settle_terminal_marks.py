#!/usr/bin/env python3
"""Promote stale marked audit rows to final when terminal prices are clear.

This is conservative: it only settles rows that already have a marked price at
or beyond a terminal threshold. It does not infer a result from unresolved
mid-market prices.
"""

from __future__ import annotations

import argparse
import csv
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trade_audit import AUDIT_FIELDS


ROOT = Path.cwd()
DEFAULT_FILES = [
    ROOT / "creamcream_trade_audit.csv",
    ROOT / "btc_directional_trade_audit.csv",
    ROOT / "btc_directional_candidate_trade_audit.csv",
    ROOT / "weather_wallet_trade_audit.csv",
]


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def latest_price(row: dict[str, str]) -> float:
    for key in ("final_price", "price_1h", "price_10m", "price_2m"):
        value = row.get(key)
        if value not in {"", None}:
            return fnum(value)
    return 0.0


def is_unrealized(row: dict[str, str]) -> bool:
    return row.get("final_result") not in {"WIN", "LOSS"}


def settle_row(row: dict[str, str], win_threshold: float, loss_threshold: float) -> bool:
    if not is_unrealized(row):
        return False
    price = latest_price(row)
    if price >= win_threshold:
        result = "WIN"
    elif 0 < price <= loss_threshold:
        result = "LOSS"
    else:
        return False

    stake = fnum(row.get("stake"))
    source_price = fnum(row.get("source_price"))
    no_slip_shares = stake / source_price if source_price > 0 else 0.0
    slip_shares = fnum(row.get("sim_shares"))
    row["final_price"] = f"{price:.6f}"
    row["final_result"] = result
    row["final_pnl"] = f"{(no_slip_shares * price - stake):.4f}"
    row["slippage_final_pnl"] = f"{(slip_shares * price - stake):.4f}"
    row["status"] = "FINAL"
    row["audit_ts"] = datetime.now(timezone.utc).isoformat()
    return True


def read_latest(path: Path) -> list[dict[str, str]]:
    latest: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for index, row in enumerate(csv.DictReader(file)):
            latest[row.get("id") or str(index)] = {field: row.get(field, "") for field in AUDIT_FIELDS}
    return list(latest.values())


def settle_file(path: Path, win_threshold: float, loss_threshold: float, dry_run: bool) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    rows = read_latest(path)
    changed = 0
    for row in rows:
        if settle_row(row, win_threshold, loss_threshold):
            changed += 1
    if changed and not dry_run:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup = path.with_suffix(path.suffix + f".bak_terminal_{stamp}")
        shutil.copy2(path, backup)
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=AUDIT_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    return len(rows), changed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--win-threshold", type=float, default=0.999)
    parser.add_argument("--loss-threshold", type=float, default=0.001)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("files", nargs="*", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    files = [ROOT / item if not item.is_absolute() else item for item in args.files] if args.files else DEFAULT_FILES
    for path in files:
        total, changed = settle_file(path, args.win_threshold, args.loss_threshold, args.dry_run)
        action = "would_settle" if args.dry_run else "settled"
        print(f"{path.name}: {action} {changed} of {total}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
