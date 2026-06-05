#!/usr/bin/env python3
"""Score market directions across all simulation strategies.

This report is direction-level, not wallet-level. It uses finalized
slippage-adjusted PnL only, then recommends where the simulation should focus
next. Pending and scanner-only directions are shown as observation candidates,
not as profit.
"""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CSV_OUT = ROOT / "market_direction_report.csv"
MD_OUT = ROOT / "market_direction_report.md"

AUDIT_FILES = {
    "creamcream_copy": ROOT / "creamcream_trade_audit.csv",
    "smart_wallet_copy": ROOT / "smart_wallet_trade_audit.csv",
    "btc_signal": ROOT / "btc_signal_trades.csv",
    "btc_directional_copy": ROOT / "btc_directional_trade_audit.csv",
    "btc_directional_candidate_copy": ROOT / "btc_directional_candidate_trade_audit.csv",
    "smart_direction_retest": ROOT / "smart_direction_retest_trade_audit.csv",
    "weather_direction_retest": ROOT / "weather_direction_retest_trade_audit.csv",
    "weather_wallet_copy": ROOT / "weather_wallet_trade_audit.csv",
    "ai_signal_copy": ROOT / "ai_signal_trade_audit.csv",
}

FIELDS = [
    "direction",
    "strategy",
    "market_type",
    "outcome",
    "price_bucket",
    "final",
    "pending",
    "wins",
    "losses",
    "stake",
    "pnl",
    "roi",
    "avg_slippage_bps",
    "max_loss",
    "action",
    "reason",
]


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def read_latest(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    latest: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for index, row in enumerate(csv.DictReader(file)):
            key = row.get("id") or row.get("trade_id") or f"row-{index}"
            latest[key] = row
    return list(latest.values())


def final_result(row: dict[str, str]) -> str:
    result = row.get("final_result") or ""
    if result in {"WIN", "LOSS"}:
        return result
    if row.get("status") == "RESOLVED" and row.get("result") in {"WIN", "LOSS"}:
        return row.get("result") or ""
    return ""


def final_pnl(row: dict[str, str]) -> float:
    if row.get("slippage_final_pnl") not in {"", None}:
        return fnum(row.get("slippage_final_pnl"))
    if row.get("status") == "RESOLVED" and row.get("pnl") not in {"", None}:
        return fnum(row.get("pnl"))
    return 0.0


def is_final(row: dict[str, str]) -> bool:
    if final_result(row) not in {"WIN", "LOSS"}:
        return False
    if row.get("slippage_final_pnl") not in {"", None}:
        return True
    return row.get("status") == "RESOLVED" and row.get("pnl") not in {"", None}


def text_of(row: dict[str, str]) -> str:
    return " ".join(
        str(row.get(key) or "")
        for key in ("title", "question", "slug", "event_slug", "eventSlug", "market_slug")
    ).lower()


def market_type(strategy: str, row: dict[str, str]) -> str:
    text = text_of(row)
    if strategy == "ai_signal_copy":
        asset = str(row.get("asset") or "").upper()
        duration = row.get("duration") or ("15m" if "15m" in text else "5m" if "5m" in text else "short")
        return f"ai_{asset}_{duration}".lower()
    if "highest temperature" in text or "lowest temperature" in text or "weather" in text:
        return "weather_temperature"
    if "up or down" in text or "updown" in text:
        if "eth" in text or str(row.get("asset") or "").upper() == "ETH":
            return "crypto_short_eth"
        return "crypto_short_btc"
    if "bitcoin" in text or "btc" in text:
        if "reach" in text or "dip" in text:
            return "btc_reach_or_dip"
        if "between" in text:
            return "btc_range"
        if "above" in text or "below" in text:
            return "btc_above_below"
        return "btc_directional_other"
    return strategy


def outcome_value(row: dict[str, str]) -> str:
    return row.get("outcome") or row.get("direction") or row.get("side") or "unknown"


def price_value(row: dict[str, str]) -> float:
    for key in ("source_price", "sim_fill_price", "entry_price", "price", "best_ask"):
        if row.get(key) not in {"", None}:
            value = fnum(row.get(key))
            if value > 0:
                return value
    return 0.0


def price_bucket(row: dict[str, str]) -> str:
    price = price_value(row)
    if price <= 0:
        return "unknown"
    low = math.floor(price * 10) / 10
    return f"{low:.1f}-{low + 0.1:.1f}"


def direction_key(strategy: str, row: dict[str, str]) -> tuple[str, str, str, str]:
    mtype = market_type(strategy, row)
    outcome = outcome_value(row)
    bucket = price_bucket(row)
    direction = f"{mtype}:{outcome}:{bucket}"
    return direction, mtype, outcome, bucket


def summarize_direction(
    direction: str,
    strategy: str,
    mtype: str,
    outcome: str,
    bucket: str,
    item: dict[str, Any],
    strategy_summary: dict[str, dict[str, float]],
) -> dict[str, Any]:
    stake = fnum(item["stake"])
    pnl = fnum(item["pnl"])
    final = int(item["final"])
    pending = int(item["pending"])
    roi = pnl / stake * 100 if stake else 0.0
    slips = item.get("slippages") or []
    avg_slip = sum(slips) / len(slips) if slips else 0.0
    max_loss = min(item.get("pnls") or [0.0])
    s = strategy_summary.get(strategy, {})
    strategy_roi = fnum(s.get("roi"))
    strategy_pnl = fnum(s.get("pnl"))
    action, reason = recommend(final, pending, pnl, roi, max_loss, mtype, outcome, bucket, strategy_roi, strategy_pnl)
    return {
        "direction": direction,
        "strategy": strategy,
        "market_type": mtype,
        "outcome": outcome,
        "price_bucket": bucket,
        "final": final,
        "pending": pending,
        "wins": int(item["wins"]),
        "losses": int(item["losses"]),
        "stake": stake,
        "pnl": pnl,
        "roi": roi,
        "avg_slippage_bps": avg_slip,
        "max_loss": max_loss,
        "action": action,
        "reason": reason,
    }


def recommend(
    final: int,
    pending: int,
    pnl: float,
    roi: float,
    max_loss: float,
    market_type_name: str,
    outcome: str,
    bucket: str,
    strategy_roi: float,
    strategy_pnl: float,
) -> tuple[str, str]:
    if final == 0 and pending > 0:
        return "OBSERVE_PENDING", "pending only; do not count as realized profit"
    if final == 0:
        return "NO_FINAL_SAMPLE", "no finalized evidence yet"
    if strategy_pnl < 0 and pnl > 0:
        return "RETEST_TINY", "profitable sub-bucket, but parent strategy is negative overall"
    if market_type_name == "weather_temperature" and pnl < 0:
        return "STOP_OR_TINY_OBSERVE", "weather direction has negative realized edge"
    if "reach_or_dip" in market_type_name:
        return "BLOCK", "BTC reach/dip bucket is negative historically"
    if final >= 20 and pnl > 0 and roi >= 3 and max_loss >= -5:
        return "PRIMARY_CANDIDATE", "positive final ROI with enough sample and controlled loss"
    if final >= 5 and pnl > 0 and roi >= 3:
        return "OBSERVE_TO_PROMOTE", "positive final ROI but sample is still small"
    if final >= 10 and (pnl <= 0 or roi <= 0):
        return "STOP", "negative or flat realized ROI after enough sample"
    if pnl < 0:
        return "DOWNWEIGHT", "negative realized PnL; keep only tiny observation if needed"
    if bucket in {"0.8-0.9", "0.9-1.0"} and pnl <= 0:
        return "BLOCK_HIGH_PRICE", "high-price bucket has poor payoff after slippage"
    return "OBSERVE", "insufficient final sample for promotion"


def build_rows() -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str, str], dict[str, Any]] = defaultdict(
        lambda: {"final": 0, "pending": 0, "wins": 0, "losses": 0, "stake": 0.0, "pnl": 0.0, "pnls": [], "slippages": []}
    )
    strategy_totals: dict[str, dict[str, float]] = defaultdict(lambda: {"stake": 0.0, "pnl": 0.0, "final": 0.0})
    for strategy, path in AUDIT_FILES.items():
        for row in read_latest(path):
            direction, mtype, outcome, bucket = direction_key(strategy, row)
            item = grouped[(direction, strategy, mtype, outcome, bucket)]
            if is_final(row):
                pnl = final_pnl(row)
                strategy_totals[strategy]["final"] += 1
                strategy_totals[strategy]["stake"] += fnum(row.get("stake"))
                strategy_totals[strategy]["pnl"] += pnl
                item["final"] += 1
                item["wins"] += 1 if pnl > 0 else 0
                item["losses"] += 1 if pnl <= 0 else 0
                item["stake"] += fnum(row.get("stake"))
                item["pnl"] += pnl
                item["pnls"].append(pnl)
                if row.get("slippage_bps") not in {"", None}:
                    item["slippages"].append(fnum(row.get("slippage_bps")))
            else:
                item["pending"] += 1
    strategy_summary: dict[str, dict[str, float]] = {}
    for strategy, totals in strategy_totals.items():
        stake = fnum(totals.get("stake"))
        pnl = fnum(totals.get("pnl"))
        strategy_summary[strategy] = {
            "stake": stake,
            "pnl": pnl,
            "roi": pnl / stake * 100 if stake else 0.0,
            "final": fnum(totals.get("final")),
        }
    rows = [
        summarize_direction(direction, strategy, mtype, outcome, bucket, item, strategy_summary)
        for (direction, strategy, mtype, outcome, bucket), item in grouped.items()
    ]
    return sorted(rows, key=lambda row: (action_rank(str(row["action"])), -int(row["final"]), -float(row["pnl"])))


