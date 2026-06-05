#!/usr/bin/env python3
"""Continuously refresh BTC directional candidate-wallet discovery.

Simulation-only. This scheduler never places orders. It periodically refreshes
candidate discovery, rotates the observation pool, and regenerates reports so
the running candidate-copy simulator can pick up new wallets from the pool CSV.
"""

from __future__ import annotations

import argparse
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path.cwd()
LOG = ROOT / "btc_candidate_discovery_scheduler.log"
ERROR_LOG = ROOT / "btc_candidate_discovery_scheduler_error.log"
STATUS = ROOT / "btc_candidate_discovery_scheduler_status.txt"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8", newline="") as file:
        file.write(text + "\n")


def write_status(text: str) -> None:
    STATUS.write_text(text + "\n", encoding="utf-8")


def run_step(name: str, command: list[str], timeout: int) -> int:
    append(LOG, f"[{now_iso()}] step start: {name} | {' '.join(command)}")
    try:
        result = subprocess.run(
            command,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        append(ERROR_LOG, f"[{now_iso()}] step timeout: {name} after {timeout}s")
        if exc.stdout:
            append(LOG, str(exc.stdout).rstrip())
        if exc.stderr:
            append(ERROR_LOG, str(exc.stderr).rstrip())
        return 124
    except Exception as exc:
        append(ERROR_LOG, f"[{now_iso()}] step failed: {name}: {exc}")
        return 1

    if result.stdout:
        append(LOG, result.stdout.rstrip())
    if result.stderr:
        append(ERROR_LOG, result.stderr.rstrip())
    append(LOG, f"[{now_iso()}] step done: {name} exit={result.returncode}")
    return result.returncode


def refresh_once(args: argparse.Namespace, scan_no: int) -> int:
    started = now_iso()
    write_status(f"{started} scan={scan_no} status=RUNNING")
    append(LOG, f"=== {started} BTC candidate discovery scan #{scan_no} start ===")

    steps = [
        (
            "discover",
            [
                "python",
                str(ROOT / "btc_directional_wallet_discovery.py"),
                "--once",
                "--public-market-pages",
                str(args.public_market_pages),
                "--max-public-markets",
                str(args.max_public_markets),
                "--trades-per-market",
                str(args.trades_per_market),
                "--enrich-top",
                str(args.enrich_top),
            ],
            args.discovery_timeout,
        ),
        ("audit_backfill", ["python", str(ROOT / "audit_backfill_scheduler.py"), "--once", "--batch-limit", "120"], 180),
        ("terminal_settle", ["python", str(ROOT / "settle_terminal_marks.py")], 60),
        ("rotate", ["python", str(ROOT / "btc_directional_candidate_rotation_report.py"), "--once"], 120),
        ("sampling_health", ["python", str(ROOT / "candidate_sampling_health.py"), "--once"], 60),
        ("apply_pool", ["python", str(ROOT / "apply_btc_candidate_rotation.py"), "--once"], 60),
        ("pool_health", ["python", str(ROOT / "btc_candidate_pool_health.py"), "--once"], 60),
        ("runtime", ["python", str(ROOT / "runtime_strategy_status.py")], 60),
        ("current_config", ["python", str(ROOT / "current_config_report.py"), "--once"], 60),
        ("capital", ["python", str(ROOT / "capital_allocation_report.py"), "--once"], 60),
        ("dashboard", ["python", str(ROOT / "generate_dashboard.py")], 90),
    ]

    failures = 0
    for name, command, timeout in steps:
        code = run_step(name, command, timeout)
        if code != 0:
            failures += 1
            if name in {"discover", "rotate", "apply_pool"}:
                break

    finished = now_iso()
    status = "OK" if failures == 0 else f"ERRORS_{failures}"
    write_status(f"{finished} scan={scan_no} status={status} failures={failures}")
    append(LOG, f"=== {finished} BTC candidate discovery scan #{scan_no} done status={status} ===")
    return failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval-sec", type=int, default=1800)
    parser.add_argument("--public-market-pages", type=int, default=8)
    parser.add_argument("--max-public-markets", type=int, default=40)
    parser.add_argument("--trades-per-market", type=int, default=200)
    parser.add_argument("--enrich-top", type=int, default=60)
    parser.add_argument("--discovery-timeout", type=int, default=240)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    scan_no = 1
    while True:
        refresh_once(args, scan_no)
        if args.once:
            return 0
        scan_no += 1
        time.sleep(max(60, args.interval_sec))


if __name__ == "__main__":
    raise SystemExit(main())
