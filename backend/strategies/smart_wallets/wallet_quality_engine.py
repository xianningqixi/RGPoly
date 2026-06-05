#!/usr/bin/env python3
"""Score copy-trading wallets using realized, slippage-adjusted audit data.

This is a reporting tool only. It does not change any running strategy.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from realized_pnl_report import (
    AUDIT_FILES as REALIZED_AUDIT_FILES,
    STRATEGY_KEYS,
    final_pnl_value,
    is_realized,
    row_time_value,
    wallet_value,
)

AUDIT_FILES = {STRATEGY_KEYS[name]: path for name, path in REALIZED_AUDIT_FILES.items()}

FIELDS = [
    "strategy",
    "wallet",
    "total_trades",
    "realized_trades",
    "pending_trades",
    "wins",
    "losses",
    "realized_stake",
    "realized_pnl",
    "realized_roi_pct",
    "win_rate_pct",
    "avg_cost_slippage_bps",
    "max_drawdown",
    "worst_market_pnl",
    "worst_market_slug",
    "max_consecutive_losses",
    "classification",
    "recommended_action",
    "reason",
]


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def parse_dt(value: str) -> datetime:
    try:
        return datetime.fromisoformat((value or "").replace("Z", "+00:00"))
    except Exception:
        return datetime.min


def latest_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            row_id = row.get("id") or str(len(rows))
            rows[row_id] = row
    return rows


def realized(row: dict[str, str]) -> bool:
    return is_realized(row)


def max_drawdown(pnls: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def max_consecutive_losses(rows: list[dict[str, str]]) -> int:
    best = 0
    current = 0
    for row in rows:
        if final_pnl_value(row) < 0:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def classify(item: dict[str, Any]) -> tuple[str, str, str]:
    realized_trades = int(item["realized_trades"])
    roi = float(item["realized_roi_pct"])
    pnl = float(item["realized_pnl"])
    avg_slippage = float(item["avg_cost_slippage_bps"])
    drawdown = float(item["max_drawdown"])
    worst_market_pnl = float(item["worst_market_pnl"])
    consecutive_losses = int(item["max_consecutive_losses"])

    if realized_trades == 0:
        return "OBSERVE", "keep_observing", "no finalized trades yet"
    if realized_trades < 30:
        if pnl > 0 and roi > 3:
            return "OBSERVE", "keep_small_observation_stake", "positive but sample size below 30"
        if pnl < 0:
            return "DOWNWEIGHT", "reduce_or_pause_until_more_evidence", "negative realized pnl with small sample"
        return "OBSERVE", "keep_observing", "sample size below 30"
    if pnl < 0 or roi < 0:
        return "PAUSE_SUGGESTED", "pause_new_entries", "negative realized pnl after sufficient sample"
    if avg_slippage > 250:
        return "DOWNWEIGHT", "tighten_slippage_and_age_filters", "average cost slippage above 250bps"
    if consecutive_losses >= 3:
        return "DOWNWEIGHT", "reduce_stake_after_loss_cluster", "three or more consecutive realized losses"
    if pnl > 0 and drawdown > pnl * 0.5:
        return "DOWNWEIGHT", "cap_market_exposure", "drawdown exceeds 50 percent of cumulative pnl"
    if pnl > 0 and worst_market_pnl < -(pnl * 0.5):
        return "DOWNWEIGHT", "lower_per_market_cap", "single market loss is too concentrated"
    if roi > 3:
        return "MAIN_POOL", "eligible_for_main_pool", "stable realized ROI above threshold"
    return "OBSERVE", "keep_observing", "realized ROI not high enough for main pool"


def score_strategy(strategy: str, path: Path) -> list[dict[str, Any]]:
    rows = latest_rows(path)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows.values():
        wallet = wallet_value(row)
        grouped[wallet].append(row)

    scored: list[dict[str, Any]] = []
    for wallet, all_rows in grouped.items():
        final_rows = sorted([row for row in all_rows if realized(row)], key=lambda row: parse_dt(row_time_value(row)))
        total = len(all_rows)
        pending = total - len(final_rows)
        wins = sum(1 for row in final_rows if final_pnl_value(row) > 0)
        losses = sum(1 for row in final_rows if final_pnl_value(row) < 0)
        stake = sum(fnum(row.get("stake")) for row in final_rows)
        pnl = sum(final_pnl_value(row) for row in final_rows)
        roi = pnl / stake * 100 if stake else 0.0
        win_rate = wins / len(final_rows) * 100 if final_rows else 0.0
        avg_cost_slippage = (
            sum(max(0.0, fnum(row.get("slippage_bps"))) for row in final_rows) / len(final_rows)
            if final_rows
            else 0.0
        )
        market_pnl: dict[str, float] = defaultdict(float)
        for row in final_rows:
            market_pnl[row.get("slug") or "unknown"] += final_pnl_value(row)
        worst_slug = ""
        worst_pnl = 0.0
        if market_pnl:
            worst_slug, worst_pnl = min(market_pnl.items(), key=lambda item: item[1])
        item: dict[str, Any] = {
            "strategy": strategy,
            "wallet": wallet,
            "total_trades": total,
            "realized_trades": len(final_rows),
            "pending_trades": pending,
            "wins": wins,
            "losses": losses,
            "realized_stake": stake,
            "realized_pnl": pnl,
            "realized_roi_pct": roi,
            "win_rate_pct": win_rate,
            "avg_cost_slippage_bps": avg_cost_slippage,
            "max_drawdown": max_drawdown([final_pnl_value(row) for row in final_rows]),
            "worst_market_pnl": worst_pnl,
            "worst_market_slug": worst_slug,
            "max_consecutive_losses": max_consecutive_losses(final_rows),
        }
        classification, action, reason = classify(item)
        item["classification"] = classification
        item["recommended_action"] = action
        item["reason"] = reason
        scored.append(item)
    return scored


def all_scores() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for strategy, path in AUDIT_FILES.items():
        rows.extend(score_strategy(strategy, path))
    return sorted(
        rows,
        key=lambda row: (
            {"MAIN_POOL": 0, "OBSERVE": 1, "DOWNWEIGHT": 2, "PAUSE_SUGGESTED": 3}.get(str(row["classification"]), 9),
            -float(row["realized_pnl"]),
        ),
    )


def write_csv(rows: list[dict[str, Any]], path: Path = Path("wallet_quality_report.csv")) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in ["realized_stake", "realized_pnl", "realized_roi_pct", "win_rate_pct", "avg_cost_slippage_bps", "max_drawdown", "worst_market_pnl"]:
                out[key] = f"{fnum(out.get(key)):.6f}"
            writer.writerow({field: out.get(field, "") for field in FIELDS})


def render(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Wallet Quality Report",
        "",
        "Only finalized trades are counted. PnL uses slippage_final_pnl.",
        "",
        "| class | strategy | wallet | realized | ROI | PnL | maxDD | avg slip | action | reason |",
        "|---|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['classification']} | {row['strategy']} | {row['wallet']} | {row['realized_trades']} | "
            f"{fnum(row['realized_roi_pct']):.2f}% | {fnum(row['realized_pnl']):.4f}U | "
            f"{fnum(row['max_drawdown']):.4f}U | {fnum(row['avg_cost_slippage_bps']):.0f} | "
            f"{row['recommended_action']} | {row['reason']} |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one quality scoring pass and exit")
    return parser


def main() -> int:
    build_parser().parse_args()
    rows = all_scores()
    write_csv(rows)
    text = render(rows)
    Path("wallet_quality_report.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
