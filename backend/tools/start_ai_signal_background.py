#!/usr/bin/env python3
"""Start the AI signal simulator as a detached background process."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path.cwd()
STDOUT = ROOT / "ai_signal_console.log"
STDERR = ROOT / "ai_signal_error.log"


def main() -> int:
    existing = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*ai_signal_simulator.py*' } | Select-Object -First 1 -ExpandProperty ProcessId",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if existing.stdout.strip():
        print(f"AI signal simulator is already running. PID: {existing.stdout.strip()}")
        return 0
    command = [
        sys.executable,
        "-u",
        str(ROOT / "ai_signal_simulator.py"),
        "--stake-usdc",
        "10",
        "--bankroll-usdc",
        "1000",
        "--interval",
        "25",
        "--assets",
        "BTC",
        "--durations",
        "15m",
        "--min-confidence",
        "0.65",
        "--min-move-bps",
        "8",
        "--min-expected-edge-bps",
        "40",
        "--max-slippage-bps",
        "150",
        "--max-source-to-ask-gap",
        "0.012",
        "--min-ask-depth-usdc",
        "25",
        "--max-entries-per-market",
        "1",
        "--max-open-positions",
        "100",
        "--max-error-backoff-sec",
        "180",
    ]
    stdout = STDOUT.open("ab")
    stderr = STDERR.open("ab")
    proc = subprocess.Popen(
        command,
        cwd=str(ROOT),
        stdout=stdout,
        stderr=stderr,
        stdin=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
    )
    (ROOT / "ai_signal_simulator.pid").write_text(str(proc.pid), encoding="ascii")
    print(f"AI signal simulator started. PID: {proc.pid}")
    print(f"Console log: {STDOUT}")
    print(f"Error log: {STDERR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
