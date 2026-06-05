#!/usr/bin/env python3
"""Recovery backtest matrix for local Polymarket simulation audits.

Read-only. This compares candidate recovery configurations after drawdown.
Only finalized `slippage_final_pnl` is counted as realized return.
"""

from __future__ import annotations

import argparse
import csv
import heapq
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

import audit_backtest


ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Case:
    name: str
    description: str
    strategies: tuple[str, ...]
    row_filter: Callable[[str, dict[str, str]], bool]
    max_open_positions: int = 100
    max_strategy_open_positions: int = 20


@dataclass
class Result:
    case: str
    selected: int
    final: int
    pending: int
    wins: int
    losses: int
    stake: float
    pnl: float
    roi: float
    max_drawdown: float
    max_open_stake: float
    max_open_positions_observed: int
    verdict: str
    notes: str


def fnum(value: object, default: float = 0.0) -> float:
    return audit_backtest.fnum(value, default)


def latest_strategy_rows(strategy: str) -> list[dict[str, str]]:
    path = audit_backtest.AUDIT_FILES[strategy]
    return audit_backtest.latest_rows(audit_backtest.read_rows(path))


def source_to_ask_gap(row: dict[str, str]) -> float:
    return audit_backtest.source_to_ask_gap(row)


def source_age_sec(row: dict[str, str]) -> float:
    return audit_backtest.source_age_sec(row)


def base_tradeable(row: dict[str, str]) -> bool:
    return (row.get("would_live_fill") or "").upper() in {"YES", "TRUE", "1"}


def no_filter(_strategy: str, row: dict[str, str]) -> bool:
    return base_tradeable(row)


def btc_basic(_strategy: str, row: dict[str, str]) -> bool:
    return (
        base_tradeable(row)
        and fnum(row.get("ask_depth_usdc")) >= 20
        and source_age_sec(row) <= 120
        and fnum(row.get("slippage_bps")) <= 500
        and source_to_ask_gap(row) <= 0.05
    )


def btc_tight(_strategy: str, row: dict[str, str]) -> bool:
    return (
        base_tradeable(row)
        and fnum(row.get("ask_depth_usdc")) >= 50
        and source_age_sec(row) <= 90
        and fnum(row.get("slippage_bps")) <= 250
        and source_to_ask_gap(row) <= 0.025
    )


def btc_optimizer_best(_strategy: str, row: dict[str, str]) -> bool:
    return (
        base_tradeable(row)
        and fnum(row.get("ask_depth_usdc")) >= 20
        and source_age_sec(row) <= 60
        and fnum(row.get("slippage_bps")) <= 500
        and source_to_ask_gap(row) <= 0.035
        and 0.10 <= fnum(row.get("source_price")) <= 0.99
    )


def weather_direction_no_failed_bucket(_strategy: str, row: dict[str, str]) -> bool:
    if not base_tradeable(row):
        return False
    wallet = row.get("wallet_name") or ""
    outcome = row.get("outcome") or ""
    bucket = row.get("price_bucket") or audit_backtest.price_bucket(fnum(row.get("source_price")))
    if wallet == "Poligarch" and outcome == "Yes" and bucket == "0.8-0.9":
        return False
    return (
        wallet in {"Poligarch", "Railbird"}
        and outcome in {"Yes", "No"}
        and bucket in {"0.8-0.9", "0.9-1.0"}
        and source_age_sec(row) <= 90
        and fnum(row.get("slippage_bps")) <= 350
        and source_to_ask_gap(row) <= 0.035
        and fnum(row.get("ask_depth_usdc")) >= 20
    )


def weather_high_conf_only(_strategy: str, row: dict[str, str]) -> bool:
    bucket = row.get("price_bucket") or audit_backtest.price_bucket(fnum(row.get("source_price")))
    return weather_direction_no_failed_bucket(_strategy, row) and bucket == "0.9-1.0"


def build_cases() -> list[Case]:
    return [
        Case(
            "all_tradeable",
            "All simulated strategies with live-fill rows only.",
            tuple(sorted(audit_backtest.AUDIT_FILES)),
            no_filter,
        ),
        Case(
            "btc_directional_only_basic",
            "Only the historically best BTC directional wallet copy, moderate filters.",
            ("btc_directional_copy",),
            btc_basic,
        ),
        Case(
            "btc_directional_only_tight",
            "BTC directional only with tighter slippage/gap/depth filters.",
            ("btc_directional_copy",),
            btc_tight,
        ),
        Case(
            "btc_directional_optimizer_best",
            "BTC directional copy using current best filter search: source age <= 60s, gap <= 0.035, slippage <= 500bps.",
            ("btc_directional_copy",),
            btc_optimizer_best,
        ),
        Case(
            "weather_direction_no_failed_bucket",
            "Weather direction retest excluding Poligarch Yes 0.8-0.9.",
            ("weather_direction_retest",),
            weather_direction_no_failed_bucket,
            max_open_positions=2,
            max_strategy_open_positions=2,
        ),
        Case(
            "weather_direction_high_conf_only",
            "Weather direction retest only 0.9-1.0 confidence buckets.",
            ("weather_direction_retest",),
            weather_high_conf_only,
            max_open_positions=2,
            max_strategy_open_positions=2,
        ),
        Case(
            "btc_basic_plus_weather_high_conf",
            "BTC basic plus high-confidence weather observation candidate.",
            ("btc_directional_copy", "weather_direction_retest"),
            lambda strategy, row: btc_optimizer_best(strategy, row)
            if strategy == "btc_directional_copy"
            else weather_high_conf_only(strategy, row),
            max_open_positions=25,
            max_strategy_open_positions=20,
        ),
    ]


