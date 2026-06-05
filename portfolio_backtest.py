#!/usr/bin/env python3
"""Time-ordered portfolio replay for local Polymarket simulation audits.

The report is read-only. It answers a stricter question than per-strategy ROI:
with a fixed paper bankroll and fixed stake, which historical signals would
have been accepted after capital and open-position constraints?
"""

from __future__ import annotations

import argparse
import csv
import heapq
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import audit_backtest


ROOT = Path(__file__).resolve().parent


def fnum(value: Any, default: float = 0.0) -> float:
    return audit_backtest.fnum(value, default)


def parse_dt(value: str | None) -> datetime:
    return audit_backtest.parse_dt(value)


def resolution_time(row: dict[str, str], fallback_days: float) -> datetime:
    for key in ("finalized_time", "resolved_time", "resolution_time", "last_checked", "audit_ts"):
        dt = parse_dt(row.get(key))
        if dt != datetime.min.replace(tzinfo=timezone.utc):
            return dt
    return audit_backtest.row_time(row) + timedelta(days=fallback_days)


def row_strategy(name: str, row: dict[str, str]) -> str:
    return row.get("strategy") or name


@dataclass
class AcceptedTrade:
    strategy: str
    row: dict[str, str]
    entry_time: datetime
    exit_time: datetime
    pnl: float


@dataclass
class PortfolioResult:
    strategy: str
    accepted: int
    rejected_capital: int
    rejected_strategy_cap: int
    final: int
    pending: int
    wins: int
    losses: int
    stake: float
    pnl: float
    roi: float


def load_candidates(args: argparse.Namespace) -> list[tuple[str, dict[str, str]]]:
    strategies = args.strategy or sorted(audit_backtest.AUDIT_FILES)
    candidates: list[tuple[str, dict[str, str]]] = []
    for name in strategies:
        rows = audit_backtest.latest_rows(audit_backtest.read_rows(audit_backtest.AUDIT_FILES[name]))
        for row in rows:
            if audit_backtest.row_time(row) < args.since_dt:
                continue
            if not audit_backtest.include_row(row, args):
                continue
            candidates.append((name, row))
    candidates.sort(key=lambda item: audit_backtest.row_time(item[1]))
    return candidates


def replay(args: argparse.Namespace) -> tuple[list[AcceptedTrade], dict[str, dict[str, int]], float, int]:
    open_heap: list[tuple[datetime, int, AcceptedTrade]] = []
    open_stake = 0.0
    max_open_stake = 0.0
    max_open_positions = 0
    sequence = 0
    accepted: list[AcceptedTrade] = []
    rejects: dict[str, dict[str, int]] = {}

    def reject(strategy: str, reason: str) -> None:
        rejects.setdefault(strategy, {"capital": 0, "strategy_cap": 0})
        rejects[strategy][reason] = rejects[strategy].get(reason, 0) + 1

    for strategy, row in load_candidates(args):
        entry_time = audit_backtest.row_time(row)
        while open_heap and open_heap[0][0] <= entry_time:
            _, _, closed = heapq.heappop(open_heap)
            open_stake = max(0.0, open_stake - args.stake_usdc)

        strategy_open = sum(1 for _, _, trade in open_heap if trade.strategy == strategy)
        if open_stake + args.stake_usdc > args.bankroll_usdc:
            reject(strategy, "capital")
            continue
        if len(open_heap) >= args.max_open_positions:
            reject(strategy, "capital")
            continue
        if strategy_open >= args.max_strategy_open_positions:
            reject(strategy, "strategy_cap")
            continue

        is_final = audit_backtest.is_final(row)
        exit_time = resolution_time(row, args.pending_hold_days)
        if not is_final:
            exit_time = max(exit_time, entry_time + timedelta(days=args.pending_hold_days))
        pnl = audit_backtest.final_pnl(row, args.stake_usdc) if is_final else 0.0
        trade = AcceptedTrade(strategy=strategy, row=row, entry_time=entry_time, exit_time=exit_time, pnl=pnl)
        accepted.append(trade)
        open_stake += args.stake_usdc
        max_open_stake = max(max_open_stake, open_stake)
        max_open_positions = max(max_open_positions, len(open_heap) + 1)
        sequence += 1
        heapq.heappush(open_heap, (exit_time, sequence, trade))
    return accepted, rejects, max_open_stake, max_open_positions


