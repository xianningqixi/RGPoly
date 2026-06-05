#!/usr/bin/env python3
"""Summarize dashboard auto-refresh health without treating old errors as current."""

from __future__ import annotations

import argparse
import csv
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path.cwd()
LOG = ROOT / "dashboard_auto_refresh.log"
ERROR_LOG = ROOT / "dashboard_auto_refresh_error.log"
OUT_CSV = ROOT / "dashboard_refresh_health.csv"
OUT_MD = ROOT / "dashboard_refresh_health.md"
FIELDS = ["ts", "last_refresh_start", "last_refresh_done", "last_exit_code", "status", "recent_error_lines", "reason"]


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []


def parse_health() -> dict[str, str]:
    lines = read_lines(LOG)
    starts = [line for line in lines if " refresh start ===" in line]
    dones = [line for line in lines if " refresh done exit=" in line]
    last_start = starts[-1] if starts else ""
    last_done = dones[-1] if dones else ""
    exit_code = ""
    match = re.search(r"exit=(\d+)", last_done)
    if match:
        exit_code = match.group(1)

    error_lines = read_lines(ERROR_LOG)
    recent_error_lines = "\n".join(error_lines[-20:])
    if exit_code == "0":
        status = "OK"
        reason = "last dashboard refresh completed successfully"
    elif last_done:
        status = "REFRESH_FAILED"
        reason = f"last dashboard refresh exited {exit_code or 'unknown'}"
    elif last_start:
        status = "NO_DONE_MARKER"
        reason = "refresh start exists but no done marker found"
    else:
        status = "NO_REFRESH_LOG"
        reason = "dashboard auto-refresh log missing or empty"

    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "last_refresh_start": last_start.replace("===", "").strip(),
        "last_refresh_done": last_done.replace("===", "").strip(),
        "last_exit_code": exit_code,
        "status": status,
        "recent_error_lines": recent_error_lines,
        "reason": reason,
    }


def write_csv(row: dict[str, str], path: Path = OUT_CSV) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in FIELDS})


def render(row: dict[str, str]) -> str:
    return "\n".join(
        [
            "# Dashboard Refresh Health",
            "",
            "| status | last exit | last done | reason |",
            "|---|---:|---|---|",
            f"| {row['status']} | {row['last_exit_code']} | {row['last_refresh_done']} | {row['reason']} |",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> int:
    build_parser().parse_args()
    row = parse_health()
    write_csv(row)
    text = render(row)
    OUT_MD.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