def load_candidates(case: Case, since_dt: datetime) -> list[tuple[str, dict[str, str]]]:
    candidates: list[tuple[str, dict[str, str]]] = []
    for strategy in case.strategies:
        for row in latest_strategy_rows(strategy):
            if audit_backtest.row_time(row) < since_dt:
                continue
            if not case.row_filter(strategy, row):
                continue
            candidates.append((strategy, row))
    candidates.sort(key=lambda item: audit_backtest.row_time(item[1]))
    return candidates


def max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def replay(case: Case, args: argparse.Namespace) -> Result:
    open_heap: list[tuple[datetime, int, str]] = []
    open_stake = 0.0
    max_open_stake = 0.0
    max_open_positions = 0
    seq = 0
    selected = 0
    final_pnls: list[float] = []
    pending = 0

    for strategy, row in load_candidates(case, args.since_dt):
        entry_time = audit_backtest.row_time(row)
        while open_heap and open_heap[0][0] <= entry_time:
            heapq.heappop(open_heap)
            open_stake = max(0.0, open_stake - args.stake_usdc)

        strategy_open = sum(1 for _, _, opened_strategy in open_heap if opened_strategy == strategy)
        if open_stake + args.stake_usdc > args.bankroll_usdc:
            continue
        if len(open_heap) >= case.max_open_positions:
            continue
        if strategy_open >= case.max_strategy_open_positions:
            continue

        selected += 1
        if audit_backtest.is_final(row):
            final_pnls.append(audit_backtest.final_pnl(row, args.stake_usdc))
            exit_time = audit_backtest.parse_dt(row.get("audit_ts"))
        else:
            pending += 1
            exit_time = entry_time + timedelta(days=args.pending_hold_days)

        if exit_time <= entry_time:
            exit_time = entry_time + timedelta(seconds=1)
        seq += 1
        open_stake += args.stake_usdc
        max_open_stake = max(max_open_stake, open_stake)
        max_open_positions = max(max_open_positions, len(open_heap) + 1)
        heapq.heappush(open_heap, (exit_time, seq, strategy))

    stake = len(final_pnls) * args.stake_usdc
    pnl = sum(final_pnls)
    roi = pnl / stake * 100 if stake else 0.0
    losses = sum(1 for value in final_pnls if value < 0)
    verdict, notes = verdict_for(len(final_pnls), roi, losses, max_drawdown(final_pnls), pnl)
    return Result(
        case=case.name,
        selected=selected,
        final=len(final_pnls),
        pending=pending,
        wins=sum(1 for value in final_pnls if value > 0),
        losses=losses,
        stake=stake,
        pnl=pnl,
        roi=roi,
        max_drawdown=max_drawdown(final_pnls),
        max_open_stake=max_open_stake,
        max_open_positions_observed=max_open_positions,
        verdict=verdict,
        notes=notes,
    )


def verdict_for(final: int, roi: float, losses: int, drawdown: float, pnl: float) -> tuple[str, str]:
    if final == 0:
        return "NO_DATA", "no finalized trades"
    if roi <= 0:
        return "REJECT", "final ROI <= 0"
    if final < 30:
        return "OBSERVE", "positive but final sample < 30"
    if drawdown > max(pnl * 0.5, 1.0):
        return "OBSERVE", "positive but drawdown is too high"
    if losses == 0:
        return "CANDIDATE", "positive, enough sample, zero finalized losses"
    return "CANDIDATE", "positive with enough sample"


def write_csv(rows: list[Result], path: Path) -> None:
    fields = list(Result.__dataclass_fields__.keys())
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for result in rows:
            row = result.__dict__.copy()
            for key in ("stake", "pnl", "roi", "max_drawdown", "max_open_stake"):
                row[key] = f"{row[key]:.6f}"
            writer.writerow(row)


def render(rows: list[Result], args: argparse.Namespace) -> str:
    lines = [
        "# Recovery Backtest Matrix",
        "",
        "Read-only replay from local audit logs. Realized ROI uses finalized slippage_final_pnl only.",
        "",
        f"- bankroll_usdc: {args.bankroll_usdc:.2f}",
        f"- stake_usdc: {args.stake_usdc:.2f}",
        f"- since: {args.since}",
        "",
        "| case | verdict | selected | final | pending | W/L | stake | pnl | ROI | max DD | max open stake | notes |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.case} | {row.verdict} | {row.selected} | {row.final} | {row.pending} | "
            f"{row.wins}/{row.losses} | {row.stake:.2f} | {row.pnl:.4f} | {row.roi:.2f}% | "
            f"{row.max_drawdown:.4f} | {row.max_open_stake:.2f} | {row.notes} |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare recovery backtest configurations")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--since", default="2026-05-20T00:00:00Z")
    parser.add_argument("--stake-usdc", type=float, default=10.0)
    parser.add_argument("--bankroll-usdc", type=float, default=1000.0)
    parser.add_argument("--pending-hold-days", type=float, default=3.0)
    parser.add_argument("--csv", type=Path, default=ROOT / "recovery_backtest_matrix.csv")
    parser.add_argument("--md", type=Path, default=ROOT / "recovery_backtest_matrix.md")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.since_dt = audit_backtest.parse_dt(args.since)
    rows = [replay(case, args) for case in build_cases()]
    rows.sort(key=lambda row: (row.verdict != "CANDIDATE", row.verdict != "OBSERVE", -row.roi, -row.final))
    write_csv(rows, args.csv)
    text = render(rows, args)
    args.md.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
