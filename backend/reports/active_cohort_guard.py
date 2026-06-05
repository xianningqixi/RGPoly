#!/usr/bin/env python3
"""Apply guardrails from active_cohort_health_report.

Simulation-only. This never sends orders. It only stops local simulator
processes and writes runtime overrides when current active-cohort evidence says
the strategy should pause or tighten.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
HEALTH = ROOT / "active_cohort_health_report.csv"
OVERRIDES = ROOT / "runtime_strategy_overrides.csv"
CHANGE_POINTS = ROOT / "strategy_change_points.csv"
STATUS = ROOT / "active_cohort_guard_status.csv"
ACTIONS = ROOT / "active_cohort_guard_actions.csv"

STOP_SCRIPTS = {
    "btc_directional_copy": "stop_btc_directional_wallet_copy.ps1",
    "btc_directional_candidate_copy": "stop_btc_directional_candidate_copy.ps1",
    "weather_direction_retest": "stop_weather_direction_retest.ps1",
    "weather_wallet_copy": "stop_weather_wallet_copy.ps1",
    "ai_signal_copy": "stop_ai_signal_simulator.ps1",
    "smart_direction_retest": "stop_smart_direction_retest.ps1",
    "smart_wallet_copy": "stop_smart_wallet_copy.ps1",
    "creamcream_copy": "stop_creamcream_copy.ps1",
}

OVERRIDE_FIELDS = ["strategy", "intended_state", "note", "updated_at", "source"]
STATUS_FIELDS = [
    "ts",
    "mode",
    "strategy",
    "health_action",
    "guard_decision",
    "final",
    "pending",
    "realized_pnl",
    "realized_roi",
    "mark_pnl",
    "reason",
]
ACTION_FIELDS = STATUS_FIELDS + ["stop_exit_code"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def append_csv(path: Path, row: dict[str, Any], fields: list[str]) -> None:
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in fields})


def upsert_override(strategy: str, note: str) -> None:
    rows = [row for row in read_csv(OVERRIDES) if row.get("strategy") != strategy]
    rows.append(
        {
            "strategy": strategy,
            "intended_state": "PAUSED",
            "note": note,
            "updated_at": now_iso(),
            "source": "active_cohort_guard",
        }
    )
    write_csv(OVERRIDES, rows, OVERRIDE_FIELDS)


def append_change_point(strategy: str, note: str) -> None:
    exists = CHANGE_POINTS.exists()
    with CHANGE_POINTS.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["strategy", "label", "cutoff_ts", "notes"])
        if not exists:
            writer.writeheader()
        label = f"{strategy}_active_cohort_guard_{datetime.now(timezone.utc).strftime('%Y_%m_%d_%H%M%S')}"
        writer.writerow({"strategy": strategy, "label": label, "cutoff_ts": now_iso(), "notes": note})


def stop_strategy(strategy: str) -> int:
    script = STOP_SCRIPTS.get(strategy)
    if not script:
        return -1
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


def decision_for(row: dict[str, str], args: argparse.Namespace) -> tuple[str, str]:
    action = row.get("action") or ""
    final = inum(row.get("final"))
    pending = inum(row.get("pending"))
    realized_pnl = fnum(row.get("realized_pnl"))
    realized_roi = fnum(row.get("realized_roi"))
    mark_pnl = fnum(row.get("mark_pnl"))
    strategy = row.get("strategy") or ""

    if action in {"PAUSE_OR_TIGHTEN"}:
        return "PAUSE_TRIGGERED", row.get("reason") or "health report requested pause/tighten"
    if final >= args.min_final_to_pause and realized_pnl < 0:
        return "PAUSE_TRIGGERED", f"finalized cohort negative: {realized_pnl:.4f}U / {realized_roi:.2f}%"
    if mark_pnl <= -args.max_mark_drawdown and pending >= args.min_pending_for_mark_pause:
        return "PAUSE_TRIGGERED", f"pending mark drawdown {mark_pnl:.4f}U exceeds guard"
    if action == "HOLD_NEW_ENTRIES":
        return "HOLD_NEW_ENTRIES", row.get("reason") or "holding new entries"
    if strategy not in STOP_SCRIPTS:
        return "REPORT_ONLY", "no stop script configured"
    return "NO_ACTION", row.get("reason") or ""


def build_rows(args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    subprocess.run(["python", str(ROOT / "current_config_report.py"), "--once"], cwd=str(ROOT), check=False)
    subprocess.run(["python", str(ROOT / "active_cohort_health_report.py"), "--once"], cwd=str(ROOT), check=False)
    health_rows = read_csv(HEALTH)
    status_rows: list[dict[str, Any]] = []
    action_rows: list[dict[str, Any]] = []
    for row in health_rows:
        decision, reason = decision_for(row, args)
        base = {
            "ts": now_iso(),
            "mode": "apply" if args.apply else "dry_run",
            "strategy": row.get("strategy") or "",
            "health_action": row.get("action") or "",
            "guard_decision": decision,
            "final": row.get("final") or "",
            "pending": row.get("pending") or "",
            "realized_pnl": row.get("realized_pnl") or "",
            "realized_roi": row.get("realized_roi") or "",
            "mark_pnl": row.get("mark_pnl") or "",
            "reason": reason,
        }
        status_rows.append(base)
        if decision == "PAUSE_TRIGGERED":
            action_rows.append(dict(base))
    return status_rows, action_rows


def apply_actions(rows: list[dict[str, Any]], apply: bool) -> None:
    for row in rows:
        if not apply:
            append_csv(ACTIONS, {**row, "stop_exit_code": ""}, ACTION_FIELDS)
            continue
        strategy = str(row.get("strategy") or "")
        note = f"auto-paused by active_cohort_guard: {row.get('reason')}"
        stop_exit = stop_strategy(strategy)
        upsert_override(strategy, note)
        append_change_point(strategy, note)
        append_csv(ACTIONS, {**row, "stop_exit_code": str(stop_exit)}, ACTION_FIELDS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--min-final-to-pause", type=int, default=1)
    parser.add_argument("--max-mark-drawdown", type=float, default=25.0)
    parser.add_argument("--min-pending-for-mark-pause", type=int, default=10)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    status_rows, action_rows = build_rows(args)
    write_csv(STATUS, status_rows, STATUS_FIELDS)
    apply_actions(action_rows, args.apply)
    for row in status_rows:
        print(f"{row['strategy']}: {row['guard_decision']} - {row['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
