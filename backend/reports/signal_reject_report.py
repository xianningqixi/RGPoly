#!/usr/bin/env python3
"""Summarize rejected live signals for active simulations."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path.cwd()

REJECT_FILES = {
    "btc_directional_copy": ROOT / "btc_directional_rejects.csv",
    "btc_directional_candidate_copy": ROOT / "btc_directional_candidate_rejects.csv",
    "weather_direction_retest": ROOT / "weather_direction_retest_rejects.csv",
    "weather_wallet_copy": ROOT / "weather_wallet_rejects.csv",
}
CHANGE_POINTS = ROOT / "strategy_change_points.csv"

FIELDS = ["strategy", "window_hours", "reason", "count", "avg_signal_age_sec", "avg_slippage_bps", "avg_source_to_ask_gap"]


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def latest_strategy_cutoff(strategy: str) -> datetime | None:
    rows = read_rows(CHANGE_POINTS)
    latest: datetime | None = None
    for row in rows:
        if row.get("strategy") != strategy:
            continue
        dt = parse_dt(row.get("cutoff_ts"))
        if dt and (latest is None or dt > latest):
            latest = dt
    return latest


def summarize(window_hours: float, since_current_config: bool) -> list[dict[str, Any]]:
    window_cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    out: list[dict[str, Any]] = []
    for strategy, path in REJECT_FILES.items():
        cutoff = window_cutoff
        if since_current_config:
            current_cutoff = latest_strategy_cutoff(strategy)
            if current_cutoff and current_cutoff > cutoff:
                cutoff = current_cutoff
        rows = [row for row in read_rows(path) if (parse_dt(row.get("ts")) or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff]
        unique_rows: dict[str, dict[str, str]] = {}
        for idx, row in enumerate(rows):
            row_id = row.get("id") or f"row:{idx}"
            unique_rows[row_id] = row
        rows = list(unique_rows.values())
        grouped: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            grouped.setdefault(row.get("reason") or "unknown", []).append(row)
        for reason, items in grouped.items():
            n = len(items) or 1
            out.append(
                {
                    "strategy": strategy,
                    "window_hours": window_hours,
                    "since_current_config": since_current_config,
                    "reason": reason,
                    "count": len(items),
                    "avg_signal_age_sec": sum(fnum(row.get("signal_age_sec")) for row in items) / n,
                    "avg_slippage_bps": sum(fnum(row.get("slippage_bps")) for row in items) / n,
                    "avg_source_to_ask_gap": sum(fnum(row.get("source_to_ask_gap")) for row in items) / n,
                }
            )
    return sorted(out, key=lambda row: (str(row["strategy"]), -int(row["count"])))


def write_csv(rows: list[dict[str, Any]], path: Path = ROOT / "signal_reject_report.csv") -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in ["window_hours", "avg_signal_age_sec", "avg_slippage_bps", "avg_source_to_ask_gap"]:
                out[key] = f"{fnum(out.get(key)):.6f}"
            writer.writerow({field: out.get(field, "") for field in FIELDS})


def render(rows: list[dict[str, Any]]) -> str:
    scope = "current active config" if rows and rows[0].get("since_current_config") else "recent window"
    lines = [
        "# Signal Reject Report",
        "",
        f"Rejected fresh signals, grouped by reason. Scope: {scope}.",
        "",
        "| strategy | reason | count | avg age | avg slip | avg gap |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['strategy']} | {row['reason']} | {row['count']} | "
            f"{fnum(row['avg_signal_age_sec']):.1f}s | {fnum(row['avg_slippage_bps']):.0f}bps | "
            f"{fnum(row['avg_source_to_ask_gap']):.4f} |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-hours", type=float, default=24)
    parser.add_argument("--since-current-config", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = summarize(args.window_hours, args.since_current_config)
    write_csv(rows)
    text = render(rows)
    (ROOT / "signal_reject_report.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