def action_rank(action: str) -> int:
    return {
        "PRIMARY_CANDIDATE": 0,
        "OBSERVE_TO_PROMOTE": 1,
        "RETEST_TINY": 2,
        "OBSERVE_PENDING": 3,
        "OBSERVE": 4,
        "NO_FINAL_SAMPLE": 5,
        "DOWNWEIGHT": 6,
        "STOP_OR_TINY_OBSERVE": 7,
        "STOP": 8,
        "BLOCK_HIGH_PRICE": 9,
        "BLOCK": 10,
    }.get(action, 99)


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in ("stake", "pnl", "roi", "avg_slippage_bps", "max_loss"):
                out[key] = f"{fnum(out.get(key)):.6f}"
            writer.writerow({field: out.get(field, "") for field in FIELDS})


def write_md(rows: list[dict[str, Any]], path: Path) -> None:
    lines = [
        "# Market Direction Report",
        "",
        "Simulation only. Realized PnL uses finalized `slippage_final_pnl`; pending rows are not profit.",
        "",
        "| action | direction | strategy | final/pending | W/L | stake | pnl | ROI | reason |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows[:80]:
        lines.append(
            "| {action} | {direction} | {strategy} | {final}/{pending} | {wins}/{losses} | {stake:.2f}U | {pnl:.4f}U | {roi:.2f}% | {reason} |".format(
                action=row["action"],
                direction=str(row["direction"]).replace("|", "/"),
                strategy=row["strategy"],
                final=int(row["final"]),
                pending=int(row["pending"]),
                wins=int(row["wins"]),
                losses=int(row["losses"]),
                stake=fnum(row["stake"]),
                pnl=fnum(row["pnl"]),
                roi=fnum(row["roi"]),
                reason=str(row["reason"]).replace("|", "/"),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--csv", type=Path, default=CSV_OUT)
    parser.add_argument("--md", type=Path, default=MD_OUT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = build_rows()
    write_csv(rows, args.csv)
    write_md(rows, args.md)
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row["action"])] += 1
    print("Market direction report")
    for action in sorted(counts, key=action_rank):
        print(f"- {action}: {counts[action]}")
    print(f"Wrote {args.csv.name} and {args.md.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
