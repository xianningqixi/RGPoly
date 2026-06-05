#!/usr/bin/env python3
"""Report performance after each strategy's latest configuration change.

This separates current-running evidence from old historical experiments. It is
read-only and uses finalized slippage_final_pnl for ROI.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from realized_pnl_report import (
    AUDIT_FILES,
    STRATEGY_KEYS,
    final_pnl_value,
    fnum,
    is_realized,
    latest_rows,
    parse_dt,
    row_time_value,
)


ROOT = Path.cwd()

FIELDS = [
    "strategy",
    "strategy_key",
    "cutoff_ts",
    "label",
    "intended_state",
    "total_since_cutoff",
    "final_since_cutoff",
    "pending_since_cutoff",
    "stake",
    "pnl",
    "roi",
    "wins",
    "losses",
    "oldest_pending_age_hours",
    "status",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def read_runtime() -> dict[str, str]:
    rows = read_csv(ROOT / "runtime_strategy_status.csv")
    runtime = {row.get("strategy", ""): row.get("intended_state", "ACTIVE") for row in rows}
    for row in read_csv(ROOT / "runtime_strategy_overrides.csv"):
        strategy = row.get("strategy") or ""
        intended = row.get("intended_state") or ""
        if strategy and intended:
            runtime[strategy] = intended
    return runtime


def latest_cutoffs() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for row in read_csv(ROOT / "strategy_change_points.csv"):
        key = row.get("strategy") or ""
        cutoff = row.get("cutoff_ts") or ""
        if not key or not cutoff:
            continue
        if key not in out or parse_dt(cutoff) >= parse_dt(out[key].get("cutoff_ts", "")):
            out[key] = row
    return out


def row_time(row: dict[str, str]) -> datetime:
    return parse_dt(row_time_value(row))


def is_final(row: dict[str, str]) -> bool:
    return is_realized(row)


def summarize_strategy(name: str, path: Path, runtime: dict[str, str], cutoffs: dict[str, dict[str, str]]) -> dict[str, Any]:
    strategy_key = STRATEGY_KEYS.get(name, name.lower().replace(" ", "_"))
    cutoff_row = cutoffs.get(strategy_key, {})
    cutoff_ts = cutoff_row.get("cutoff_ts") or "1970-01-01T00:00:00+00:00"
    cutoff = parse_dt(cutoff_ts)
    rows = [row for row in latest_rows(path).values() if row_time(row) >= cutoff]
    final_rows = [row for row in rows if is_final(row)]
    pending_rows = [row for row in rows if not is_final(row)]
    stake = sum(fnum(row.get("stake")) for row in final_rows)
    pnl = sum(final_pnl_value(row) for row in final_rows)
    wins = sum(1 for row in final_rows if final_pnl_value(row) > 0)
    losses = sum(1 for row in final_rows if final_pnl_value(row) < 0)
    pending_times = [row_time(row) for row in pending_rows]
    pending_times = [item for item in pending_times if item != datetime.min]
    oldest_age = 0.0
    if pending_times:
        oldest = min(pending_times)
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        oldest_age = max(0.0, (datetime.now(timezone.utc) - oldest.astimezone(timezone.utc)).total_seconds() / 3600)
    intended = runtime.get(strategy_key, "ACTIVE")
    if intended == "PAUSED":
        status = "PAUSED"
    elif len(rows) == 0:
        status = "NO_NEW_TRADES"
    elif len(final_rows) == 0:
        status = "WAITING_FINAL"
    elif pnl > 0:
        status = "POSITIVE_CURRENT_CONFIG"
    elif pnl < 0:
        status = "NEGATIVE_CURRENT_CONFIG"
    else:
        status = "FLAT_CURRENT_CONFIG"
    return {
        "strategy": name,
        "strategy_key": strategy_key,
        "cutoff_ts": cutoff_ts,
        "label": cutoff_row.get("label") or "",
        "intended_state": intended,
        "total_since_cutoff": len(rows),
        "final_since_cutoff": len(final_rows),
        "pending_since_cutoff": len(pending_rows),
        "stake": stake,
        "pnl": pnl,
        "roi": pnl / stake * 100 if stake else 0.0,
        "wins": wins,
        "losses": losses,
        "oldest_pending_age_hours": oldest_age,
        "status": status,
    }


def build_rows() -> list[dict[str, Any]]:
    runtime = read_runtime()
    cutoffs = latest_cutoffs()
    return [summarize_strategy(name, path, runtime, cutoffs) for name, path in AUDIT_FILES.items()]


def write_csv(rows: list[dict[str, Any]], path: Path = ROOT / "current_config_report.csv") -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in ["stake", "pnl", "roi", "oldest_pending_age_hours"]:
                out[key] = f"{fnum(out.get(key)):.6f}"
            writer.writerow({field: out.get(field, "") for field in FIELDS})


def render(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Current Config Report",
        "",
        "Counts rows after each strategy's latest change point. ROI is final-only slippage_final_pnl.",
        "",
        "| strategy | state | since cutoff | total | final | pending | W/L | pnl | roi | status |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['strategy']} | {row['intended_state']} | {row['cutoff_ts']} | "
            f"{row['total_since_cutoff']} | {row['final_since_cutoff']} | {row['pending_since_cutoff']} | "
            f"{row['wins']}/{row['losses']} | {fnum(row['pnl']):.4f}U | {fnum(row['roi']):.2f}% | {row['status']} |"
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
    (ROOT / "current_config_report.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
