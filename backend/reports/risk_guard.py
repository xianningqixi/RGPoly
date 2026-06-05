#!/usr/bin/env python3
"""Automatically pause losing simulation strategies after current-config evidence.

This is simulation-only. It never sends orders. The guard reads current config
final-only ROI, stops eligible local simulator processes, and writes a runtime
override so future reports treat the strategy as paused.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
CURRENT_CONFIG = ROOT / "current_config_report.csv"
OVERRIDES = ROOT / "runtime_strategy_overrides.csv"
CHANGE_POINTS = ROOT / "strategy_change_points.csv"
LOG = ROOT / "risk_guard_actions.csv"
STATUS = ROOT / "risk_guard_status.csv"

GUARDED = {
    "btc_directional_copy": {
        "stop_script": "stop_btc_directional_wallet_copy.ps1",
        "label_prefix": "btc_directional_auto_paused",
    },
    "btc_directional_candidate_copy": {
        "stop_script": "stop_btc_directional_candidate_copy.ps1",
        "label_prefix": "btc_directional_candidate_auto_paused",
    },
    "smart_direction_retest": {
        "stop_script": "stop_smart_direction_retest.ps1",
        "label_prefix": "smart_direction_retest_auto_paused",
    },
    "weather_wallet_copy": {
        "stop_script": "stop_weather_wallet_copy.ps1",
        "label_prefix": "weather_auto_paused",
    },
    "weather_direction_retest": {
        "stop_script": "stop_weather_direction_retest.ps1",
        "label_prefix": "weather_direction_retest_auto_paused",
        "pause_on_any_loss": True,
    },
    "ai_signal_copy": {
        "stop_script": "stop_ai_signal_simulator.ps1",
        "label_prefix": "ai_signal_auto_paused",
    },
}

OVERRIDE_FIELDS = ["strategy", "intended_state", "note", "updated_at", "source"]
LOG_FIELDS = [
    "ts",
    "mode",
    "strategy",
    "action",
    "reason",
    "final_since_cutoff",
    "wins",
    "losses",
    "stake",
    "pnl",
    "roi",
    "stop_exit_code",
]
STATUS_FIELDS = [
    "ts",
    "mode",
    "strategy",
    "intended_state",
    "total_since_cutoff",
    "final_since_cutoff",
    "pending_since_cutoff",
    "wins",
    "losses",
    "stake",
    "pnl",
    "roi",
    "status",
    "guard_decision",
    "reason",
]


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def inum(value: Any) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def append_csv(path: Path, row: dict[str, Any], fields: list[str]) -> None:
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in fields})


def append_change_point(strategy: str, label: str, note: str) -> None:
    exists = CHANGE_POINTS.exists()
    with CHANGE_POINTS.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["strategy", "label", "cutoff_ts", "notes"])
        if not exists:
            writer.writeheader()
        writer.writerow({"strategy": strategy, "label": label, "cutoff_ts": now_iso(), "notes": note})


def upsert_override(strategy: str, note: str) -> None:
    rows = read_csv(OVERRIDES)
    out = [row for row in rows if row.get("strategy") != strategy]
    out.append(
        {
            "strategy": strategy,
            "intended_state": "PAUSED",
            "note": note,
            "updated_at": now_iso(),
            "source": "risk_guard",
        }
    )
    write_csv(OVERRIDES, out, OVERRIDE_FIELDS)


def stop_strategy(strategy: str) -> int:
    script = GUARDED[strategy]["stop_script"]
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    return result.returncode


def pause_reason(row: dict[str, str], min_final: int, max_negative_roi: float, max_consecutive_losses: int) -> str:
    strategy = row.get("strategy_key") or ""
    final = inum(row.get("final_since_cutoff"))
    roi = fnum(row.get("roi"))
    pnl = fnum(row.get("pnl"))
    losses = inum(row.get("losses"))
    wins = inum(row.get("wins"))

    if GUARDED.get(strategy, {}).get("pause_on_any_loss") and losses > 0:
        return f"{losses} finalized loss detected in guarded positive-only retest"
    if final < min_final:
        return ""
    if pnl < 0 and roi <= max_negative_roi:
        return f"current-config final ROI {roi:.2f}% with PnL {pnl:.4f}U"
    if final >= max_consecutive_losses and losses >= max_consecutive_losses and wins == 0:
        return f"{losses} current-config finalized losses and no wins"
    return ""


def evaluate(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    subprocess.run(["python", str(ROOT / "current_config_report.py"), "--once"], cwd=str(ROOT), check=False)
    rows = read_csv(CURRENT_CONFIG)
    actions: list[dict[str, Any]] = []
    status_rows: list[dict[str, Any]] = []
    for row in rows:
        strategy = row.get("strategy_key") or ""
        if strategy not in GUARDED:
            continue
        reason = ""
        decision = "NO_ACTION"
        if row.get("intended_state") == "PAUSED":
            decision = "ALREADY_PAUSED"
        else:
            reason = pause_reason(row, args.min_final, args.max_negative_roi, args.max_consecutive_losses)
            if reason:
                decision = "PAUSE_TRIGGERED"
            elif inum(row.get("final_since_cutoff")) < args.min_final:
                decision = "WAITING_FINAL_SAMPLE"
            elif inum(row.get("pending_since_cutoff")) > 0:
                decision = "WAITING_PENDING_RESOLUTION"
        status_rows.append(
            {
                "ts": now_iso(),
                "mode": "apply" if args.apply else "dry_run",
                "strategy": strategy,
                "intended_state": row.get("intended_state", ""),
                "total_since_cutoff": row.get("total_since_cutoff", ""),
                "final_since_cutoff": row.get("final_since_cutoff", ""),
                "pending_since_cutoff": row.get("pending_since_cutoff", ""),
                "wins": row.get("wins", ""),
                "losses": row.get("losses", ""),
                "stake": row.get("stake", ""),
                "pnl": row.get("pnl", ""),
                "roi": row.get("roi", ""),
                "status": row.get("status", ""),
                "guard_decision": decision,
                "reason": reason,
            }
        )
        if row.get("intended_state") == "PAUSED":
            continue
        if not reason:
            continue
        action = {
            "ts": now_iso(),
            "mode": "apply" if args.apply else "dry_run",
            "strategy": strategy,
            "action": "pause_new_entries",
            "reason": reason,
            "final_since_cutoff": row.get("final_since_cutoff", ""),
            "wins": row.get("wins", ""),
            "losses": row.get("losses", ""),
            "stake": row.get("stake", ""),
            "pnl": row.get("pnl", ""),
            "roi": row.get("roi", ""),
            "stop_exit_code": "",
        }
        actions.append(action)
    return actions, status_rows


def apply_actions(actions: list[dict[str, Any]], dry_run: bool) -> None:
    for action in actions:
        strategy = str(action["strategy"])
        if dry_run:
            append_csv(LOG, action, LOG_FIELDS)
            continue
        note = f"auto-paused by risk_guard: {action['reason']}"
        stop_exit = stop_strategy(strategy)
        action["stop_exit_code"] = str(stop_exit)
        upsert_override(strategy, note)
        label = f"{GUARDED[strategy]['label_prefix']}_{datetime.now(timezone.utc).strftime('%Y_%m_%d_%H%M%S')}"
        append_change_point(strategy, label, note)
        append_csv(LOG, action, LOG_FIELDS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually stop strategies and write PAUSED overrides")
    parser.add_argument("--min-final", type=int, default=10)
    parser.add_argument("--max-negative-roi", type=float, default=0.0)
    parser.add_argument("--max-consecutive-losses", type=int, default=5)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    actions, status_rows = evaluate(args)
    write_csv(STATUS, status_rows, STATUS_FIELDS)
    apply_actions(actions, dry_run=not args.apply)
    if not actions:
        print("risk_guard: no pause action")
        for row in status_rows:
            print(
                f"risk_guard: {row['strategy']} decision={row['guard_decision']} "
                f"final={row['final_since_cutoff']} pending={row['pending_since_cutoff']} roi={row['roi']}"
            )
        return 0
    for action in actions:
        print(
            f"risk_guard: {action['mode']} {action['strategy']} {action['action']} "
            f"reason={action['reason']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
