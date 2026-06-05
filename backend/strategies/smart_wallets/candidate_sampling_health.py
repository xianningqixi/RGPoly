#!/usr/bin/env python3
"""Report whether the BTC candidate pool is producing usable No-only samples."""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
POOL = ROOT / "btc_directional_candidate_pool.csv"
REJECTS = ROOT / "btc_directional_candidate_rejects.csv"
AUDIT = ROOT / "btc_directional_candidate_trade_audit.csv"
CHANGE_POINTS = ROOT / "strategy_change_points.csv"
OUT_CSV = ROOT / "candidate_sampling_health.csv"
OUT_MD = ROOT / "candidate_sampling_health.md"

FIELDS = [
    "ts",
    "alias",
    "wallet",
    "candidate_rank",
    "last_seen_age_hours",
    "opens_since_cutoff",
    "final_since_cutoff",
    "pending_since_cutoff",
    "rejects_since_cutoff",
    "yes_rejects_since_cutoff",
    "bad_market_rejects_since_cutoff",
    "old_rejects_since_cutoff",
    "fresh_no_rejects_since_cutoff",
    "health",
    "recommended_action",
    "reason",
]


def parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def latest_cutoff(strategy: str) -> datetime:
    latest = datetime.min.replace(tzinfo=timezone.utc)
    for row in read_csv(CHANGE_POINTS):
        if row.get("strategy") != strategy:
            continue
        ts = parse_dt(row.get("cutoff_ts"))
        if ts and ts > latest:
            latest = ts
    return latest


def build_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    cutoff = latest_cutoff("btc_directional_candidate_copy")
    pool = read_csv(args.pool)
    reject_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in read_csv(args.rejects):
        ts = parse_dt(row.get("ts"))
        if not ts or ts < cutoff:
            continue
        alias = row.get("wallet_name") or ""
        reason = row.get("reason") or "UNKNOWN"
        reject_counts[alias][reason] += 1
        if row.get("outcome") == "Yes":
            reject_counts[alias]["__YES__"] += 1
        if reason == "blocked_market_type":
            reject_counts[alias]["__BAD_MARKET__"] += 1
        if row.get("outcome") == "No" and reason not in {"outcome_not_allowed", "source_too_old"}:
            reject_counts[alias]["__FRESH_NO_REJECT__"] += 1

    audit_latest: dict[str, dict[str, str]] = {}
    for row in read_csv(args.audit):
        trade_id = row.get("id") or ""
        if trade_id:
            audit_latest[trade_id] = row

    audit_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in audit_latest.values():
        ts = parse_dt(row.get("detected_time") or row.get("audit_ts"))
        if not ts or ts < cutoff:
            continue
        alias = row.get("wallet_name") or ""
        audit_counts[alias]["opens"] += 1
        if row.get("final_result") in {"WIN", "LOSS"}:
            audit_counts[alias]["final"] += 1
        else:
            audit_counts[alias]["pending"] += 1

    now = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    for pool_row in pool:
        alias = pool_row.get("alias") or ""
        last_seen_age_hours = fnum(pool_row.get("last_seen_age_sec")) / 3600
        rejects = reject_counts[alias]
        audits = audit_counts[alias]
        reject_total = sum(count for key, count in rejects.items() if not key.startswith("__"))
        yes_rejects = rejects["__YES__"]
        bad_market_rejects = rejects["__BAD_MARKET__"]
        old_rejects = rejects["source_too_old"]
        fresh_no_rejects = rejects["__FRESH_NO_REJECT__"]
        opens = audits["opens"]
        final = audits["final"]
        pending = audits["pending"]

        if opens:
            health = "SAMPLING"
            action = "keep_current_slot"
            reason = f"{opens} candidate No-only samples opened since latest change point"
        elif last_seen_age_hours > args.stale_hours:
            health = "STALE_SLOT"
            action = "rotate_if_no_new_signal_next_cycle"
            reason = f"no sample and latest source signal is {last_seen_age_hours:.1f}h old"
        elif yes_rejects >= args.yes_reject_warning and yes_rejects >= max(1, reject_total * 0.6):
            health = "YES_HEAVY_LIVE_FLOW"
            action = "watch_but_do_not_relax_yes"
            reason = f"{yes_rejects}/{reject_total} recent rejects are Yes; keep No-only until final evidence changes"
        elif bad_market_rejects >= args.bad_market_reject_warning and bad_market_rejects >= max(1, reject_total * 0.5):
            health = "BAD_MARKET_LIVE_FLOW"
            action = "rotate_out_if_pool_has_replacement"
            reason = f"{bad_market_rejects}/{reject_total} recent rejects are blocked reach/dip markets"
        elif fresh_no_rejects:
            health = "FRESH_NO_BLOCKED"
            action = "inspect_price_depth_filter"
            reason = f"{fresh_no_rejects} fresh No signals were blocked by non-outcome filters"
        else:
            health = "WAITING_FRESH_NO"
            action = "keep_observing"
            reason = "no fresh qualifying No signal yet"

        rows.append(
            {
                "ts": now,
                "alias": alias,
                "wallet": pool_row.get("wallet", ""),
                "candidate_rank": pool_row.get("candidate_rank", ""),
                "last_seen_age_hours": f"{last_seen_age_hours:.2f}",
                "opens_since_cutoff": opens,
                "final_since_cutoff": final,
                "pending_since_cutoff": pending,
                "rejects_since_cutoff": reject_total,
                "yes_rejects_since_cutoff": yes_rejects,
                "bad_market_rejects_since_cutoff": bad_market_rejects,
                "old_rejects_since_cutoff": old_rejects,
                "fresh_no_rejects_since_cutoff": fresh_no_rejects,
                "health": health,
                "recommended_action": action,
                "reason": reason,
            }
        )
    order = {
        "SAMPLING": 0,
        "FRESH_NO_BLOCKED": 1,
        "WAITING_FRESH_NO": 2,
        "BAD_MARKET_LIVE_FLOW": 3,
        "YES_HEAVY_LIVE_FLOW": 4,
        "STALE_SLOT": 5,
    }
    rows.sort(key=lambda row: (order.get(str(row.get("health")), 99), fnum(row.get("last_seen_age_hours"))))
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in FIELDS} for row in rows)


