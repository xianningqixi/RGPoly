#!/usr/bin/env python3
"""Recommend BTC directional candidate-wallet rotation.

This report is read-only. It compares the latest discovered BTC directional
wallet candidates with the current observation simulator results, then writes
add/keep/remove suggestions. It never edits launch scripts and never sends
orders.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path.cwd()
CANDIDATES = ROOT / "btc_directional_wallet_candidates.csv"
AUDIT = ROOT / "btc_directional_candidate_trade_audit.csv"
OUT_CSV = ROOT / "btc_directional_candidate_rotation_report.csv"
OUT_MD = ROOT / "btc_directional_candidate_rotation_report.md"

FIELDS = [
    "ts",
    "alias",
    "wallet",
    "candidate_rank",
    "discovery_recommendation",
    "score",
    "seed_trade_count",
    "seed_markets",
    "observed_volume_usdc",
    "no_buy_count",
    "yes_buy_count",
    "above_count",
    "range_count",
    "reach_dip_count",
    "avg_price",
    "last_seen",
    "last_seen_age_sec",
    "sim_total",
    "sim_final",
    "sim_pending",
    "sim_wins",
    "sim_losses",
    "sim_stake",
    "sim_final_pnl",
    "sim_final_roi",
    "avg_slippage_bps",
    "positive_2m_rate",
    "positive_10m_rate",
    "positive_1h_rate",
    "action",
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


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDS})


def latest_audit_rows(path: Path) -> dict[str, dict[str, str]]:
    rows = read_csv(path)
    latest: dict[str, dict[str, str]] = {}
    for row in rows:
        trade_id = row.get("id") or ""
        if not trade_id:
            continue
        latest[trade_id] = row
    return latest


def pct(numerator: float, denominator: float) -> float:
    return (numerator / denominator * 100.0) if denominator else 0.0


def alias_for_candidate(row: dict[str, str]) -> str:
    alias = row.get("alias") or (row.get("wallet") or "")[:10]
    clean = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in alias).strip("_")
    return f"candidate_{(clean or alias)[:32]}"


def summarize_sim(rows: list[dict[str, str]]) -> dict[str, Any]:
    final_rows = [row for row in rows if row.get("status") in {"FINAL", "RESOLVED"} or row.get("final_result") in {"WIN", "LOSS"}]
    pending_rows = [row for row in rows if row not in final_rows]
    wins = sum(1 for row in final_rows if row.get("final_result") == "WIN")
    losses = sum(1 for row in final_rows if row.get("final_result") == "LOSS")
    stake = sum(fnum(row.get("stake")) for row in final_rows)
    pnl = sum(fnum(row.get("slippage_final_pnl")) for row in final_rows)
    slips = [fnum(row.get("slippage_bps")) for row in rows if row.get("slippage_bps") not in {"", None}]
    mark_2m = [fnum(row.get("slippage_pnl_2m")) for row in rows if row.get("slippage_pnl_2m") not in {"", None}]
    mark_10m = [fnum(row.get("slippage_pnl_10m")) for row in rows if row.get("slippage_pnl_10m") not in {"", None}]
    mark_1h = [fnum(row.get("slippage_pnl_1h")) for row in rows if row.get("slippage_pnl_1h") not in {"", None}]
    return {
        "sim_total": len(rows),
        "sim_final": len(final_rows),
        "sim_pending": len(pending_rows),
        "sim_wins": wins,
        "sim_losses": losses,
        "sim_stake": stake,
        "sim_final_pnl": pnl,
        "sim_final_roi": pct(pnl, stake),
        "avg_slippage_bps": sum(slips) / len(slips) if slips else 0.0,
        "positive_2m_rate": pct(sum(1 for value in mark_2m if value > 0), len(mark_2m)),
        "positive_10m_rate": pct(sum(1 for value in mark_10m if value > 0), len(mark_10m)),
        "positive_1h_rate": pct(sum(1 for value in mark_1h if value > 0), len(mark_1h)),
    }


def action_for(row: dict[str, Any], args: argparse.Namespace) -> tuple[str, str]:
    discovery = str(row.get("discovery_recommendation") or "")
    final_count = inum(row.get("sim_final"))
    pending_count = inum(row.get("sim_pending"))
    total = inum(row.get("sim_total"))
    roi = fnum(row.get("sim_final_roi"))
    avg_slip = fnum(row.get("avg_slippage_bps"))
    rank = inum(row.get("candidate_rank"))
    seed_trade_count = inum(row.get("seed_trade_count"))
    no_count = inum(row.get("no_buy_count"))
    yes_count = inum(row.get("yes_buy_count"))
    no_ratio = no_count / (no_count + yes_count) if (no_count + yes_count) else 0.0
    reach_dip = inum(row.get("reach_dip_count"))
    avg_price = fnum(row.get("avg_price"))
    last_seen_age_sec = fnum(row.get("last_seen_age_sec"))
    mark_2m = fnum(row.get("positive_2m_rate"))
    mark_10m = fnum(row.get("positive_10m_rate"))

    if discovery == "REJECT_FOR_NOW" or reach_dip > 0:
        return "REMOVE_OR_SKIP", "discovery rejected or has reach/dip exposure"
    if total == 0 and no_ratio < args.min_no_ratio_for_new_observation:
        return "WATCHLIST_ONLY", f"No ratio {no_ratio:.2f} below No-only observation gate"
    if total == 0 and last_seen_age_sec > args.max_unsampled_last_seen_age_sec:
        return "WATCHLIST_ONLY", f"candidate has no sample and last signal is stale ({last_seen_age_sec / 3600:.1f}h)"
    if avg_price >= args.max_avg_price:
        return "REMOVE_OR_SKIP", f"average source price too high ({avg_price:.3f})"
    if (
        total == 0
        and discovery in {"OBSERVE_HIGH", "OBSERVE_SMALL"}
        and rank <= args.no_dominant_rotation_pool
        and seed_trade_count >= args.min_seed_trades_no_dominant
        and no_ratio >= args.min_no_ratio_no_dominant
        and reach_dip == 0
    ):
        return "ADD_TO_OBSERVATION", f"No-dominant fresh candidate: No ratio {no_ratio:.2f} with {seed_trade_count} seed trades"
    if final_count >= args.min_final and roi <= args.min_roi:
        return "REMOVE_OR_SKIP", f"final ROI {roi:.2f}% after {final_count} finalized trades"
    if final_count >= args.min_final and avg_slip > args.max_avg_slippage_bps:
        return "REMOVE_OR_SKIP", f"average slippage {avg_slip:.0f}bps is above cap"
    if total >= args.min_mark_sample and final_count < args.min_final and (mark_2m < args.min_positive_mark_rate or mark_10m < args.min_positive_mark_rate):
        return "DOWNWEIGHT_OBSERVATION", f"early mark quality is weak: 2m {mark_2m:.1f}%, 10m {mark_10m:.1f}%"
    if final_count >= args.min_final and roi >= args.promote_roi:
        return "PROMOTE_CANDIDATE", f"final ROI {roi:.2f}% after {final_count} finalized trades"
    if total > 0:
        return "KEEP_OBSERVING", f"{total} simulated trades, {pending_count} pending, waiting for final sample"
    min_seed = args.min_seed_trades_high if discovery == "OBSERVE_HIGH" else args.min_seed_trades
    if discovery in {"OBSERVE_HIGH", "OBSERVE_SMALL"} and rank <= args.rotation_pool and seed_trade_count >= min_seed:
        return "ADD_TO_OBSERVATION", "high-ranked discovered candidate not yet sampled"
    return "WATCHLIST_ONLY", "not sampled and below current rotation priority"


def build_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    candidates = read_csv(args.candidates)
    latest = latest_audit_rows(args.audit)
    by_alias: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in latest.values():
        alias = row.get("wallet_name") or ""
        if alias:
            by_alias[alias].append(row)

    candidate_aliases = {alias_for_candidate(row): row for row in candidates}
    all_aliases = set(candidate_aliases) | set(by_alias)
    rows: list[dict[str, Any]] = []
    ts = now_iso()
    ranked_candidates = {alias_for_candidate(row): index for index, row in enumerate(candidates, start=1)}
    for alias in sorted(all_aliases, key=lambda name: ranked_candidates.get(name, 999999)):
        source = candidate_aliases.get(alias, {})
        sim = summarize_sim(by_alias.get(alias, []))
        last_seen = source.get("last_seen", "")
        last_seen_dt = parse_dt(last_seen)
        last_seen_age_sec = (datetime.now(timezone.utc) - last_seen_dt).total_seconds() if last_seen_dt else 999999999.0
        row: dict[str, Any] = {
            "ts": ts,
            "alias": alias,
            "wallet": source.get("wallet", ""),
            "candidate_rank": ranked_candidates.get(alias, ""),
            "discovery_recommendation": source.get("recommendation", "NOT_IN_DISCOVERY"),
            "score": f"{fnum(source.get('score')):.6f}" if source else "",
            "seed_trade_count": source.get("seed_trade_count", ""),
            "seed_markets": source.get("seed_markets", ""),
            "observed_volume_usdc": source.get("observed_volume_usdc", ""),
            "no_buy_count": source.get("no_buy_count", ""),
            "yes_buy_count": source.get("yes_buy_count", ""),
            "above_count": source.get("above_count", ""),
            "range_count": source.get("range_count", ""),
            "reach_dip_count": source.get("reach_dip_count", ""),
            "avg_price": source.get("avg_price", ""),
            "last_seen": last_seen,
            "last_seen_age_sec": f"{last_seen_age_sec:.2f}",
            **sim,
        }
        action, reason = action_for(row, args)
        row["action"] = action
        row["reason"] = reason
        rows.append(row)
    return rows


def fmt(value: Any, digits: int = 2) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return str(value or "")


def write_md(path: Path, rows: list[dict[str, Any]]) -> None:
    action_order = {
        "PROMOTE_CANDIDATE": 0,
        "KEEP_OBSERVING": 1,
        "ADD_TO_OBSERVATION": 2,
        "DOWNWEIGHT_OBSERVATION": 3,
        "REMOVE_OR_SKIP": 4,
        "WATCHLIST_ONLY": 5,
    }
    ordered = sorted(rows, key=lambda row: (action_order.get(str(row.get("action")), 99), inum(row.get("candidate_rank") or 999999)))
    lines = [
        "# BTC Directional Candidate Rotation Report",
        "",
        "Simulation only. Final ROI uses finalized `slippage_final_pnl`; pending and mark-to-market are diagnostics only.",
        "",
        "| action | alias | rank | rec | last seen age | sim final/pending | final ROI | 2m+ | 10m+ | avg slip | reason |",
        "|---|---|---:|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in ordered[:40]:
        lines.append(
            "| {action} | {alias} | {rank} | {rec} | {last_seen_age}h | {final}/{pending} | {roi}% | {p2}% | {p10}% | {slip}bps | {reason} |".format(
                action=row.get("action", ""),
                alias=row.get("alias", ""),
                rank=row.get("candidate_rank", ""),
                rec=row.get("discovery_recommendation", ""),
                last_seen_age=fmt(fnum(row.get("last_seen_age_sec")) / 3600, 1),
                final=row.get("sim_final", 0),
                pending=row.get("sim_pending", 0),
                roi=fmt(row.get("sim_final_roi"), 2),
                p2=fmt(row.get("positive_2m_rate"), 1),
                p10=fmt(row.get("positive_10m_rate"), 1),
                slip=fmt(row.get("avg_slippage_bps"), 0),
                reason=str(row.get("reason", "")).replace("|", "/"),
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Compatibility flag; report always runs once")
    parser.add_argument("--candidates", type=Path, default=CANDIDATES)
    parser.add_argument("--audit", type=Path, default=AUDIT)
    parser.add_argument("--out-csv", type=Path, default=OUT_CSV)
    parser.add_argument("--out-md", type=Path, default=OUT_MD)
    parser.add_argument("--rotation-pool", type=int, default=30)
    parser.add_argument("--no-dominant-rotation-pool", type=int, default=60)
    parser.add_argument("--min-seed-trades", type=int, default=10)
    parser.add_argument("--min-seed-trades-no-dominant", type=int, default=5)
    parser.add_argument("--min-seed-trades-high", type=int, default=15)
    parser.add_argument("--min-final", type=int, default=20)
    parser.add_argument("--min-roi", type=float, default=0.0)
    parser.add_argument("--promote-roi", type=float, default=3.0)
    parser.add_argument("--max-avg-slippage-bps", type=float, default=250.0)
    parser.add_argument("--max-avg-price", type=float, default=0.82)
    parser.add_argument("--max-unsampled-last-seen-age-sec", type=float, default=6 * 3600)
    parser.add_argument("--min-no-ratio-for-new-observation", type=float, default=0.50)
    parser.add_argument("--min-no-ratio-no-dominant", type=float, default=0.75)
    parser.add_argument("--min-mark-sample", type=int, default=5)
    parser.add_argument("--min-positive-mark-rate", type=float, default=45.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = build_rows(args)
    write_csv(args.out_csv, rows)
    write_md(args.out_md, rows)
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row.get("action"))] += 1
    print("BTC directional candidate rotation report")
    for action in sorted(counts):
        print(f"- {action}: {counts[action]}")
    print(f"Wrote {args.out_csv.name} and {args.out_md.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
