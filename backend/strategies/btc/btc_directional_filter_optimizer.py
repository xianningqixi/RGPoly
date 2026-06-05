#!/usr/bin/env python3
"""Search BTC directional copy filters with finalized PnL only.

This is advisory and read-only. It allows losing trades, but ranks
configurations by positive realized PnL, ROI, sample size, and drawdown.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import itertools
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import audit_backtest


ROOT = Path.cwd()
STRATEGY = "btc_directional_copy"


@dataclass(frozen=True)
class FilterCase:
    name: str
    market_types: tuple[str, ...]
    outcomes: tuple[str, ...]
    min_source_price: float
    max_source_price: float
    max_slippage_bps: float
    max_source_to_ask_gap: float
    max_source_age_sec: float
    min_ask_depth_usdc: float
    max_open_positions: int


@dataclass
class Result:
    name: str
    verdict: str
    final: int
    pending: int
    wins: int
    losses: int
    stake: float
    pnl: float
    roi: float
    max_drawdown: float
    drawdown_to_pnl: float
    max_open_stake: float
    market_types: str
    outcomes: str
    source_price_range: str
    max_slippage_bps: float
    max_source_to_ask_gap: float
    max_source_age_sec: float
    min_ask_depth_usdc: float
    max_open_positions: int
    notes: str


def fnum(value: Any, default: float = 0.0) -> float:
    return audit_backtest.fnum(value, default)


def market_type(row: dict[str, str]) -> str:
    slug = (row.get("slug") or "").lower()
    title = (row.get("title") or "").lower()
    text = f"{title} {slug}"
    if "between" in text:
        return "range"
    if "reach" in text or "dip" in text:
        return "reach_or_dip"
    if "above" in text or "below" in text:
        return "above_below"
    return "other"


def latest_rows() -> list[dict[str, str]]:
    return audit_backtest.latest_rows(audit_backtest.read_rows(audit_backtest.AUDIT_FILES[STRATEGY]))


def is_tradeable(row: dict[str, str], case: FilterCase) -> bool:
    if (row.get("would_live_fill") or "").upper() not in {"YES", "TRUE", "1"}:
        return False
    if market_type(row) not in case.market_types:
        return False
    if (row.get("outcome") or "") not in case.outcomes:
        return False
    source_price = fnum(row.get("source_price"))
    if source_price < case.min_source_price or source_price > case.max_source_price:
        return False
    if fnum(row.get("slippage_bps")) > case.max_slippage_bps:
        return False
    if audit_backtest.source_to_ask_gap(row) > case.max_source_to_ask_gap:
        return False
    if audit_backtest.source_age_sec(row) > case.max_source_age_sec:
        return False
    if fnum(row.get("ask_depth_usdc")) < case.min_ask_depth_usdc:
        return False
    return True


def max_drawdown(pnls: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def replay(rows: list[dict[str, str]], case: FilterCase, args: argparse.Namespace) -> Result:
    open_heap: list[tuple[datetime, int]] = []
    open_stake = 0.0
    max_open_stake = 0.0
    seq = 0
    pending = 0
    pnls: list[float] = []

    candidates = [row for row in rows if audit_backtest.row_time(row) >= args.since_dt and is_tradeable(row, case)]
    candidates.sort(key=audit_backtest.row_time)

    for row in candidates:
        entry_time = audit_backtest.row_time(row)
        while open_heap and open_heap[0][0] <= entry_time:
            heapq.heappop(open_heap)
            open_stake = max(0.0, open_stake - args.stake_usdc)
        if len(open_heap) >= case.max_open_positions:
            continue
        if open_stake + args.stake_usdc > args.bankroll_usdc:
            continue

        if audit_backtest.is_final(row):
            pnls.append(audit_backtest.final_pnl(row, args.stake_usdc))
            exit_time = audit_backtest.parse_dt(row.get("audit_ts"))
        else:
            pending += 1
            exit_time = entry_time + timedelta(days=args.pending_hold_days)
        if exit_time <= entry_time:
            exit_time = entry_time + timedelta(seconds=1)
        seq += 1
        open_stake += args.stake_usdc
        max_open_stake = max(max_open_stake, open_stake)
        heapq.heappush(open_heap, (exit_time, seq))

    stake = len(pnls) * args.stake_usdc
    pnl = sum(pnls)
    roi = pnl / stake * 100 if stake else 0.0
    drawdown = max_drawdown(pnls)
    dd_to_pnl = drawdown / pnl if pnl > 0 else math.inf
    verdict, notes = verdict_for(len(pnls), pnl, roi, dd_to_pnl)
    return Result(
        name=case.name,
        verdict=verdict,
        final=len(pnls),
        pending=pending,
        wins=sum(1 for pnl in pnls if pnl > 0),
        losses=sum(1 for pnl in pnls if pnl < 0),
        stake=stake,
        pnl=pnl,
        roi=roi,
        max_drawdown=drawdown,
        drawdown_to_pnl=dd_to_pnl if math.isfinite(dd_to_pnl) else 999.0,
        max_open_stake=max_open_stake,
        market_types="+".join(case.market_types),
        outcomes="+".join(case.outcomes),
        source_price_range=f"{case.min_source_price:.2f}-{case.max_source_price:.2f}",
        max_slippage_bps=case.max_slippage_bps,
        max_source_to_ask_gap=case.max_source_to_ask_gap,
        max_source_age_sec=case.max_source_age_sec,
        min_ask_depth_usdc=case.min_ask_depth_usdc,
        max_open_positions=case.max_open_positions,
        notes=notes,
    )


def verdict_for(final: int, pnl: float, roi: float, dd_to_pnl: float) -> tuple[str, str]:
    if final < 20:
        return "WEAK_SAMPLE", "final sample < 20"
    if pnl <= 0 or roi <= 0:
        return "REJECT", "realized PnL/ROI <= 0"
    if final < 50:
        return "OBSERVE", "positive but final sample < 50"
    if dd_to_pnl > 1.0:
        return "OBSERVE", "positive but max drawdown exceeds total profit"
    if dd_to_pnl > 0.7:
        return "OBSERVE", "positive but drawdown is still high"
    if roi < 3.0:
        return "OBSERVE", "positive but ROI < 3%"
    return "CANDIDATE", "positive with acceptable drawdown"


def build_cases() -> list[FilterCase]:
    market_sets = [
        ("above_below",),
        ("above_below", "range"),
        ("above_below", "reach_or_dip"),
        ("above_below", "range", "reach_or_dip"),
    ]
    outcome_sets = [("No",), ("Yes",), ("No", "Yes")]
    price_ranges = [(0.10, 0.99), (0.30, 0.99), (0.40, 0.99), (0.50, 0.99), (0.60, 0.99), (0.70, 0.99)]
    slippage_caps = [150, 250, 350, 500]
    gap_caps = [0.015, 0.025, 0.035, 0.05]
    age_caps = [60, 90, 120]
    depth_mins = [20, 50, 100]
    open_caps = [5, 10, 20]
    cases: list[FilterCase] = []
    for market_set, outcome_set, price_range, slip, gap, age, depth, open_cap in itertools.product(
        market_sets, outcome_sets, price_ranges, slippage_caps, gap_caps, age_caps, depth_mins, open_caps
    ):
        name = (
            f"m={'+'.join(market_set)}|o={'+'.join(outcome_set)}|p={price_range[0]:.1f}-{price_range[1]:.1f}|"
            f"slip<={slip}|gap<={gap}|age<={age}|depth>={depth}|open<={open_cap}"
        )
        cases.append(
            FilterCase(
                name=name,
                market_types=market_set,
                outcomes=outcome_set,
                min_source_price=price_range[0],
                max_source_price=price_range[1],
                max_slippage_bps=slip,
                max_source_to_ask_gap=gap,
                max_source_age_sec=age,
                min_ask_depth_usdc=depth,
                max_open_positions=open_cap,
            )
        )
    return cases


def write_csv(rows: list[Result], path: Path) -> None:
    fields = list(Result.__dataclass_fields__.keys())
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for result in rows:
            row = result.__dict__.copy()
            for key in (
                "stake",
                "pnl",
                "roi",
                "max_drawdown",
                "drawdown_to_pnl",
                "max_open_stake",
                "max_slippage_bps",
                "max_source_to_ask_gap",
                "max_source_age_sec",
                "min_ask_depth_usdc",
            ):
                row[key] = f"{float(row[key]):.6f}"
            writer.writerow(row)


def render(rows: list[Result], args: argparse.Namespace) -> str:
    lines = [
        "# BTC Directional Filter Optimizer",
        "",
        "Read-only parameter search. Losing trades are allowed; ranking requires positive finalized slippage_final_pnl.",
        "",
        f"- since: {args.since}",
        f"- bankroll_usdc: {args.bankroll_usdc:.2f}",
        f"- stake_usdc: {args.stake_usdc:.2f}",
        f"- searched_cases: {args.searched_cases}",
        "",
        "| rank | verdict | final | W/L | pnl | ROI | max DD | DD/PnL | market | outcome | price | slip | gap | age | depth | open | notes |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for idx, row in enumerate(rows[: args.top], start=1):
        lines.append(
            f"| {idx} | {row.verdict} | {row.final} | {row.wins}/{row.losses} | {row.pnl:.4f} | "
            f"{row.roi:.2f}% | {row.max_drawdown:.4f} | {row.drawdown_to_pnl:.2f} | "
            f"{row.market_types} | {row.outcomes} | {row.source_price_range} | {row.max_slippage_bps:.0f} | "
            f"{row.max_source_to_ask_gap:.3f} | {row.max_source_age_sec:.0f}s | {row.min_ask_depth_usdc:.0f} | "
            f"{row.max_open_positions} | {row.notes} |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Optimize BTC directional copy filters from audit logs")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--since", default="2026-05-20T00:00:00Z")
    parser.add_argument("--stake-usdc", type=float, default=10.0)
    parser.add_argument("--bankroll-usdc", type=float, default=1000.0)
    parser.add_argument("--pending-hold-days", type=float, default=3.0)
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--csv", type=Path, default=ROOT / "btc_directional_filter_optimizer.csv")
    parser.add_argument("--md", type=Path, default=ROOT / "btc_directional_filter_optimizer.md")
    return parser


def sort_key(row: Result) -> tuple[int, int, float, float, float, int]:
    verdict_rank = {"CANDIDATE": 0, "OBSERVE": 1, "WEAK_SAMPLE": 2, "REJECT": 3}.get(row.verdict, 4)
    return (verdict_rank, -row.final, row.drawdown_to_pnl, -row.roi, -row.pnl, row.losses)


def main() -> int:
    args = build_parser().parse_args()
    args.since_dt = audit_backtest.parse_dt(args.since)
    rows = latest_rows()
    cases = build_cases()
    args.searched_cases = len(cases)
    results = [replay(rows, case, args) for case in cases]
    results.sort(key=sort_key)
    write_csv(results, args.csv)
    text = render(results, args)
    args.md.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
