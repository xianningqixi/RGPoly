#!/usr/bin/env python3
"""Summarize BTC candidate shadow observations."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
INPUT = ROOT / "btc_candidate_shadow_observer.csv"
OUT_CSV = ROOT / "btc_candidate_shadow_report.csv"
OUT_MD = ROOT / "btc_candidate_shadow_report.md"
FIELDS = ["scope", "wallet", "total", "take", "reject", "top_reason", "take_rate", "avg_slippage_bps", "avg_depth_usdc", "action"]


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def summarize_group(scope: str, wallet: str, rows: list[dict[str, str]]) -> dict[str, Any]:
    total = len(rows)
    take_rows = [row for row in rows if row.get("reason") == "TAKE"]
    reject = total - len(take_rows)
    reasons = Counter(row.get("reason") or "UNKNOWN" for row in rows)
    top_reason = reasons.most_common(1)[0][0] if reasons else ""
    avg_slip = sum(fnum(row.get("slippage_bps")) for row in take_rows) / len(take_rows) if take_rows else 0.0
    avg_depth = sum(fnum(row.get("ask_depth_usdc")) for row in take_rows) / len(take_rows) if take_rows else 0.0
    take_rate = len(take_rows) / total * 100 if total else 0.0
    if len(take_rows) >= 5 and take_rate >= 10 and avg_slip <= 200:
        action = "PROMOTE_TO_1U_OBSERVE"
    elif len(take_rows) > 0:
        action = "KEEP_SHADOW"
    else:
        action = "NO_ACTION"
    return {
        "scope": scope,
        "wallet": wallet,
        "total": total,
        "take": len(take_rows),
        "reject": reject,
        "top_reason": top_reason,
        "take_rate": take_rate,
        "avg_slippage_bps": avg_slip,
        "avg_depth_usdc": avg_depth,
        "action": action,
    }


def build_rows() -> list[dict[str, Any]]:
    rows = read_rows(INPUT)
    out = [summarize_group("all", "ALL", rows)]
    by_wallet: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_wallet[row.get("wallet") or "UNKNOWN"].append(row)
    wallet_rows = [summarize_group("wallet", wallet, group) for wallet, group in by_wallet.items()]
    wallet_rows.sort(key=lambda row: (-int(row["take"]), -float(row["take_rate"]), -int(row["total"])))
    out.extend(wallet_rows[:20])
    return out


def write_csv(rows: list[dict[str, Any]], path: Path = OUT_CSV) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in ("take_rate", "avg_slippage_bps", "avg_depth_usdc"):
                out[key] = f"{fnum(out.get(key)):.6f}"
            writer.writerow({field: out.get(field, "") for field in FIELDS})


def render(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# BTC Candidate Shadow Report",
        "",
        "Shadow only. No paper trades are opened and no rows enter realized ROI.",
        "",
        "| scope | wallet | total | TAKE | reject | top reason | TAKE rate | avg slip | action |",
        "|---|---|---:|---:|---:|---|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['scope']} | {row['wallet']} | {int(row['total'])} | {int(row['take'])} | "
            f"{int(row['reject'])} | {row['top_reason']} | {fnum(row['take_rate']):.2f}% | "
            f"{fnum(row['avg_slippage_bps']):.1f} | {row['action']} |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> int:
    build_parser().parse_args()
    rows = build_rows()
    write_csv(rows)
    text = render(rows)
    OUT_MD.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
