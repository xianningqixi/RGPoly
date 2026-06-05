#!/usr/bin/env python3
"""Apply BTC directional candidate rotation to the simulation observation pool.

This script only writes a local wallet-pool CSV for the paper-trading candidate
simulator. It does not place orders, does not edit private keys, and does not
promote candidates to the main BTC directional strategy.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
ROTATION_REPORT = ROOT / "btc_directional_candidate_rotation_report.csv"
SAMPLING_HEALTH = ROOT / "candidate_sampling_health.csv"
REJECTS = ROOT / "btc_directional_candidate_rejects.csv"
AUDIT = ROOT / "btc_directional_candidate_trade_audit.csv"
CHANGE_POINTS = ROOT / "strategy_change_points.csv"
POOL = ROOT / "btc_directional_candidate_pool.csv"
POOL_MD = ROOT / "btc_directional_candidate_pool.md"

POOL_FIELDS = [
    "updated_at",
    "alias",
    "wallet",
    "action",
    "candidate_rank",
    "discovery_recommendation",
    "score",
    "last_seen",
    "last_seen_age_sec",
    "sim_final",
    "sim_pending",
    "sim_final_roi",
    "positive_2m_rate",
    "positive_10m_rate",
    "no_buy_count",
    "yes_buy_count",
    "avg_price",
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


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=POOL_FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in POOL_FIELDS} for row in rows)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def latest_cutoff(strategy: str) -> datetime:
    latest = datetime.min.replace(tzinfo=timezone.utc)
    for row in read_csv(CHANGE_POINTS):
        if row.get("strategy") != strategy:
            continue
        ts = parse_dt(row.get("cutoff_ts"))
        if ts and ts > latest:
            latest = ts
    return latest


def eligible(row: dict[str, str], args: argparse.Namespace) -> bool:
    action = row.get("action") or ""
    if action not in {"PROMOTE_CANDIDATE", "KEEP_OBSERVING", "ADD_TO_OBSERVATION"}:
        return False
    if not row.get("wallet"):
        return False
    if row.get("discovery_recommendation") == "REJECT_FOR_NOW":
        return False
    if fnum(row.get("sim_final_roi")) < args.min_final_roi and inum(row.get("sim_final")) >= args.min_final_gate:
        return False
    if (
        inum(row.get("sim_final")) < args.min_final_gate
        and inum(row.get("sim_pending")) >= args.max_pending_per_wallet
        and action != "PROMOTE_CANDIDATE"
    ):
        return False
    return True


def excluded_by_sampling_health(path: Path) -> set[str]:
    excluded: set[str] = set()
    for row in read_csv(path):
        if row.get("health") not in {"YES_HEAVY_LIVE_FLOW", "BAD_MARKET_LIVE_FLOW"}:
            continue
        if inum(row.get("opens_since_cutoff")) > 0:
            continue
        alias = row.get("alias") or ""
        if alias:
            excluded.add(alias)
    return excluded


def excluded_by_recent_rejects() -> set[str]:
    now = datetime.now(timezone.utc)
    cutoff = min(latest_cutoff("btc_directional_candidate_copy"), now - timedelta(hours=2))
    rejects: dict[str, Counter[str]] = defaultdict(Counter)
    for row in read_csv(REJECTS):
        ts = parse_dt(row.get("ts"))
        if not ts or ts < cutoff:
            continue
        alias = row.get("wallet_name") or ""
        if not alias:
            continue
        rejects[alias]["total"] += 1
        if row.get("outcome") == "Yes":
            rejects[alias]["yes"] += 1
        if row.get("reason") == "blocked_market_type":
            rejects[alias]["bad_market"] += 1
        if row.get("reason") in {"source_price_out_of_range", "source_size_too_small"}:
            rejects[alias]["bad_source"] += 1

    opened: set[str] = set()
    latest_audit: dict[str, dict[str, str]] = {}
    for row in read_csv(AUDIT):
        trade_id = row.get("id") or ""
        if trade_id:
            latest_audit[trade_id] = row
    for row in latest_audit.values():
        ts = parse_dt(row.get("detected_time") or row.get("audit_ts"))
        if ts and ts >= cutoff and row.get("wallet_name"):
            opened.add(row.get("wallet_name") or "")

    excluded: set[str] = set()
    for alias, counts in rejects.items():
        if alias in opened:
            continue
        total = counts["total"]
        yes = counts["yes"]
        bad_market = counts["bad_market"]
        bad_source = counts["bad_source"]
        if yes >= 3 and yes >= max(1, total * 0.60):
            excluded.add(alias)
        elif bad_market >= 5 and bad_market >= max(1, total * 0.50):
            excluded.add(alias)
        elif bad_source >= 8:
            excluded.add(alias)
    return excluded


def action_priority(action: str) -> int:
    return {
        "PROMOTE_CANDIDATE": 0,
        "KEEP_OBSERVING": 1,
        "ADD_TO_OBSERVATION": 2,
    }.get(action, 99)


def candidate_priority(row: dict[str, str]) -> tuple[int, int, float, float, float, int, int, int]:
    action = row.get("action", "")
    final = inum(row.get("sim_final"))
    pending = inum(row.get("sim_pending"))
    p2 = fnum(row.get("positive_2m_rate"))
    p10 = fnum(row.get("positive_10m_rate"))
    rank = inum(row.get("candidate_rank") or 999999)
    last_seen_age_sec = fnum(row.get("last_seen_age_sec") or 999999999)
    no_count = inum(row.get("no_buy_count"))
    yes_count = inum(row.get("yes_buy_count"))
    no_ratio = no_count / (no_count + yes_count) if (no_count + yes_count) else 0.0
    sampled = 0 if final or pending else 1
    early_quality = (p2 + p10) / 2.0 if (p2 or p10) else 0.0
    # Lower tuple sorts first: promoted first, sampled candidates before fresh unsampled slots,
    # recent source activity, stronger No-dominance, better early quality, fewer pending,
    # better discovery rank.
    return (action_priority(action), sampled, last_seen_age_sec, -no_ratio, -early_quality, pending, -final, rank)


def build_pool(args: argparse.Namespace) -> list[dict[str, Any]]:
    report = read_csv(args.rotation_report)
    excluded_aliases = excluded_by_sampling_health(args.sampling_health) | excluded_by_recent_rejects()
    all_candidates = [row for row in report if eligible(row, args)]
    candidates = [row for row in all_candidates if row.get("alias") not in excluded_aliases]
    candidates.sort(key=candidate_priority)
    out: list[dict[str, Any]] = []
    seen_wallets: set[str] = set()
    ts = now_iso()
    for row in candidates:
        wallet = (row.get("wallet") or "").lower()
        if wallet in seen_wallets:
            continue
        seen_wallets.add(wallet)
        out.append(
            {
                "updated_at": ts,
                "alias": row.get("alias", ""),
                "wallet": wallet,
                "action": row.get("action", ""),
                "candidate_rank": row.get("candidate_rank", ""),
                "discovery_recommendation": row.get("discovery_recommendation", ""),
                "score": row.get("score", ""),
                "last_seen": row.get("last_seen", ""),
                "last_seen_age_sec": row.get("last_seen_age_sec", ""),
                "sim_final": row.get("sim_final", ""),
                "sim_pending": row.get("sim_pending", ""),
                "sim_final_roi": row.get("sim_final_roi", ""),
                "positive_2m_rate": row.get("positive_2m_rate", ""),
                "positive_10m_rate": row.get("positive_10m_rate", ""),
                "no_buy_count": row.get("no_buy_count", ""),
                "yes_buy_count": row.get("yes_buy_count", ""),
                "avg_price": row.get("avg_price", ""),
                "reason": row.get("reason", ""),
            }
        )
        if len(out) >= args.max_wallets:
            break
    return out


def write_md(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# BTC Directional Candidate Pool",
        "",
        "Simulation observation pool only. This file is consumed by the candidate paper-trading simulator.",
        "",
        "| alias | wallet | action | rank | last seen age | final/pending | ROI | 2m+ | 10m+ | reason |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {alias} | {wallet} | {action} | {rank} | {last_seen_age:.1f}h | {final}/{pending} | {roi:.2f}% | {p2:.1f}% | {p10:.1f}% | {reason} |".format(
                alias=row.get("alias", ""),
                wallet=row.get("wallet", ""),
                action=row.get("action", ""),
                rank=row.get("candidate_rank", ""),
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
    parser.add_argument("--once", action="store_true", help="Compatibility flag; script always runs once")
    parser.add_argument("--rotation-report", type=Path, default=ROTATION_REPORT)
    parser.add_argument("--sampling-health", type=Path, default=SAMPLING_HEALTH)
    parser.add_argument("--out-csv", type=Path, default=POOL)
    parser.add_argument("--out-md", type=Path, default=POOL_MD)
    parser.add_argument("--max-wallets", type=int, default=12)
    parser.add_argument("--min-wallets", type=int, default=10)
    parser.add_argument("--min-final-gate", type=int, default=20)
    parser.add_argument("--min-final-roi", type=float, default=0.0)
    parser.add_argument("--max-pending-per-wallet", type=int, default=3)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = build_pool(args)
    write_csv(args.out_csv, rows)
    write_md(args.out_md, rows)
    print(f"Applied BTC candidate simulation pool: {len(rows)} wallets")
    for row in rows:
        print(f"- {row['alias']} ({row['action']}, rank {row['candidate_rank']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
