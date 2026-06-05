#!/usr/bin/env python3
"""Report BTC candidate pool health for the paper-trading discovery loop."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
ROTATION = ROOT / "btc_directional_candidate_rotation_report.csv"
POOL = ROOT / "btc_directional_candidate_pool.csv"
OUT_CSV = ROOT / "btc_candidate_pool_health.csv"
OUT_MD = ROOT / "btc_candidate_pool_health.md"

FIELDS = [
    "ts",
    "alias",
    "wallet",
    "in_pool",
    "candidate_rank",
    "discovery_recommendation",
    "rotation_action",
    "health",
    "last_seen",
    "last_seen_age_sec",
    "sim_total",
    "sim_final",
    "sim_pending",
    "sim_final_roi",
    "positive_2m_rate",
    "positive_10m_rate",
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


def health_for(row: dict[str, str], in_pool: bool, max_pending_per_wallet: int) -> str:
    action = row.get("action") or ""
    final = inum(row.get("sim_final"))
    pending = inum(row.get("sim_pending"))
    roi = fnum(row.get("sim_final_roi"))
    if action == "PROMOTE_CANDIDATE":
        return "PROMOTION_READY"
    if final >= 20 and roi <= 0:
        return "FAILED_FINAL_GATE"
    if pending >= max_pending_per_wallet and final < 20:
        return "WAITING_FINAL_OFF_POOL" if not in_pool else "PENDING_HEAVY_IN_POOL"
    if in_pool and pending == 0 and final == 0:
        return "NEW_OBSERVATION"
    if in_pool and pending > 0:
        return "WAITING_FINAL_IN_POOL"
    if action == "ADD_TO_OBSERVATION":
        return "READY_TO_ADD"
    if action == "KEEP_OBSERVING":
        return "KEEP_OBSERVING"
    if action == "REMOVE_OR_SKIP":
        return "SKIPPED"
    return "WATCHLIST"


def build_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    pool_aliases = {row.get("alias", "") for row in read_csv(args.pool)}
    rows = []
    ts = now_iso()
    for row in read_csv(args.rotation):
        alias = row.get("alias", "")
        in_pool = alias in pool_aliases
        health = health_for(row, in_pool, args.max_pending_per_wallet)
        if args.focus_only and health in {"SKIPPED", "WATCHLIST"}:
            continue
        rows.append(
            {
                "ts": ts,
                "alias": alias,
                "wallet": row.get("wallet", ""),
                "in_pool": "YES" if in_pool else "NO",
                "candidate_rank": row.get("candidate_rank", ""),
                "discovery_recommendation": row.get("discovery_recommendation", ""),
                "rotation_action": row.get("action", ""),
                "health": health,
                "last_seen": row.get("last_seen", ""),
                "last_seen_age_sec": row.get("last_seen_age_sec", ""),
                "sim_total": row.get("sim_total", ""),
                "sim_final": row.get("sim_final", ""),
                "sim_pending": row.get("sim_pending", ""),
                "sim_final_roi": row.get("sim_final_roi", ""),
                "positive_2m_rate": row.get("positive_2m_rate", ""),
                "positive_10m_rate": row.get("positive_10m_rate", ""),
                "reason": row.get("reason", ""),
            }
        )
    order = {
        "PROMOTION_READY": 0,
        "NEW_OBSERVATION": 1,
        "WAITING_FINAL_IN_POOL": 2,
        "READY_TO_ADD": 3,
        "WAITING_FINAL_OFF_POOL": 4,
        "PENDING_HEAVY_IN_POOL": 5,
        "KEEP_OBSERVING": 6,
        "FAILED_FINAL_GATE": 7,
        "SKIPPED": 8,
        "WATCHLIST": 9,
    }
    rows.sort(key=lambda item: (order.get(str(item["health"]), 99), inum(item.get("candidate_rank") or 999999)))
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in FIELDS} for row in rows)


def write_md(path: Path, rows: list[dict[str, Any]]) -> None:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row.get("health"))] += 1
    lines = [
        "# BTC Candidate Pool Health",
        "",
        "Simulation only. Final ROI uses finalized `slippage_final_pnl`; pending and mark data are diagnostics.",
        "",
        "## Counts",
        "",
    ]
    for key in sorted(counts):
        lines.append(f"- {key}: {counts[key]}")
    lines.extend(
        [
            "",
            "## Candidates",
            "",
            "| health | in pool | alias | rank | rec | last seen age | final/pending | final ROI | 2m+ | 10m+ | reason |",
            "|---|---|---|---:|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in rows[:40]:
        lines.append(
            "| {health} | {in_pool} | {alias} | {rank} | {rec} | {last_seen_age:.1f}h | {final}/{pending} | {roi:.2f}% | {p2:.1f}% | {p10:.1f}% | {reason} |".format(
                health=row.get("health", ""),
                in_pool=row.get("in_pool", ""),
                alias=row.get("alias", ""),
                rank=row.get("candidate_rank", ""),
                rec=row.get("discovery_recommendation", ""),
                last_seen_age=fnum(row.get("last_seen_age_sec")) / 3600,
                final=row.get("sim_final", ""),
                pending=row.get("sim_pending", ""),
                roi=fnum(row.get("sim_final_roi")),
                p2=fnum(row.get("positive_2m_rate")),
                p10=fnum(row.get("positive_10m_rate")),
                reason=str(row.get("reason", "")).replace("|", "/"),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--rotation", type=Path, default=ROTATION)
    parser.add_argument("--pool", type=Path, default=POOL)
    parser.add_argument("--out-csv", type=Path, default=OUT_CSV)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    parser.add_argument("--max-pending-per-wallet", type=int, default=3)
    parser.add_argument("--focus-only", action=argparse.BooleanOptionalAction, default=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = build_rows(args)
    write_csv(args.out_csv, rows)
    write_md(args.out_md, rows)
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row["health"])] += 1
    print("BTC candidate pool health")
    for key in sorted(counts):
        print(f"- {key}: {counts[key]}")
    print(f"Wrote {args.out_csv.name} and {args.out_md.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
