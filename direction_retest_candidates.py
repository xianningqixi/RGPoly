#!/usr/bin/env python3
"""Find wallet+direction buckets worth isolated paper retesting.

This is report-only. It uses finalized slippage_final_pnl and separates
wallet-level sub-directions from losing parent strategies.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import Any

from market_direction_report import (
    AUDIT_FILES,
    direction_key,
    final_pnl,
    fnum,
    is_final,
    read_latest,
)
from realized_pnl_report import wallet_value


ROOT = Path(__file__).resolve().parent
OUT_CSV = ROOT / "direction_retest_candidates.csv"
OUT_MD = ROOT / "direction_retest_candidates.md"

FIELDS = [
    "action",
    "strategy",
    "wallet",
    "market_type",
    "outcome",
    "price_bucket",
    "final",
    "wins",
    "losses",
    "win_rate",
    "stake",
    "pnl",
    "roi",
    "max_loss",
    "max_drawdown",
    "max_consecutive_losses",
    "suggested_stake_usdc",
    "suggested_filters",
    "reason",
]


def equity_stats(pnls: list[float]) -> tuple[float, int]:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    max_consec = 0
    consec = 0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
        if pnl < 0:
            consec += 1
            max_consec = max(max_consec, consec)
        else:
            consec = 0
    return max_dd, max_consec


def action_for(row: dict[str, Any]) -> tuple[str, str, float]:
    final = int(row["final"])
    pnl = fnum(row["pnl"])
    roi = fnum(row["roi"])
    win_rate = fnum(row["win_rate"])
    max_loss = fnum(row["max_loss"])
    max_dd = fnum(row["max_drawdown"])
    max_consec = int(row["max_consecutive_losses"])
    market_type = str(row["market_type"])
    price_bucket = str(row["price_bucket"])

    if final < 10:
        return "WATCHLIST_ONLY", "sample below 10 finalized trades", 0.0
    if pnl <= 0 or roi <= 0:
        return "BLOCK", "negative or flat final-only sub-direction", 0.0
    if "reach_or_dip" in market_type:
        return "BLOCK", "reach/dip markets remain blocked", 0.0
    if max_consec >= 4:
        return "WATCHLIST_ONLY", f"positive PnL but loss streak is high ({max_consec})", 0.0
    if max_dd > max(2.0, pnl * 1.2):
        return "WATCHLIST_ONLY", f"positive PnL but drawdown {max_dd:.2f}U is too large versus pnl {pnl:.2f}U", 0.0
    if max_loss < -10:
        return "WATCHLIST_ONLY", f"single loss {max_loss:.2f}U is too large for stable curve retest", 0.0
    if final >= 30 and roi >= 3 and (win_rate >= 60 or roi >= 15):
        stake = 0.25 if market_type.startswith("crypto_short") else 0.5
        return "READY_TINY_RETEST", "wallet+direction has enough positive finalized evidence for tiny isolated simulation", stake
    if final >= 10 and roi >= 3:
        return "OBSERVE_ONLY", "positive but not enough stable finalized sample", 0.0
    return "WATCHLIST_ONLY", "edge too small for a new retest", 0.0


def suggested_filters(row: dict[str, Any]) -> str:
    market_type = str(row["market_type"])
    outcome = str(row["outcome"])
    bucket = str(row["price_bucket"])
    if market_type.startswith("crypto_short"):
        asset = "BTC" if "btc" in market_type else "ETH" if "eth" in market_type else ""
        return f"asset={asset}; outcome={outcome}; price_bucket={bucket}; max_age=6s; max_slip=120bps"
    if market_type == "weather_temperature":
        return f"outcome={outcome}; price_bucket={bucket}; max_age=60s; max_slip=150bps; max_gap=0.010"
    if market_type.startswith("btc_"):
        return f"outcome={outcome}; price_bucket={bucket}; block=reach,dip; max_age=90s"
    return f"outcome={outcome}; price_bucket={bucket}"


def build_rows() -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str, str], dict[str, Any]] = defaultdict(
        lambda: {"final": 0, "wins": 0, "losses": 0, "stake": 0.0, "pnl": 0.0, "pnls": []}
    )
    for strategy, path in AUDIT_FILES.items():
        for row in read_latest(path):
            if not is_final(row):
                continue
            _, market_type, outcome, bucket = direction_key(strategy, row)
            wallet = wallet_value(row)
            item = grouped[(strategy, wallet, market_type, outcome, bucket)]
            pnl = final_pnl(row)
            item["final"] += 1
            item["wins"] += 1 if pnl > 0 else 0
            item["losses"] += 1 if pnl < 0 else 0
            item["stake"] += fnum(row.get("stake"))
            item["pnl"] += pnl
            item["pnls"].append(pnl)

    rows: list[dict[str, Any]] = []
    for (strategy, wallet, market_type, outcome, bucket), item in grouped.items():
        final = int(item["final"])
        stake = fnum(item["stake"])
        pnl = fnum(item["pnl"])
        pnls = list(item["pnls"])
        max_dd, max_consec = equity_stats(pnls)
        row: dict[str, Any] = {
            "strategy": strategy,
            "wallet": wallet,
            "market_type": market_type,
            "outcome": outcome,
            "price_bucket": bucket,
            "final": final,
            "wins": int(item["wins"]),
            "losses": int(item["losses"]),
            "win_rate": (int(item["wins"]) / final * 100.0) if final else 0.0,
            "stake": stake,
            "pnl": pnl,
            "roi": pnl / stake * 100.0 if stake else 0.0,
            "max_loss": min(pnls) if pnls else 0.0,
            "max_drawdown": max_dd,
            "max_consecutive_losses": max_consec,
        }
        action, reason, stake_usdc = action_for(row)
        row["action"] = action
        row["reason"] = reason
        row["suggested_stake_usdc"] = stake_usdc
        row["suggested_filters"] = suggested_filters(row)
        rows.append(row)
    order = {"READY_TINY_RETEST": 0, "OBSERVE_ONLY": 1, "WATCHLIST_ONLY": 2, "BLOCK": 3}
    return sorted(rows, key=lambda row: (order.get(str(row["action"]), 99), -fnum(row["pnl"]), -int(row["final"])))


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in ("win_rate", "stake", "pnl", "roi", "max_loss", "max_drawdown", "suggested_stake_usdc"):
                out[key] = f"{fnum(out.get(key)):.6f}"
            writer.writerow({field: out.get(field, "") for field in FIELDS})


def write_md(rows: list[dict[str, Any]], path: Path) -> None:
    lines = [
        "# Direction Retest Candidates",
        "",
        "Simulation only. Candidates are wallet+direction buckets scored with finalized slippage_final_pnl.",
        "",
        "| action | strategy | wallet | direction | final | W/L | ROI | PnL | maxDD | streak | stake | filters | reason |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows[:80]:
        direction = f"{row['market_type']}:{row['outcome']}:{row['price_bucket']}"
        lines.append(
            "| {action} | {strategy} | {wallet} | {direction} | {final} | {wins}/{losses} | {roi:.2f}% | {pnl:.4f}U | {dd:.2f}U | {streak} | {stake:.2f}U | {filters} | {reason} |".format(
                action=row["action"],
                strategy=row["strategy"],
                wallet=str(row["wallet"]).replace("|", "/"),
                direction=direction.replace("|", "/"),
                final=int(row["final"]),
                wins=int(row["wins"]),
                losses=int(row["losses"]),
                roi=fnum(row["roi"]),
                pnl=fnum(row["pnl"]),
                dd=fnum(row["max_drawdown"]),
                streak=int(row["max_consecutive_losses"]),
                stake=fnum(row["suggested_stake_usdc"]),
                filters=str(row["suggested_filters"]).replace("|", "/"),
                reason=str(row["reason"]).replace("|", "/"),
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
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row["action"])] += 1
    print("Direction retest candidates")
    for key in ["READY_TINY_RETEST", "OBSERVE_ONLY", "WATCHLIST_ONLY", "BLOCK"]:
        if counts.get(key):
            print(f"- {key}: {counts[key]}")
    print(f"Wrote {args.csv.name} and {args.md.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
