#!/usr/bin/env python3
"""Read-only parameter sweep for the active weather direction retest.

The goal is not to prove a strategy with weak data. It is to prevent blind
loosening/tightening by replaying already captured audit rows with multiple
parameter sets and final-only PnL.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import portfolio_backtest


ROOT = Path(__file__).resolve().parent
DEFAULT_SINCE = "2026-05-25T13:58:41Z"


@dataclass(frozen=True)
class SweepCase:
    name: str
    max_source_age_sec: float
    max_slippage_bps: float
    max_source_to_ask_gap: float
    min_ask_depth_usdc: float
    min_direction_edge: float
    max_open_positions: int
    max_strategy_open_positions: int


@dataclass
class SweepResult:
    name: str
    selected: int
    final: int
    pending: int
    wins: int
    losses: int
    pnl: float
    roi: float
    max_drawdown: float
    max_open_stake: float
    max_open_positions_observed: int
    cap_rejects: int
    strategy_cap_rejects: int
    verdict: str
    notes: str


def base_args(case: SweepCase, cli: argparse.Namespace) -> SimpleNamespace:
    return SimpleNamespace(
        strategy=["weather_direction_retest"],
        stake_usdc=cli.stake_usdc,
        since=cli.since,
        since_dt=portfolio_backtest.parse_dt(cli.since),
        wallet=["Poligarch", "Railbird"],
        outcome=["Yes", "No"],
        price_bucket=["0.8-0.9", "0.9-1.0"],
        min_source_price=0.80,
        max_source_price=0.995,
        min_entry_price=0.80,
        max_entry_price=0.995,
        max_slippage_bps=case.max_slippage_bps,
        max_source_to_ask_gap=case.max_source_to_ask_gap,
        max_source_age_sec=case.max_source_age_sec,
        min_ask_depth_usdc=case.min_ask_depth_usdc,
        min_direction_edge=case.min_direction_edge,
        require_live_fill=True,
        bankroll_usdc=cli.bankroll_usdc,
        max_open_positions=case.max_open_positions,
        max_strategy_open_positions=case.max_strategy_open_positions,
        pending_hold_days=3.0,
    )


def max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def verdict_for(result: SweepResult) -> tuple[str, str]:
    if result.final < 5:
        return "WEAK_SAMPLE", "final sample < 5"
    if result.losses > 0:
        return "REJECT", "has finalized losses"
    if result.roi < 3.0:
        return "REJECT", "final ROI < 3%"
    if result.final < 30:
        return "OBSERVE", "positive but final sample < 30"
    return "CANDIDATE", "passes sample/ROI/loss gates"


def run_case(case: SweepCase, cli: argparse.Namespace) -> SweepResult:
    args = base_args(case, cli)
    accepted, rejects, max_open_stake, max_open_positions = portfolio_backtest.replay(args)
    final = [trade for trade in accepted if portfolio_backtest.audit_backtest.is_final(trade.row)]
    pnls = [trade.pnl for trade in final]
    stake = len(final) * cli.stake_usdc
    pnl = sum(pnls)
    result = SweepResult(
        name=case.name,
        selected=len(accepted),
        final=len(final),
        pending=len(accepted) - len(final),
        wins=sum(1 for value in pnls if value > 0),
        losses=sum(1 for value in pnls if value < 0),
        pnl=pnl,
        roi=pnl / stake * 100 if stake else 0.0,
        max_drawdown=max_drawdown(pnls),
        max_open_stake=max_open_stake,
        max_open_positions_observed=max_open_positions,
        cap_rejects=rejects.get("weather_direction_retest", {}).get("capital", 0),
        strategy_cap_rejects=rejects.get("weather_direction_retest", {}).get("strategy_cap", 0),
        verdict="",
        notes="",
    )
    result.verdict, result.notes = verdict_for(result)
    return result


def sweep_cases() -> list[SweepCase]:
    return [
        SweepCase("current_guarded_2slot", 90, 350, 0.035, 20, 0.005, 2, 2),
        SweepCase("previous_6slot", 90, 350, 0.035, 20, 0.005, 6, 6),
        SweepCase("looser_10slot", 90, 350, 0.035, 20, 0.005, 10, 10),
        SweepCase("tighter_slippage", 90, 250, 0.025, 20, 0.005, 6, 6),
        SweepCase("tighter_age", 60, 350, 0.035, 20, 0.005, 6, 6),
        SweepCase("tighter_all", 60, 250, 0.025, 30, 0.010, 6, 6),
        SweepCase("slightly_looser_age", 120, 350, 0.035, 20, 0.005, 6, 6),
        SweepCase("slightly_looser_slip", 90, 450, 0.045, 20, 0.005, 6, 6),
    ]


def write_csv(rows: list[SweepResult], path: Path) -> None:
    fields = list(SweepResult.__dataclass_fields__.keys())
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for result in rows:
            row = result.__dict__.copy()
            for key in ("pnl", "roi", "max_drawdown", "max_open_stake"):
                row[key] = f"{row[key]:.6f}"
            writer.writerow(row)


def render(rows: list[SweepResult], cli: argparse.Namespace) -> str:
    lines = [
        "# Weather Direction Parameter Sweep",
        "",
        "Read-only portfolio replay. Final ROI uses finalized slippage_final_pnl only.",
        "",
        f"- since: {cli.since}",
        f"- bankroll_usdc: {cli.bankroll_usdc:.2f}",
        f"- stake_usdc: {cli.stake_usdc:.2f}",
        "",
        "| case | verdict | selected | final | pending | W/L | pnl | ROI | max DD | max open stake | cap rejects | notes |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.name} | {row.verdict} | {row.selected} | {row.final} | {row.pending} | "
            f"{row.wins}/{row.losses} | {row.pnl:.4f} | {row.roi:.2f}% | {row.max_drawdown:.4f} | "
            f"{row.max_open_stake:.2f} | {row.cap_rejects + row.strategy_cap_rejects} | {row.notes} |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Weather direction retest parameter sweep")
    parser.add_argument("--once", action="store_true", help="Run one sweep and exit")
    parser.add_argument("--since", default=DEFAULT_SINCE)
    parser.add_argument("--stake-usdc", type=float, default=10.0)
    parser.add_argument("--bankroll-usdc", type=float, default=1000.0)
    parser.add_argument("--csv", type=Path, default=ROOT / "weather_direction_parameter_sweep.csv")
    parser.add_argument("--md", type=Path, default=ROOT / "weather_direction_parameter_sweep.md")
    return parser


def main() -> int:
    cli = build_parser().parse_args()
    rows = [run_case(case, cli) for case in sweep_cases()]
    rows.sort(key=lambda row: (row.verdict != "CANDIDATE", row.verdict != "OBSERVE", -row.final, -row.roi, row.losses))
    write_csv(rows, cli.csv)
    text = render(rows, cli)
    cli.md.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
