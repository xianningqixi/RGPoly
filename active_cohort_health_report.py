#!/usr/bin/env python3
"""Health report for the current active simulated cohort.

Final PnL is the only realized profit. Mark PnL and scenarios are diagnostics
for drawdown control while waiting for markets to finalize.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

import audit_backtest
from realized_pnl_report import row_time_value


ROOT = Path(__file__).resolve().parent
CURRENT_CONFIG = ROOT / "current_config_report.csv"
OUT_CSV = ROOT / "active_cohort_health_report.csv"
OUT_MD = ROOT / "active_cohort_health_report.md"

FIELDS = [
    "strategy",
    "state",
    "cutoff_ts",
    "total",
    "final",
    "pending",
    "wins",
    "losses",
    "realized_stake",
    "realized_pnl",
    "realized_roi",
    "pending_stake",
    "mark_pnl",
    "mark_roi_on_pending",
    "all_win_total_pnl",
    "all_loss_total_pnl",
    "action",
    "reason",
]


def fnum(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


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


def latest_price(row: dict[str, str]) -> float:
    for key in ("final_price", "price_1h", "price_10m", "price_2m"):
        value = fnum(row.get(key), -1)
        if value >= 0:
            return value
    return fnum(row.get("sim_fill_price"), fnum(row.get("source_price")))


def pending_mark_pnl(row: dict[str, str]) -> float:
    for key in ("slippage_pnl_1h", "slippage_pnl_10m", "slippage_pnl_2m"):
        if row.get(key) not in (None, ""):
            return fnum(row.get(key))
    shares = fnum(row.get("sim_shares"))
    stake = fnum(row.get("stake"))
    return shares * latest_price(row) - stake


def pending_win_pnl(row: dict[str, str]) -> float:
    shares = fnum(row.get("sim_shares"))
    stake = fnum(row.get("stake"))
    return shares - stake


def pending_loss_pnl(row: dict[str, str]) -> float:
    return -fnum(row.get("stake"))


def active_configs() -> list[dict[str, str]]:
    return [row for row in read_csv(CURRENT_CONFIG) if row.get("intended_state") != "PAUSED"]


def strategy_rows(strategy_key: str, cutoff_ts: str) -> list[dict[str, str]]:
    path = audit_backtest.AUDIT_FILES.get(strategy_key)
    if not path:
        return []
    cutoff = audit_backtest.parse_dt(cutoff_ts)
    return [
        row
        for row in audit_backtest.latest_rows(audit_backtest.read_rows(path))
        if audit_backtest.parse_dt(row_time_value(row)) >= cutoff
    ]


def action_for(final: int, pending: int, realized_pnl: float, mark_pnl: float, all_loss_total: float, args: argparse.Namespace) -> tuple[str, str]:
    if final == 0 and pending >= args.max_pending_without_final:
        return "HOLD_NEW_ENTRIES", f"pending {pending} >= {args.max_pending_without_final} and no finalized proof yet"
    if final >= args.min_final and realized_pnl > 0:
        return "ALLOW_SCALE_CAUTIOUSLY", "finalized cohort is profitable"
    if realized_pnl < 0:
        return "PAUSE_OR_TIGHTEN", "finalized cohort is negative"
    if mark_pnl < -args.mark_drawdown_warn:
        return "HOLD_NEW_ENTRIES", f"pending mark drawdown {mark_pnl:.2f}U below warning"
    if all_loss_total < -args.max_all_loss_risk:
        return "HOLD_NEW_ENTRIES", f"all-loss scenario {all_loss_total:.2f}U exceeds risk budget"
    return "WAIT_FINAL", "pending diagnostics only; final PnL not available"


def build_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for config in active_configs():
        strategy = config.get("strategy_key") or ""
        cutoff = config.get("cutoff_ts") or ""
        rows = strategy_rows(strategy, cutoff)
        final_rows = [row for row in rows if audit_backtest.is_final(row)]
        pending_rows = [row for row in rows if not audit_backtest.is_final(row)]
        realized_stake = sum(fnum(row.get("stake")) for row in final_rows)
        realized_pnl = sum(fnum(row.get("slippage_final_pnl"), fnum(row.get("final_pnl"))) for row in final_rows)
        pending_stake = sum(fnum(row.get("stake")) for row in pending_rows)
        mark_pnl = sum(pending_mark_pnl(row) for row in pending_rows)
        all_win_total = realized_pnl + sum(pending_win_pnl(row) for row in pending_rows)
        all_loss_total = realized_pnl + sum(pending_loss_pnl(row) for row in pending_rows)
        action, reason = action_for(len(final_rows), len(pending_rows), realized_pnl, mark_pnl, all_loss_total, args)
        out.append(
            {
                "strategy": strategy,
                "state": config.get("intended_state") or "",
                "cutoff_ts": cutoff,
                "total": len(rows),
                "final": len(final_rows),
                "pending": len(pending_rows),
                "wins": sum(1 for row in final_rows if fnum(row.get("slippage_final_pnl"), fnum(row.get("final_pnl"))) > 0),
                "losses": sum(1 for row in final_rows if fnum(row.get("slippage_final_pnl"), fnum(row.get("final_pnl"))) < 0),
                "realized_stake": realized_stake,
                "realized_pnl": realized_pnl,
                "realized_roi": realized_pnl / realized_stake * 100 if realized_stake else 0.0,
                "pending_stake": pending_stake,
                "mark_pnl": mark_pnl,
                "mark_roi_on_pending": mark_pnl / pending_stake * 100 if pending_stake else 0.0,
                "all_win_total_pnl": all_win_total,
                "all_loss_total_pnl": all_loss_total,
                "action": action,
                "reason": reason,
            }
        )
    return out


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in (
                "realized_stake",
                "realized_pnl",
                "realized_roi",
                "pending_stake",
                "mark_pnl",
                "mark_roi_on_pending",
                "all_win_total_pnl",
                "all_loss_total_pnl",
            ):
                out[key] = f"{fnum(out.get(key)):.6f}"
            writer.writerow({field: out.get(field, "") for field in FIELDS})


def render(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Active Cohort Health Report",
        "",
        "Simulation only. Realized PnL uses finalized slippage_final_pnl. Mark PnL is diagnostic and not counted as ROI.",
        "",
        "| strategy | action | total | final/pending | W/L | realized PnL | realized ROI | pending stake | mark PnL | all win | all loss | reason |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['strategy']} | {row['action']} | {row['total']} | {row['final']}/{row['pending']} | "
            f"{row['wins']}/{row['losses']} | {fnum(row['realized_pnl']):.4f}U | {fnum(row['realized_roi']):.2f}% | "
            f"{fnum(row['pending_stake']):.2f}U | {fnum(row['mark_pnl']):.4f}U | "
            f"{fnum(row['all_win_total_pnl']):.4f}U | {fnum(row['all_loss_total_pnl']):.4f}U | {row['reason']} |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--min-final", type=int, default=10)
    parser.add_argument("--max-pending-without-final", type=int, default=10)
    parser.add_argument("--mark-drawdown-warn", type=float, default=25.0)
    parser.add_argument("--max-all-loss-risk", type=float, default=100.0)
    parser.add_argument("--csv", type=Path, default=OUT_CSV)
    parser.add_argument("--md", type=Path, default=OUT_MD)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = build_rows(args)
    write_csv(rows, args.csv)
    text = render(rows)
    args.md.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