def summarize(accepted: list[AcceptedTrade], rejects: dict[str, dict[str, int]], args: argparse.Namespace) -> list[PortfolioResult]:
    strategies = sorted({trade.strategy for trade in accepted} | set(rejects))
    rows: list[PortfolioResult] = []
    for strategy in strategies:
        trades = [trade for trade in accepted if trade.strategy == strategy]
        final = [trade for trade in trades if audit_backtest.is_final(trade.row)]
        pnl = sum(trade.pnl for trade in final)
        stake = len(final) * args.stake_usdc
        wins = sum(1 for trade in final if trade.pnl > 0)
        losses = sum(1 for trade in final if trade.pnl < 0)
        rows.append(
            PortfolioResult(
                strategy=strategy,
                accepted=len(trades),
                rejected_capital=rejects.get(strategy, {}).get("capital", 0),
                rejected_strategy_cap=rejects.get(strategy, {}).get("strategy_cap", 0),
                final=len(final),
                pending=len(trades) - len(final),
                wins=wins,
                losses=losses,
                stake=stake,
                pnl=pnl,
                roi=pnl / stake * 100 if stake else 0.0,
            )
        )
    return rows


def write_csv(rows: list[PortfolioResult], path: Path) -> None:
    fields = list(PortfolioResult.__dataclass_fields__.keys())
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for result in rows:
            row = result.__dict__.copy()
            for key in ("stake", "pnl", "roi"):
                row[key] = f"{row[key]:.6f}"
            writer.writerow(row)


def render(rows: list[PortfolioResult], accepted: list[AcceptedTrade], max_open_stake: float, max_open_positions: int, args: argparse.Namespace) -> str:
    final_trades = [trade for trade in accepted if audit_backtest.is_final(trade.row)]
    total_stake = len(final_trades) * args.stake_usdc
    total_pnl = sum(trade.pnl for trade in final_trades)
    total_roi = total_pnl / total_stake * 100 if total_stake else 0.0
    lines = [
        "# Portfolio Backtest Report",
        "",
        "Time-ordered read-only replay. Final ROI uses finalized slippage_final_pnl only.",
        "",
        f"- bankroll_usdc: {args.bankroll_usdc:.2f}",
        f"- stake_usdc: {args.stake_usdc:.2f}",
        f"- max_open_positions: {args.max_open_positions}",
        f"- max_strategy_open_positions: {args.max_strategy_open_positions}",
        f"- accepted: {len(accepted)}",
        f"- final: {len(final_trades)}",
        f"- total_pnl: {total_pnl:.4f}U",
        f"- total_roi: {total_roi:.2f}%",
        f"- max_open_stake: {max_open_stake:.2f}U",
        f"- max_open_positions_observed: {max_open_positions}",
        "",
        "| strategy | accepted | cap rejects | strategy rejects | final | pending | W/L | stake | pnl | roi |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row.strategy} | {row.accepted} | {row.rejected_capital} | {row.rejected_strategy_cap} | "
            f"{row.final} | {row.pending} | {row.wins}/{row.losses} | {row.stake:.2f} | "
            f"{row.pnl:.4f} | {row.roi:.2f}% |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = audit_backtest.build_parser()
    parser.description = "Portfolio-level time-ordered backtest from local audit logs"
    parser.add_argument("--bankroll-usdc", type=float, default=1000.0)
    parser.add_argument("--max-open-positions", type=int, default=100)
    parser.add_argument("--max-strategy-open-positions", type=int, default=20)
    parser.add_argument("--pending-hold-days", type=float, default=3.0)
    parser.set_defaults(csv=ROOT / "portfolio_backtest_report.csv", md=ROOT / "portfolio_backtest_report.md")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.since_dt = parse_dt(args.since)
    accepted, rejects, max_open_stake, max_open_positions = replay(args)
    rows = summarize(accepted, rejects, args)
    write_csv(rows, args.csv)
    text = render(rows, accepted, max_open_stake, max_open_positions, args)
    args.md.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
