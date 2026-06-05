#!/usr/bin/env python3
"""Audit-data quality report for simulation strategies.

The report focuses on whether realized ROI is based on enough final rows and
whether pending rows are large enough to make current performance incomplete.
It is read-only and does not change strategy behavior.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from realized_pnl_report import (
    AUDIT_FILES as REALIZED_AUDIT_FILES,
    STRATEGY_KEYS,
    is_realized,
    row_time_value,
)


ROOT = Path.cwd()

AUDIT_FILES = {STRATEGY_KEYS[name]: path for name, path in REALIZED_AUDIT_FILES.items()}

FIELDS = [
    "strategy",
    "total_rows",
    "final_rows",
    "pending_rows",
    "final_coverage_pct",
    "pending_stake_usdc",
    "oldest_pending_time",
    "oldest_pending_age_hours",
    "data_quality",
    "recommended_action",
]


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
    full = ROOT / path
    if not full.exists():
        return []
    latest: dict[str, dict[str, str]] = {}
    with full.open("r", encoding="utf-8-sig", newline="") as file:
        for idx, row in enumerate(csv.DictReader(file)):
            row_id = row.get("id") or str(idx)
            latest[row_id] = row
    return list(latest.values())


def is_final(row: dict[str, str]) -> bool:
    return is_realized(row)


def signal_time(row: dict[str, str]) -> datetime | None:
    return parse_dt(row_time_value(row))


def classify(total: int, final: int, pending: int, oldest_age: float) -> tuple[str, str]:
    if total == 0:
        return "NO_DATA", "wait_for_signals"
    coverage = final / total * 100 if total else 0.0
    if pending > 0 and oldest_age >= 24:
        return "STALE_PENDING", "backfill_or_inspect_resolution"
    if final < 30:
        return "LOW_FINAL_SAMPLE", "observe_only_until_30_final_rows"
    if coverage < 50:
        return "LOW_FINAL_COVERAGE", "do_not_raise_stake_until_more_final_rows"
    return "OK", "use_final_rows_only"


def summarize(strategy: str, path: Path) -> dict[str, str]:
    rows = read_rows(path)
    final_rows = [row for row in rows if is_final(row)]
    pending_rows = [row for row in rows if not is_final(row)]
    pending_stake = sum(fnum(row.get("stake")) for row in pending_rows)
    pending_times = [ts for ts in (signal_time(row) for row in pending_rows) if ts]
    oldest = min(pending_times) if pending_times else None
    age_hours = 0.0
    if oldest:
        age_hours = max(0.0, (datetime.now(timezone.utc) - oldest.astimezone(timezone.utc)).total_seconds() / 3600)
    quality, action = classify(len(rows), len(final_rows), len(pending_rows), age_hours)
    coverage = len(final_rows) / len(rows) * 100 if rows else 0.0
    return {
        "strategy": strategy,
        "total_rows": str(len(rows)),
        "final_rows": str(len(final_rows)),
        "pending_rows": str(len(pending_rows)),
        "final_coverage_pct": f"{coverage:.2f}",
        "pending_stake_usdc": f"{pending_stake:.4f}",
        "oldest_pending_time": oldest.isoformat() if oldest else "",
        "oldest_pending_age_hours": f"{age_hours:.2f}",
        "data_quality": quality,
        "recommended_action": action,
    }


def build_rows() -> list[dict[str, str]]:
    return [summarize(strategy, path) for strategy, path in AUDIT_FILES.items()]


def write_csv(rows: list[dict[str, str]], path: Path = ROOT / "data_quality_report.csv") -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def render(rows: list[dict[str, str]]) -> str:
    lines = [
        "# Data Quality Report",
        "",
        "Only final rows can be used for true ROI. Pending rows are exposure/coverage checks only.",
        "",
        "| strategy | total | final | pending | coverage | pending stake | oldest pending age | quality | action |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['strategy']} | {row['total_rows']} | {row['final_rows']} | {row['pending_rows']} | "
            f"{row['final_coverage_pct']}% | {row['pending_stake_usdc']}U | "
            f"{row['oldest_pending_age_hours']}h | {row['data_quality']} | {row['recommended_action']} |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one data-quality pass and exit")
    return parser


def main() -> int:
    build_parser().parse_args()
    rows = build_rows()
    write_csv(rows)
    text = render(rows)
    (ROOT / "data_quality_report.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
