#!/usr/bin/env python3
"""Bucket realized BTC directional copy performance.

Only finalized rows are counted. PnL uses slippage_final_pnl.
This report is advisory and does not edit running strategy parameters.
"""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable


ROOT = Path.cwd()
AUDIT = ROOT / "btc_directional_trade_audit.csv"
CSV_OUT = ROOT / "btc_directional_bucket_report.csv"
MD_OUT = ROOT / "btc_directional_bucket_report.md"
FIELDS = ["bucket_type", "bucket", "final", "wins", "losses", "stake", "pnl", "roi", "action"]


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
        for row in csv.DictReader(file):
            key = row.get("id") or row.get("trade_id") or ""
            if key:
                latest[key] = row
    return list(latest.values())


def price_bucket(row: dict[str, str]) -> str:
    price = fnum(row.get("source_price"))
    low = math.floor(price * 10) / 10
    return f"{low:.1f}-{low + 0.1:.1f}"


def market_type(row: dict[str, str]) -> str:
    slug = row.get("slug", "")
    if "reach" in slug or "dip" in slug:
        return "reach_or_dip"
    if "between" in slug:
        return "range"
    if "above" in slug:
        return "above"
    return "other"


def action(final: int, roi: float, pnl: float) -> str:
    if final < 5:
        return "OBSERVE"
    if pnl > 0 and roi > 3:
        return "ALLOW"
    if pnl < 0 or roi <= 0:
        return "BLOCK_OR_DOWNWEIGHT"
    return "OBSERVE"


def summarize(rows: list[dict[str, str]], bucket_type: str, key_fn: Callable[[dict[str, str]], Any]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"final": 0, "wins": 0, "losses": 0, "stake": 0.0, "pnl": 0.0})
    for row in rows:
        if row.get("final_result") not in {"WIN", "LOSS"}:
            continue
        key = str(key_fn(row))
        pnl = fnum(row.get("slippage_final_pnl"))
        item = grouped[key]
        item["final"] += 1
        item["wins"] += 1 if pnl > 0 else 0
        item["losses"] += 1 if pnl <= 0 else 0
        item["stake"] += fnum(row.get("stake"))
        item["pnl"] += pnl
    out: list[dict[str, Any]] = []
    for key, item in grouped.items():
        roi = item["pnl"] / item["stake"] * 100 if item["stake"] else 0.0
        out.append(
            {
                "bucket_type": bucket_type,
                "bucket": key,
                "final": item["final"],
                "wins": item["wins"],
                "losses": item["losses"],
                "stake": item["stake"],
                "pnl": item["pnl"],
                "roi": roi,
                "action": action(item["final"], roi, item["pnl"]),
            }
        )
    return sorted(out, key=lambda row: (row["bucket_type"], row["bucket"]))


def build_rows() -> list[dict[str, Any]]:
    rows = read_latest(AUDIT)
    out: list[dict[str, Any]] = []
    out.extend(summarize(rows, "outcome", lambda row: row.get("outcome", "")))
    out.extend(summarize(rows, "market_type", market_type))
    out.extend(summarize(rows, "source_price_bucket", price_bucket))
    out.extend(summarize(rows, "outcome_price_bucket", lambda row: f"{row.get('outcome','')}:{price_bucket(row)}"))
    return out


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["stake"] = f"{fnum(out.get('stake')):.4f}"
            out["pnl"] = f"{fnum(out.get('pnl')):.4f}"
            out["roi"] = f"{fnum(out.get('roi')):.4f}"
            writer.writerow({field: out.get(field, "") for field in FIELDS})


def render(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# BTC Directional Bucket Report",
        "",
        "Only finalized rows are counted. PnL uses slippage_final_pnl.",
        "",
        "| bucket type | bucket | final | W/L | stake | pnl | ROI | action |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['bucket_type']} | {row['bucket']} | {int(row['final'])} | "
            f"{int(row['wins'])}/{int(row['losses'])} | {fnum(row['stake']):.2f}U | "
            f"{fnum(row['pnl']):.4f}U | {fnum(row['roi']):.2f}% | {row['action']} |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, default=CSV_OUT)
    parser.add_argument("--md", type=Path, default=MD_OUT)
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = build_rows()
    write_csv(rows, args.csv)
    text = render(rows)
    args.md.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
