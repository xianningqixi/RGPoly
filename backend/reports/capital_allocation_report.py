#!/usr/bin/env python3
"""Recommend simulation capital allocation by strategy.

Advisory only. This report does not edit launch scripts. It uses finalized
slippage-adjusted PnL as the main evidence and treats pending-only strategies
as observation, not profit.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
REALIZED = ROOT / "realized_pnl_report.csv"
CURRENT = ROOT / "current_config_report.csv"
OUT_CSV = ROOT / "capital_allocation_report.csv"
OUT_MD = ROOT / "capital_allocation_report.md"

FIELDS = [
    "strategy",
    "tier",
    "max_new_trade_stake_usdc",
    "max_open_stake_usdc",
    "realized",
    "pending",
    "pnl",
    "roi",
    "action",
    "reason",
]


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def inum(value: Any) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def strategy_key(name: str) -> str:
    return name.lower().replace(" ", "_")


def allocation_for(realized: dict[str, str], current: dict[str, str]) -> dict[str, Any]:
    strategy = realized.get("strategy", "")
    final = inum(realized.get("realized"))
    pending = inum(realized.get("pending"))
    pnl = fnum(realized.get("pnl"))
    roi = fnum(realized.get("roi"))
    current_state = current.get("intended_state") or "ACTIVE"
    current_final = inum(current.get("final_since_cutoff"))
    current_pending = inum(current.get("pending_since_cutoff"))

    tier = "ZERO"
    stake = 0.0
    open_cap = 0.0
    action = "pause_or_skip"
    reason = "default no allocation"

    if current_state == "PAUSED":
        tier = "PAUSED_ZERO"
        action = "keep_paused"
        reason = "strategy is intentionally paused"
    elif strategy == "BTC directional copy" and final >= 30 and pnl > 0 and roi >= 3:
        tier = "CORE_OBSERVATION"
        stake = 1.0
        open_cap = 10.0
        action = "keep_running_small"
        reason = "only strategy with sufficient positive finalized ROI"
    elif strategy == "BTC directional candidate copy":
        tier = "CANDIDATE_OBSERVATION"
        stake = 0.5
        open_cap = 6.0
        action = "observe_until_final_sample"
        reason = "candidate wallets pending; no realized profit counted yet"
    elif strategy == "Smart direction retest":
        tier = "TINY_RETEST"
        stake = 0.25
        open_cap = 2.0
        action = "tiny_retest_only"
        reason = "isolated retest from positive sub-buckets inside a negative parent strategy"
    elif strategy == "Weather direction retest":
        if current_state == "ACTIVE" and current_final > 0 and fnum(current.get("pnl")) > 0:
            tier = "ACTIVE_10U_RETEST"
            stake = 10.0
            open_cap = 20.0
            action = "keep_running_2slot_guarded"
            reason = "current 10U cohort is positive but pending can erase profit; cap open exposure at 2 slots"
        else:
            tier = "TINY_RETEST"
            stake = 0.5
            open_cap = 3.0
            action = "tiny_retest_only"
            reason = "isolated retest from finalized-positive weather wallet+direction buckets"
    elif current_final == 0 and current_pending > 0:
        tier = "WAITING_FINAL"
        stake = 0.0
        open_cap = 0.0
        action = "do_not_add_until_final"
        reason = "current config has pending exposure but no finalized result"
    elif final < 30 and pnl >= 0:
        tier = "SMALL_OBSERVATION"
        stake = 0.25
        open_cap = 2.0
        action = "observe_only"
        reason = "sample is too small for normal allocation"
    elif pnl < 0 or roi <= 0:
        tier = "ZERO"
        action = "do_not_allocate"
        reason = "negative or flat finalized ROI"
    else:
        tier = "WATCH"
        action = "watch_only"
        reason = "does not meet promotion criteria"

    return {
        "strategy": strategy,
        "tier": tier,
        "max_new_trade_stake_usdc": stake,
        "max_open_stake_usdc": open_cap,
        "realized": final,
        "pending": pending,
        "pnl": pnl,
        "roi": roi,
        "action": action,
        "reason": reason,
    }


def build_rows() -> list[dict[str, Any]]:
    realized_rows = read_csv(REALIZED)
    current_by_strategy = {row.get("strategy", ""): row for row in read_csv(CURRENT)}
    rows = [allocation_for(row, current_by_strategy.get(row.get("strategy", ""), {})) for row in realized_rows]
    tier_rank = {
        "CORE_OBSERVATION": 0,
        "ACTIVE_10U_RETEST": 1,
        "CANDIDATE_OBSERVATION": 2,
        "TINY_RETEST": 3,
        "SMALL_OBSERVATION": 4,
        "WAITING_FINAL": 5,
        "WATCH": 6,
        "PAUSED_ZERO": 7,
        "ZERO": 8,
    }
    return sorted(rows, key=lambda row: (tier_rank.get(str(row["tier"]), 99), -fnum(row["pnl"])))


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in ("max_new_trade_stake_usdc", "max_open_stake_usdc", "pnl", "roi"):
                out[key] = f"{fnum(out.get(key)):.6f}"
            writer.writerow({field: out.get(field, "") for field in FIELDS})


def write_md(rows: list[dict[str, Any]], path: Path) -> None:
    lines = [
        "# Capital Allocation Report",
        "",
        "Simulation only. Allocation is advisory and based on finalized `slippage_final_pnl`.",
        "",
        "| tier | strategy | stake | open cap | final/pending | PnL | ROI | action | reason |",
        "|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {tier} | {strategy} | {stake:.2f}U | {cap:.2f}U | {final}/{pending} | {pnl:.4f}U | {roi:.2f}% | {action} | {reason} |".format(
                tier=row["tier"],
                strategy=row["strategy"],
                stake=fnum(row["max_new_trade_stake_usdc"]),
                cap=fnum(row["max_open_stake_usdc"]),
                final=inum(row["realized"]),
                pending=inum(row["pending"]),
                pnl=fnum(row["pnl"]),
                roi=fnum(row["roi"]),
                action=row["action"],
                reason=row["reason"],
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--csv", type=Path, default=OUT_CSV)
    parser.add_argument("--md", type=Path, default=OUT_MD)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = build_rows()
    write_csv(rows, args.csv)
    write_md(rows, args.md)
    print("Capital allocation report")
    for row in rows:
        print(f"- {row['tier']}: {row['strategy']} stake={fnum(row['max_new_trade_stake_usdc']):.2f}U cap={fnum(row['max_open_stake_usdc']):.2f}U")
    print(f"Wrote {args.csv.name} and {args.md.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