def write_md(path: Path, rows: list[dict[str, Any]]) -> None:
    counts = Counter(str(row.get("health")) for row in rows)
    lines = [
        "# Candidate Sampling Health",
        "",
        "Simulation only. This report checks whether the current No-only BTC candidate pool is producing testable samples.",
        "",
        "## Counts",
        "",
    ]
    for key in sorted(counts):
        lines.append(f"- {key}: {counts[key]}")
    lines.extend(
        [
            "",
            "## Pool",
            "",
            "| health | alias | rank | last seen | opens/final/pending | rejects | yes | bad market | action | reason |",
            "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    for row in rows:
        lines.append(
            "| {health} | {alias} | {rank} | {age}h | {opens}/{final}/{pending} | {rejects} | {yes} | {bad} | {action} | {reason} |".format(
                health=row.get("health", ""),
                alias=row.get("alias", ""),
                rank=row.get("candidate_rank", ""),
                age=row.get("last_seen_age_hours", ""),
                opens=row.get("opens_since_cutoff", 0),
                final=row.get("final_since_cutoff", 0),
                pending=row.get("pending_since_cutoff", 0),
                rejects=row.get("rejects_since_cutoff", 0),
                yes=row.get("yes_rejects_since_cutoff", 0),
                bad=row.get("bad_market_rejects_since_cutoff", 0),
                action=row.get("recommended_action", ""),
                reason=str(row.get("reason", "")).replace("|", "/"),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--pool", type=Path, default=POOL)
    parser.add_argument("--rejects", type=Path, default=REJECTS)
    parser.add_argument("--audit", type=Path, default=AUDIT)
    parser.add_argument("--out-csv", type=Path, default=OUT_CSV)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    parser.add_argument("--stale-hours", type=float, default=6.0)
    parser.add_argument("--yes-reject-warning", type=int, default=3)
    parser.add_argument("--bad-market-reject-warning", type=int, default=5)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = build_rows(args)
    write_csv(args.out_csv, rows)
    write_md(args.out_md, rows)
    counts = Counter(str(row.get("health")) for row in rows)
    print("Candidate sampling health")
    for key in sorted(counts):
        print(f"- {key}: {counts[key]}")
    print(f"Wrote {args.out_csv.name} and {args.out_md.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
