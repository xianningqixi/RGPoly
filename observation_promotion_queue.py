#!/usr/bin/env python3
"""Build a conservative observation queue for possible future promotion.

This report does not start bots or change allocation. It separates candidates
worth more paper observation from the current main positive curve.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
QUALITY = ROOT / "wallet_quality_report.csv"
CANDIDATES = ROOT / "btc_directional_candidate_pool.csv"
OUT_CSV = ROOT / "observation_promotion_queue.csv"
OUT_MD = ROOT / "observation_promotion_queue.md"

FIELDS = [
    "rank",
    "source",
    "strategy",
    "wallet",
    "action",
    "suggested_stake_usdc",
    "max_open_stake_usdc",
    "realized_trades",
    "pending_trades",
    "roi",
    "pnl",
    "max_drawdown",
    "avg_slippage_bps",
    "reason",
]


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def quality_rows() -> list[dict[str, Any]]:
    rows = []
    for row in read_csv(QUALITY):
        realized = int(fnum(row.get("realized_trades")))
        roi = fnum(row.get("realized_roi_pct"))
        pnl = fnum(row.get("realized_pnl"))
        drawdown = fnum(row.get("max_drawdown"))
        slip = fnum(row.get("avg_cost_slippage_bps"))
        losses = int(fnum(row.get("losses")))
        if row.get("classification") != "OBSERVE":
            continue
        if realized <= 0 or pnl <= 0 or roi <= 0 or losses > 1:
            continue
        if drawdown > max(0.25, pnl * 0.75):
            continue
        if slip > 300:
            continue
        action = "OBSERVE_MORE"
        stake = 1.0
        cap = 2.0
        if realized >= 10 and roi >= 3 and losses == 0:
            action = "NEAR_PROMOTION_WATCH"
            stake = 1.0
            cap = 3.0
        rows.append(
            {
                "source": "quality",
                "strategy": row.get("strategy", ""),
                "wallet": row.get("wallet", ""),
                "action": action,
                "suggested_stake_usdc": stake,
                "max_open_stake_usdc": cap,
                "realized_trades": realized,
                "pending_trades": int(fnum(row.get("pending_trades"))),
                "roi": roi,
                "pnl": pnl,
                "max_drawdown": drawdown,
                "avg_slippage_bps": slip,
                "reason": row.get("reason", ""),
            }
        )
    return rows


def candidate_rows() -> list[dict[str, Any]]:
    rows = []
    for row in read_csv(CANDIDATES):
        action = row.get("action", "")
        if action not in {"ADD_TO_OBSERVATION", "KEEP_OBSERVING"}:
            continue
        sim_final = int(fnum(row.get("sim_final")))
        sim_roi = fnum(row.get("sim_final_roi"))
        score = fnum(row.get("score"))
        if sim_final > 0 and sim_roi < 0:
            continue
        if score < 300 and action == "ADD_TO_OBSERVATION":
            continue
        rows.append(
            {
                "source": "candidate_pool",
                "strategy": "btc_directional_candidate_copy",
                "wallet": row.get("alias", ""),
                "action": "SHADOW_OBSERVE" if sim_final == 0 else "OBSERVE_MORE",
                "suggested_stake_usdc": 0.0 if sim_final == 0 else 1.0,
                "max_open_stake_usdc": 0.0 if sim_final == 0 else 2.0,
                "realized_trades": sim_final,
                "pending_trades": int(fnum(row.get("sim_pending"))),
                "roi": sim_roi,
                "pnl": 0.0,
                "max_drawdown": 0.0,
                "avg_slippage_bps": 0.0,
                "reason": row.get("reason", ""),
            }
        )
    return rows


def build_rows(limit: int) -> list[dict[str, Any]]:
    rows = quality_rows() + candidate_rows()
    rows.sort(
        key=lambda row: (
            row["action"] != "NEAR_PROMOTION_WATCH",
            row["suggested_stake_usdc"] <= 0,
            -int(row["realized_trades"]),
            -float(row["roi"]),
        )
    )
    deduped = []
    seen = set()
    for row in rows:
        key = (row.get("strategy"), row.get("wallet"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    out = []
    for index, row in enumerate(deduped[:limit], start=1):
        row = dict(row)
        row["rank"] = index
        out.append(row)
    return out


def write_csv(rows: list[dict[str, Any]], path: Path = OUT_CSV) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in ("suggested_stake_usdc", "max_open_stake_usdc", "roi", "pnl", "max_drawdown", "avg_slippage_bps"):
                out[key] = f"{fnum(out.get(key)):.6f}"
            writer.writerow({field: out.get(field, "") for field in FIELDS})


def render(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Observation Promotion Queue",
        "",
        "Advisory only. These candidates are not part of the current main realized ROI curve.",
        "",
        "| rank | action | source | strategy | wallet | stake | cap | final/pending | ROI | PnL | reason |",
        "|---:|---|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['rank']} | {row['action']} | {row['source']} | {row['strategy']} | {row['wallet']} | "
            f"{fnum(row['suggested_stake_usdc']):.2f} | {fnum(row['max_open_stake_usdc']):.2f} | "
            f"{int(row['realized_trades'])}/{int(row['pending_trades'])} | {fnum(row['roi']):.2f}% | "
            f"{fnum(row['pnl']):.4f} | {row['reason']} |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--limit", type=int, default=20)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = build_rows(args.limit)
    write_csv(rows)
    text = render(rows)
    OUT_MD.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
