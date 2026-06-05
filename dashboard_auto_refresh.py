#!/usr/bin/env python3
"""Refresh dashboard reports every 10 minutes."""

from __future__ import annotations

import subprocess
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LOG = ROOT / "dashboard_auto_refresh.log"
ERROR_LOG = ROOT / "dashboard_auto_refresh_error.log"


def write(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8", newline="") as file:
        file.write(text + "\n")


def refresh_once() -> int:
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write(LOG, f"=== {started} refresh start ===")
    result = subprocess.run(
        ["python", str(ROOT / "generate_dashboard.py"), "--refresh"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.stdout:
        write(LOG, result.stdout.rstrip())
    if result.stderr:
        write(ERROR_LOG, result.stderr.rstrip())
    finished = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write(LOG, f"=== {finished} refresh done exit={result.returncode} ===")
    return result.returncode


def main() -> int:
    while True:
        refresh_once()
        time.sleep(600)


if __name__ == "__main__":
    raise SystemExit(main())
