#!/usr/bin/env python3
"""Decide whether the current simulation evidence is positive enough to scale.

This report follows the current objective: drawdowns and losing trades are
allowed, but the overall realized curve must be profitable. It only counts
finalized `slippage_final_pnl` as realized profit. Pending rows are risk
exposure, never profit.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
CURRENT_CONFIG = ROOT / "current_config_report.csv"
CURRENT_EQUITY = ROOT / "realized_current_config_equity_curve.csv"
RECOVERY_BACKTEST = ROOT / "recovery_backtest_matrix.csv"
RUNTIME_STATUS = ROOT / "runtime_strategy_status.csv"
OUT_CSV = ROOT / "stability_verdict_report.csv"
OUT_MD = ROOT / "stability_verdict_report.md"

FIELDS = [
    "scope",
    "verdict",
    "final_trades",
    "pending_trades",
    "wins",
    "losses",
    "stake",
    "pnl",
    "roi",
    "max_drawdown",
    "drawdown_to_pnl",
    "backtest_case",
    "backtest_final",
    "backtest_pending",
    "backtest_pnl",
    "backtest_roi",
    "backtest_drawdown_to_pnl",
    "runtime_attention",
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


def max_drawdown(values: list[float]) -> float:
    peak = 0.0
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        worst = max(worst, peak - value)
    return worst


def active_current_rows() -> list[dict[str, str]]:
    return [row for row in read_csv(CURRENT_CONFIG) if row.get("intended_state") != "PAUSED"]


def best_recovery_candidate(preferred_case: str) -> dict[str, str]:
    rows = read_csv(RECOVERY_BACKTEST)
    if preferred_case:
        for row in rows:
            if row.get("case") == preferred_case:
                return row
    candidates = [row for row in rows if row.get("verdict") == "CANDIDATE"]
    if not candidates:
        return {}
    candidates.sort(
        key=lambda row: (
            -inum(row.get("final")),
            fnum(row.get("max_drawdown")) / fnum(row.get("pnl")) if fnum(row.get("pnl")) > 0 else 999.0,
            -fnum(row.get("roi")),
        )
    )
    return candidates[0]


def build_row(args: argparse.Namespace) -> dict[str, Any]:
    active = active_current_rows()
    final_trades = sum(inum(row.get("final_since_cutoff")) for row in active)
    pending_trades = sum(inum(row.get("pending_since_cutoff")) for row in active)
    wins = sum(inum(row.get("wins")) for row in active)
    losses = sum(inum(row.get("losses")) for row in active)
    stake = sum(fnum(row.get("stake")) for row in active)
    pnl = sum(fnum(row.get("pnl")) for row in active)
    roi = pnl / stake * 100 if stake else 0.0

    equity_rows = read_csv(CURRENT_EQUITY)
    active_equity = [fnum(row.get("active_current_equity")) for row in equity_rows]
    drawdown = max_drawdown(active_equity)
    drawdown_to_pnl = drawdown / pnl if pnl > 0 else 999.0

    backtest = best_recovery_candidate(args.preferred_backtest_case)
    backtest_case = backtest.get("case") or ""
    backtest_final = inum(backtest.get("final"))
    backtest_pending = inum(backtest.get("pending"))
    backtest_pnl = fnum(backtest.get("pnl"))
    backtest_roi = fnum(backtest.get("roi"))
    backtest_drawdown_to_pnl = (
        fnum(backtest.get("max_drawdown")) / backtest_pnl if backtest_pnl > 0 else 999.0
    )

    runtime = read_csv(RUNTIME_STATUS)
    runtime_attention = sum(1 for row in runtime if str(row.get("status") or "").startswith("ATTENTION"))

    reasons: list[str] = []
    if final_trades < args.min_final:
        reasons.append(f"final sample {final_trades} < {args.min_final}")
    if roi < args.min_roi:
        reasons.append(f"current ROI {roi:.2f}% < {args.min_roi:.2f}%")
    if not backtest:
        reasons.append("no positive recovery backtest candidate")
    elif backtest_roi < args.min_backtest_roi:
        reasons.append(f"best backtest ROI {backtest_roi:.2f}% < {args.min_backtest_roi:.2f}%")
    elif backtest_drawdown_to_pnl > args.max_backtest_drawdown_to_pnl:
        reasons.append(
            f"best backtest drawdown/pnl {backtest_drawdown_to_pnl:.2f} > {args.max_backtest_drawdown_to_pnl:.2f}"
        )
    if drawdown_to_pnl > args.max_drawdown_to_pnl:
        reasons.append(f"drawdown/pnl {drawdown_to_pnl:.2f} > {args.max_drawdown_to_pnl:.2f}")
    if runtime_attention:
        reasons.append(f"runtime attention count {runtime_attention} > 0")

    if not active:
        verdict = "NO_ACTIVE_STRATEGY"
        reasons.append("no active strategy")
    elif reasons:
        verdict = "NOT_STABLE_YET"
    else:
        verdict = "STABLE_POSITIVE"

    return {
        "scope": "current_active_config",
        "verdict": verdict,
        "final_trades": final_trades,
        "pending_trades": pending_trades,
        "wins": wins,
        "losses": losses,
        "stake": stake,
        "pnl": pnl,
        "roi": roi,
        "max_drawdown": drawdown,
        "drawdown_to_pnl": drawdown_to_pnl if pnl > 0 else 0.0,
        "backtest_case": backtest_case,
        "backtest_final": backtest_final,
        "backtest_pending": backtest_pending,
        "backtest_pnl": backtest_pnl,
        "backtest_roi": backtest_roi,
        "backtest_drawdown_to_pnl": backtest_drawdown_to_pnl if backtest_pnl > 0 else 0.0,
        "runtime_attention": runtime_attention,
        "reason": "; ".join(reasons) if reasons else "meets all stable-positive gates",
    }


def write_csv(row: dict[str, Any], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        out = dict(row)
        for key in [
            "stake",
            "pnl",
            "roi",
            "max_drawdown",
            "drawdown_to_pnl",
            "backtest_pnl",
            "backtest_roi",
            "backtest_drawdown_to_pnl",
        ]:
            out[key] = f"{fnum(out.get(key)):.6f}"
        writer.writerow({field: out.get(field, "") for field in FIELDS})


def write_md(row: dict[str, Any], path: Path) -> None:
    lines = [
        "# Stability Verdict Report",
        "",
        "Simulation only. Losing trades and drawdowns are allowed; profit must be finalized `slippage_final_pnl`.",
        "",
        "| scope | verdict | final/pending | W/L | stake | pnl | ROI | max DD | DD/PnL | backtest | backtest ROI | backtest DD/PnL | reason |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---|",
        (
            f"| {row['scope']} | {row['verdict']} | {row['final_trades']}/{row['pending_trades']} | "
            f"{row['wins']}/{row['losses']} | {fnum(row['stake']):.2f}U | {fnum(row['pnl']):.4f}U | "
            f"{fnum(row['roi']):.2f}% | {fnum(row['max_drawdown']):.4f}U | "
            f"{fnum(row['drawdown_to_pnl']):.2f} | {row['backtest_case']} | "
            f"{fnum(row['backtest_roi']):.2f}% | {fnum(row['backtest_drawdown_to_pnl']):.2f} | "
            f"{row['reason']} |"
        ),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--min-final", type=int, default=30)
    parser.add_argument("--min-roi", type=float, default=3.0)
    parser.add_argument("--min-backtest-roi", type=float, default=3.0)
    parser.add_argument("--max-drawdown-to-pnl", type=float, default=1.0)
    parser.add_argument("--max-backtest-drawdown-to-pnl", type=float, default=1.0)
    parser.add_argument("--preferred-backtest-case", default="btc_directional_optimizer_best")
    parser.add_argument("--csv", type=Path, default=OUT_CSV)
    parser.add_argument("--md", type=Path, default=OUT_MD)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    row = build_row(args)
    write_csv(row, args.csv)
    write_md(row, args.md)
    print("Stability verdict")
    print(f"- verdict: {row['verdict']}")
    print(f"- final: {row['final_trades']} pending: {row['pending_trades']} W/L: {row['wins']}/{row['losses']}")
    print(f"- pnl: {fnum(row['pnl']):.4f}U roi: {fnum(row['roi']):.2f}%")
    print(f"- reason: {row['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
