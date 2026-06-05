#!/usr/bin/env python3
"""Pending-settlement scenario report for the active current configuration."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

import audit_backtest


ROOT = Path.cwd()
DEFAULT_SINCE = "2026-05-25T13:58:41Z"
FIELDS = [
    "strategy",
    "final",
    "pending",
    "realized_pnl",
    "realized_roi",
    "pending_stake",
    "pending_best_case_pnl",
    "pending_worst_case_pnl",
    "required_profit_buffer",
    "profit_buffer_gap",
    "new_entries_allowed",
    "all_win_total_pnl",
    "all_loss_total_pnl",
    "losses_to_turn_negative",
    "verdict",
    "notes",
]


@dataclass
class PendingTrade:
    fill: float
    stake: float

    @property
    def win_pnl(self) -> float:
        if self.fill <= 0:
            return 0.0
        return self.stake / self.fill - self.stake

    @property
    def loss_pnl(self) -> float:
        return -self.stake


def latest_current_rows(strategy: str, since: str) -> list[dict[str, str]]:
    path = audit_backtest.AUDIT_FILES[strategy]
    since_dt = audit_backtest.parse_dt(since)
    rows = audit_backtest.latest_rows(audit_backtest.read_rows(path))
    return [row for row in rows if audit_backtest.row_time(row) >= since_dt]


def pending_trade(row: dict[str, str], stake_usdc: float) -> PendingTrade:
    original_stake = audit_backtest.fnum(row.get("stake"), stake_usdc)
    fill = audit_backtest.fnum(row.get("sim_fill_price"), audit_backtest.fnum(row.get("best_ask")))
    stake = stake_usdc if original_stake > 0 else audit_backtest.fnum(row.get("stake"), stake_usdc)
    return PendingTrade(fill=fill, stake=stake)


def losses_to_negative(realized_pnl: float, pending: list[PendingTrade]) -> int:
    if realized_pnl < 0:
        return 0
    pnl = realized_pnl
    for index, trade in enumerate(sorted(pending, key=lambda item: item.loss_pnl), start=1):
        pnl += trade.loss_pnl
        if pnl < 0:
            return index
    return len(pending) + 1


def build_row(strategy: str, since: str, stake_usdc: float, min_profit_buffer: float) -> dict[str, str]:
    rows = latest_current_rows(strategy, since)
    final_rows = [row for row in rows if audit_backtest.is_final(row)]
    pending_rows = [row for row in rows if not audit_backtest.is_final(row)]
    realized_pnls = [audit_backtest.final_pnl(row, stake_usdc) for row in final_rows]
    realized_pnl = sum(realized_pnls)
    realized_stake = len(final_rows) * stake_usdc
    pending = [pending_trade(row, stake_usdc) for row in pending_rows]
    best_case = sum(trade.win_pnl for trade in pending)
    worst_case = sum(trade.loss_pnl for trade in pending)
    buffer_gap = max(0.0, min_profit_buffer - realized_pnl)
    new_entries_allowed = realized_pnl >= min_profit_buffer
    turn_loss_count = losses_to_negative(realized_pnl, pending)
    if not pending:
        verdict = "NO_PENDING"
        notes = "all current rows finalized"
    elif turn_loss_count <= len(pending):
        verdict = "PENDING_CAN_ERASE_PROFIT"
        notes = f"{turn_loss_count} pending loss(es) can turn current realized PnL negative"
    else:
        verdict = "PENDING_BUFFERED"
        notes = "current realized PnL can absorb all pending losses"
    return {
        "strategy": strategy,
        "final": str(len(final_rows)),
        "pending": str(len(pending_rows)),
        "realized_pnl": f"{realized_pnl:.6f}",
        "realized_roi": f"{(realized_pnl / realized_stake * 100) if realized_stake else 0.0:.6f}",
        "pending_stake": f"{sum(trade.stake for trade in pending):.6f}",
        "pending_best_case_pnl": f"{best_case:.6f}",
        "pending_worst_case_pnl": f"{worst_case:.6f}",
        "required_profit_buffer": f"{min_profit_buffer:.6f}",
        "profit_buffer_gap": f"{buffer_gap:.6f}",
        "new_entries_allowed": "YES" if new_entries_allowed else "NO",
        "all_win_total_pnl": f"{realized_pnl + best_case:.6f}",
        "all_loss_total_pnl": f"{realized_pnl + worst_case:.6f}",
        "losses_to_turn_negative": str(turn_loss_count if turn_loss_count <= len(pending) else ""),
        "verdict": verdict,
        "notes": notes,
    }


def write_csv(rows: list[dict[str, str]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in FIELDS} for row in rows)


def render(rows: list[dict[str, str]]) -> str:
    lines = [
        "# Pending Scenario Report",
        "",
        "Simulation only. Final ROI still uses finalized slippage_final_pnl; pending scenarios are risk diagnostics.",
        "",
        "| strategy | final/pending | realized PnL | ROI | pending stake | buffer gap | new entries | all win | all loss | verdict | notes |",
        "|---|---:|---:|---:|---:|---:|---|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['strategy']} | {row['final']}/{row['pending']} | {float(row['realized_pnl']):.4f} | "
            f"{float(row['realized_roi']):.2f}% | {float(row['pending_stake']):.2f} | "
            f"{float(row['profit_buffer_gap']):.4f} | {row['new_entries_allowed']} | "
            f"{float(row['all_win_total_pnl']):.4f} | {float(row['all_loss_total_pnl']):.4f} | "
            f"{row['verdict']} | {row['notes']} |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pending scenario diagnostics")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--strategy", action="append", default=["weather_direction_retest"])
    parser.add_argument("--since", default=DEFAULT_SINCE)
    parser.add_argument("--stake-usdc", type=float, default=10.0)
    parser.add_argument("--min-profit-buffer-usdc", type=float, default=10.0)
    parser.add_argument("--csv", type=Path, default=ROOT / "pending_scenario_report.csv")
    parser.add_argument("--md", type=Path, default=ROOT / "pending_scenario_report.md")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = [build_row(strategy, args.since, args.stake_usdc, args.min_profit_buffer_usdc) for strategy in args.strategy]
    write_csv(rows, args.csv)
    text = render(rows)
    args.md.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
