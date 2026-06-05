#!/usr/bin/env python3
"""Compare stale sim-log exposure with authoritative audit-log exposure.

The simulators should gate new entries from audit logs because audit logs are
updated to FINAL. Older sim CSV files can stay at MARK and falsely look open.
This report makes that mismatch visible.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
OUT_CSV = ROOT / "exposure_consistency_report.csv"
OUT_MD = ROOT / "exposure_consistency_report.md"

PAIRS = [
    ("weather_direction_retest", ROOT / "weather_direction_retest_sim.csv", ROOT / "weather_direction_retest_trade_audit.csv"),
    ("weather_wallet_copy", ROOT / "weather_wallet_copy_sim.csv", ROOT / "weather_wallet_trade_audit.csv"),
    ("btc_directional_copy", ROOT / "btc_directional_wallet_copy_sim.csv", ROOT / "btc_directional_trade_audit.csv"),
    ("btc_directional_candidate_copy", ROOT / "btc_directional_candidate_copy_sim.csv", ROOT / "btc_directional_candidate_trade_audit.csv"),
    ("smart_wallet_copy", ROOT / "smart_wallet_copy_sim.csv", ROOT / "smart_wallet_trade_audit.csv"),
    ("smart_direction_retest", ROOT / "smart_direction_retest_sim.csv", ROOT / "smart_direction_retest_trade_audit.csv"),
    ("creamcream_copy", ROOT / "creamcream_copy_sim.csv", ROOT / "creamcream_trade_audit.csv"),
]

FIELDS = [
    "strategy",
    "sim_open_count",
    "sim_open_stake",
    "audit_open_count",
    "audit_open_stake",
    "extra_sim_open_count",
    "extra_sim_open_stake",
    "status",
    "action",
]


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def read_latest(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    latest: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for idx, row in enumerate(csv.DictReader(file)):
            row_id = row.get("id") or row.get("trade_id") or f"{path.name}:{idx}"
            latest[row_id] = row
    return latest


def open_rows(path: Path) -> dict[str, dict[str, str]]:
    return {row_id: row for row_id, row in read_latest(path).items() if row.get("status") in {"OPEN", "MARK"}}


def summarize(strategy: str, sim_path: Path, audit_path: Path) -> dict[str, Any]:
    sim_open = open_rows(sim_path)
    audit_open = open_rows(audit_path)
    extra_ids = set(sim_open) - set(audit_open)
    sim_stake = sum(fnum(row.get("stake")) for row in sim_open.values())
    audit_stake = sum(fnum(row.get("stake")) for row in audit_open.values())
    extra_stake = sum(fnum(sim_open[row_id].get("stake")) for row_id in extra_ids)
    if extra_ids:
        status = "SIM_STALE_OPEN"
        action = "use_audit_for_entry_limits"
    else:
        status = "OK"
        action = "no_action"
    return {
        "strategy": strategy,
        "sim_open_count": len(sim_open),
        "sim_open_stake": sim_stake,
        "audit_open_count": len(audit_open),
        "audit_open_stake": audit_stake,
        "extra_sim_open_count": len(extra_ids),
        "extra_sim_open_stake": extra_stake,
        "status": status,
        "action": action,
    }


def build_rows() -> list[dict[str, Any]]:
    rows = [summarize(strategy, sim_path, audit_path) for strategy, sim_path, audit_path in PAIRS]
    return sorted(rows, key=lambda row: (row["status"] == "OK", -fnum(row["extra_sim_open_stake"])))


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in ("sim_open_stake", "audit_open_stake", "extra_sim_open_stake"):
                out[key] = f"{fnum(out.get(key)):.6f}"
            writer.writerow({field: out.get(field, "") for field in FIELDS})


def render(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Exposure Consistency Report",
        "",
        "Audit logs are authoritative for entry limits because they receive FINAL updates.",
        "",
        "| strategy | sim open | audit open | extra sim open | status | action |",
        "|---|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['strategy']} | {row['sim_open_count']} / {fnum(row['sim_open_stake']):.2f}U | "
            f"{row['audit_open_count']} / {fnum(row['audit_open_stake']):.2f}U | "
            f"{row['extra_sim_open_count']} / {fnum(row['extra_sim_open_stake']):.2f}U | "
            f"{row['status']} | {row['action']} |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--csv", type=Path, default=OUT_CSV)
    parser.add_argument("--md", type=Path, default=OUT_MD)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = build_rows()
    write_csv(rows, args.csv)
    text = render(rows)
    args.md.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
