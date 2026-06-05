#!/usr/bin/env python3
"""AI-approved crypto lead-lag simulation bot.

This script never places live orders. It generates candidate signals, asks the
AI decision engine for TAKE/SKIP, records every decision, and only appends
simulated TAKE trades to ai_signal_trade_audit.csv.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_decision_engine import append_decision, decide, decision_row
from crypto_lead_lag_signal import build_candidates, event_for_slug, write_candidates
from portfolio_risk import portfolio_open_exposure
from trade_audit import ensure_audit_open, latest_audit_rows, update_audit_marks


TRADE_FIELDS = [
    "ts",
    "id",
    "candidate_id",
    "asset",
    "slug",
    "question",
    "direction",
    "stake",
    "estimated_q",
    "best_bid",
    "best_ask",
    "sim_fill_price",
    "sim_shares",
    "would_live_fill",
    "slippage_bps",
    "source_to_ask_gap",
    "expected_edge_bps",
    "ai_confidence",
    "ai_reason",
    "ai_risk_flags",
    "status",
    "url",
]

HEALTH_FIELDS = [
    "ts",
    "scan",
    "candidates",
    "take",
    "skip",
    "opened",
    "errors",
    "failure_streak",
    "next_sleep_sec",
]


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_trade(path: Path, row: dict[str, Any]) -> None:
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=TRADE_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in TRADE_FIELDS})


def write_health(path: Path, row: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=HEALTH_FIELDS)
        writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in HEALTH_FIELDS})


def read_seen_decisions(path: Path) -> set[str]:
    if not path.exists():
        return set()
    seen: set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            cid = row.get("candidate_id")
            if cid:
                seen.add(cid)
    return seen


def event_market(slug: str) -> dict[str, Any] | None:
    event = event_for_slug(slug)
    if not event:
        return None
    markets = event.get("markets") or []
    return markets[0] if markets else None


def market_loader(slug: str) -> dict[str, Any] | None:
    try:
        return event_market(slug)
    except Exception:
        return None


def existing_entries(audit_path: Path, slug: str, outcome: str) -> int:
    rows = latest_audit_rows(audit_path)
    count = 0
    for row in rows.values():
        if row.get("slug") == slug and row.get("outcome") == outcome:
            count += 1
    return count


def open_exposure(audit_path: Path) -> tuple[int, float]:
    rows = latest_audit_rows(audit_path)
    count = 0
    stake = 0.0
    for row in rows.values():
        if row.get("status") not in {"OPEN", "MARK"}:
            continue
        count += 1
        stake += fnum(row.get("stake"))
    return count, stake


def simulate_take(args: argparse.Namespace, candidate: dict[str, Any], decision: dict[str, Any]) -> bool:
    slug = str(candidate.get("slug") or "")
    outcome = str(candidate.get("direction") or "")
    if existing_entries(args.audit_log, slug, outcome) >= args.max_entries_per_market:
        return False
    open_count, open_stake = open_exposure(args.audit_log)
    portfolio_count, portfolio_stake = portfolio_open_exposure()
    if (
        open_stake >= args.bankroll_usdc
        or portfolio_stake >= args.bankroll_usdc
        or open_count >= args.max_open_positions
    ):
        return False
    market = event_market(slug)
    if not market:
        return False
    stake = min(
        args.stake_usdc,
        fnum(decision.get("stake_usdc")) or args.stake_usdc,
        max(0.0, args.bankroll_usdc - portfolio_stake),
        max(0.0, args.bankroll_usdc - open_stake),
    )
    if stake <= 0:
        return False
    trade_id = str(candidate.get("candidate_id") or f"{slug}:{outcome}:{int(time.time())}")
    ensure_audit_open(
        args.audit_log,
        trade_id=trade_id,
        strategy="ai_signal",
        wallet_name=f"AI_{candidate.get('asset')}_{candidate.get('duration')}",
        signal_time=str(candidate.get("ts") or now_iso()),
        title=str(candidate.get("question") or slug),
        slug=slug,
        event_slug=str(candidate.get("event_slug") or slug),
        outcome=outcome,
        stake=stake,
        source_price=fnum(candidate.get("best_ask")),
        market=market,
        extra={
            "estimated_q": candidate.get("estimated_q"),
            "ev": candidate.get("expected_edge_bps"),
            "price_bucket": f"{candidate.get('asset')}:{candidate.get('duration')}",
            "recommended_stake": f"{stake:.4f}",
        },
    )
    append_trade(
        args.trades_log,
        {
            "ts": now_iso(),
            "id": trade_id,
            "candidate_id": candidate.get("candidate_id"),
            "asset": candidate.get("asset"),
            "slug": slug,
            "question": candidate.get("question"),
            "direction": outcome,
            "stake": f"{stake:.4f}",
            "estimated_q": candidate.get("estimated_q"),
            "best_bid": candidate.get("best_bid"),
            "best_ask": candidate.get("best_ask"),
            "sim_fill_price": candidate.get("sim_fill_price"),
            "sim_shares": candidate.get("sim_shares"),
            "would_live_fill": candidate.get("would_live_fill"),
            "slippage_bps": candidate.get("slippage_bps"),
            "source_to_ask_gap": candidate.get("source_to_ask_gap"),
            "expected_edge_bps": candidate.get("expected_edge_bps"),
            "ai_confidence": decision.get("confidence"),
            "ai_reason": decision.get("reason"),
            "ai_risk_flags": ";".join(decision.get("risk_flags") or []),
            "status": "OPEN",
            "url": candidate.get("url"),
        },
    )
    return True


def run_once(args: argparse.Namespace) -> tuple[int, int, int, int, int]:
    errors = 0
    try:
        update_audit_marks(args.audit_log, market_loader, max_rows=args.max_audit_updates)
    except Exception as exc:
        errors += 1
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] AI audit update skipped | {type(exc).__name__}: {exc}", flush=True)
    try:
        candidates = build_candidates(args)
    except Exception as exc:
        errors += 1
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] AI candidate build failed | {type(exc).__name__}: {exc}", flush=True)
        candidates = []
    write_candidates(candidates, args.candidate_output)
    seen = read_seen_decisions(args.decisions_log)
    take_count = 0
    skip_count = 0
    opened_count = 0
    for candidate in candidates:
        cid = str(candidate.get("candidate_id") or "")
        if cid and cid in seen:
            continue
        decision = decide(candidate, args)
        row = decision_row(candidate, decision)
        append_decision(args.decisions_log, row)
        seen.add(cid)
        if decision.get("decision") == "TAKE":
            take_count += 1
            if simulate_take(args, candidate, decision):
                opened_count += 1
        else:
            skip_count += 1
    return len(candidates), take_count, skip_count, opened_count, errors


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--assets", default="BTC,ETH")
    parser.add_argument("--durations", default="5m,15m")
    parser.add_argument("--lookahead-seconds", type=int, default=1200)
    parser.add_argument("--stake-usdc", type=float, default=1.0)
    parser.add_argument("--bankroll-usdc", type=float, default=1000.0)
    parser.add_argument("--min-take-stake-usdc", type=float, default=1.0)
    parser.add_argument("--min-confidence", type=float, default=0.58)
    parser.add_argument("--min-move-bps", type=float, default=8.0)
    parser.add_argument("--min-expected-edge-bps", type=float, default=25.0)
    parser.add_argument("--min-price-sources", type=int, default=2)
    parser.add_argument("--max-source-spread-bps", type=float, default=8.0)
    parser.add_argument("--max-source-to-ask-gap", type=float, default=0.015)
    parser.add_argument("--max-entry-price", type=float, default=0.70)
    parser.add_argument("--max-slippage-bps", type=float, default=200.0)
    parser.add_argument("--min-ask-depth-usdc", type=float, default=20.0)
    parser.add_argument("--min-seconds-after-start", type=int, default=15)
    parser.add_argument("--min-seconds-before-end", type=int, default=35)
    parser.add_argument("--signal-bucket-seconds", type=int, default=60)
    parser.add_argument("--max-entries-per-market", type=int, default=1)
    parser.add_argument("--max-open-positions", type=int, default=100)
    parser.add_argument("--max-audit-updates", type=int, default=50)
    parser.add_argument("--openai-timeout-sec", type=float, default=12.0)
    parser.add_argument("--trades-log", type=Path, default=Path("ai_signal_trades.csv"))
    parser.add_argument("--audit-log", type=Path, default=Path("ai_signal_trade_audit.csv"))
    parser.add_argument("--decisions-log", type=Path, default=Path("ai_signal_decisions.csv"))
    parser.add_argument("--candidate-output", type=Path, default=Path("crypto_lead_lag_candidates.csv"))
    parser.add_argument("--health-output", type=Path, default=Path("ai_signal_health.csv"))
    parser.add_argument("--max-error-backoff-sec", type=float, default=180.0)
    parser.add_argument("--max-scans", type=int, default=0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    scan = 0
    failure_streak = 0
    while True:
        scan += 1
        next_sleep = args.interval
        try:
            candidates, takes, skips, opened, errors = run_once(args)
            if errors or candidates == 0:
                failure_streak += 1
            else:
                failure_streak = 0
            if failure_streak:
                next_sleep = min(args.max_error_backoff_sec, args.interval * min(6, 1 + failure_streak))
            write_health(
                args.health_output,
                {
                    "ts": now_iso(),
                    "scan": scan,
                    "candidates": candidates,
                    "take": takes,
                    "skip": skips,
                    "opened": opened,
                    "errors": errors,
                    "failure_streak": failure_streak,
                    "next_sleep_sec": f"{next_sleep:.2f}",
                },
            )
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] AI signal scan #{scan} | "
                f"candidates={candidates} | take={takes} | skip={skips} | opened={opened} | "
                f"errors={errors} | next_sleep={next_sleep:.0f}s",
                flush=True,
            )
        except KeyboardInterrupt:
            print("Stopped.", flush=True)
            return 130
        except Exception as exc:
            failure_streak += 1
            next_sleep = min(args.max_error_backoff_sec, args.interval * min(6, 1 + failure_streak))
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] AI signal simulator error: {type(exc).__name__}: {exc}",
                file=sys.stderr,
                flush=True,
            )
        if args.once or (args.max_scans and scan >= args.max_scans):
            return 0
        time.sleep(next_sleep)


if __name__ == "__main__":
    raise SystemExit(main())
