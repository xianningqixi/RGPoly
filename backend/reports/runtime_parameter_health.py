#!/usr/bin/env python3
"""Validate live simulator command-line parameters against guarded settings."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
OUT_CSV = ROOT / "runtime_parameter_health.csv"
OUT_MD = ROOT / "runtime_parameter_health.md"

FIELDS = [
    "ts",
    "strategy",
    "pid",
    "status",
    "stake_usdc",
    "bankroll_usdc",
    "max_open_positions",
    "min_realized_pnl_buffer_usdc",
    "reason",
]


@dataclass(frozen=True)
class Expected:
    strategy: str
    script: str
    stake_usdc: str
    bankroll_usdc: str
    max_open_positions: str
    min_realized_pnl_buffer_usdc: str


EXPECTED = [
    Expected(
        strategy="weather_high_prob_wallet_copy",
        script="weather_high_prob_wallet_copy_sim.py",
        stake_usdc="10",
        bankroll_usdc="1000",
        max_open_positions="100",
        min_realized_pnl_buffer_usdc="",
    ),
    Expected(
        strategy="btc_directional_live_shadow",
        script="btc_directional_live_shadow_sim.py",
        stake_usdc="30",
        bankroll_usdc="900",
        max_open_positions="30",
        min_realized_pnl_buffer_usdc="",
    ),
    Expected(
        strategy="weather_high_prob_live_shadow",
        script="weather_high_prob_live_shadow_sim.py",
        stake_usdc="30",
        bankroll_usdc="900",
        max_open_positions="30",
        min_realized_pnl_buffer_usdc="",
    ),
    Expected(
        strategy="btc_no_dominant_candidate_copy",
        script="btc_no_dominant_candidate_copy_sim.py",
        stake_usdc="10",
        bankroll_usdc="1000",
        max_open_positions="100",
        min_realized_pnl_buffer_usdc="",
    ),
    Expected(
        strategy="eth_high_quality_directional_copy",
        script="eth_high_quality_directional_copy_sim.py",
        stake_usdc="10",
        bankroll_usdc="1000",
        max_open_positions="100",
        min_realized_pnl_buffer_usdc="",
    ),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def process_rows() -> list[dict[str, str]]:
    command = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -like 'python*' } | "
        "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        raw: Any = json.loads(result.stdout)
        if isinstance(raw, dict):
            raw = [raw]
        return [{"pid": str(row.get("ProcessId") or ""), "command": str(row.get("CommandLine") or "")} for row in raw]
    except Exception:
        return []


def arg_value(command: str, flag: str) -> str:
    parts = command.split()
    for index, part in enumerate(parts):
        if part == flag and index + 1 < len(parts):
            return parts[index + 1].strip('"')
        if part.startswith(flag + "="):
            return part.split("=", 1)[1].strip('"')
    return ""


def build_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    procs = process_rows()
    for expected in EXPECTED:
        matches = [proc for proc in procs if expected.script in proc["command"]]
        if not matches:
            rows.append(
                {
                    "ts": now_iso(),
                    "strategy": expected.strategy,
                    "pid": "",
                    "status": "NOT_RUNNING",
                    "stake_usdc": "",
                    "bankroll_usdc": "",
                    "max_open_positions": "",
                    "min_realized_pnl_buffer_usdc": "",
                    "reason": "expected simulator process not found",
                }
            )
            continue
        for proc in matches:
            command = proc["command"]
            values = {
                "stake_usdc": arg_value(command, "--stake-usdc"),
                "bankroll_usdc": arg_value(command, "--bankroll-usdc"),
                "max_open_positions": arg_value(command, "--max-open-positions"),
                "min_realized_pnl_buffer_usdc": arg_value(command, "--min-realized-pnl-buffer-usdc"),
            }
            issues = []
            for key, expected_value in {
                "stake_usdc": expected.stake_usdc,
                "bankroll_usdc": expected.bankroll_usdc,
                "max_open_positions": expected.max_open_positions,
                "min_realized_pnl_buffer_usdc": expected.min_realized_pnl_buffer_usdc,
            }.items():
                if values[key] != expected_value:
                    issues.append(f"{key}={values[key] or 'missing'} expected {expected_value}")
            rows.append(
                {
                    "ts": now_iso(),
                    "strategy": expected.strategy,
                    "pid": proc["pid"],
                    "status": "OK" if not issues else "PARAM_MISMATCH",
                    **values,
                    "reason": "; ".join(issues) if issues else "guarded runtime parameters match expected settings",
                }
            )
    return rows


def write_csv(rows: list[dict[str, str]], path: Path = OUT_CSV) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in FIELDS} for row in rows)


def render(rows: list[dict[str, str]]) -> str:
    lines = [
        "# Runtime Parameter Health",
        "",
        "Checks whether running simulators match the guarded paper-trading settings.",
        "",
        "| strategy | status | pid | stake | bankroll | max open | profit buffer | reason |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['strategy']} | {row['status']} | {row['pid']} | {row['stake_usdc']} | "
            f"{row['bankroll_usdc']} | {row['max_open_positions']} | "
            f"{row['min_realized_pnl_buffer_usdc']} | {row['reason']} |"
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
