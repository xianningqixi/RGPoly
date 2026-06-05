#!/usr/bin/env python3
"""Shadow-observe BTC directional candidate wallets without opening paper trades."""

from __future__ import annotations

import argparse
import csv
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trade_audit import order_snapshot

import btc_directional_wallet_copy_sim as btc


ROOT = Path.cwd()
OUT_CSV = ROOT / "btc_candidate_shadow_observer.csv"
SEEN = ROOT / "btc_candidate_shadow_seen.json"

FIELDS = [
    "ts",
    "wallet",
    "id",
    "reason",
    "title",
    "slug",
    "outcome",
    "source_price",
    "source_usdc",
    "signal_age_sec",
    "best_ask",
    "ask_depth_usdc",
    "would_live_fill",
    "slippage_bps",
    "source_to_ask_gap",
    "market_current_price",
    "notes",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def append_row(path: Path, row: dict[str, Any]) -> None:
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in FIELDS})


def shadow_snapshot(row: dict[str, Any], stake_usdc: float) -> dict[str, Any]:
    slug = str(row.get("slug") or "")
    outcome = str(row.get("outcome") or "")
    source_price = fnum(row.get("price"))
    market = btc.market_by_slug(slug)
    current = btc.latest_price(slug, outcome)
    try:
        snapshot = order_snapshot(market, outcome, stake_usdc) if market else {}
    except Exception:
        snapshot = {}
    fill_price = fnum(snapshot.get("sim_fill_price")) or source_price
    best_ask = fnum(snapshot.get("best_ask"))
    return {
        "best_ask": f"{best_ask:.6f}" if best_ask else "",
        "ask_depth_usdc": f"{fnum(snapshot.get('ask_depth_usdc')):.4f}",
        "would_live_fill": "YES" if snapshot.get("would_live_fill") else "NO",
        "slippage_bps": f"{((fill_price - source_price) / source_price * 10000) if source_price > 0 else 0.0:.2f}",
        "source_to_ask_gap": f"{(best_ask - source_price) if best_ask > 0 and source_price > 0 else 999.0:.6f}",
        "market_current_price": f"{current:.6f}" if current is not None else "",
    }


def args_for_filters(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        allowed_outcome=set(args.allowed_outcome or []),
        block_market_keyword=list(args.block_market_keyword or []),
        max_source_age_sec=args.max_source_age_sec,
        min_price=args.min_price,
        max_price=args.max_price,
        yes_max_price=args.yes_max_price,
        min_source_usdc=args.min_source_usdc,
    )


def run_once(args: argparse.Namespace) -> int:
    filter_args = args_for_filters(args)
    candidates = btc.load_candidate_wallets(args.wallet_candidates, args.candidate_limit)
    seen = btc.read_seen(args.seen)
    new_rows = 0
    for alias, wallet in candidates.items():
        try:
            rows = btc.fetch_recent(wallet, args.limit)
        except Exception as exc:
            append_row(
                args.csv,
                {
                    "ts": now_iso(),
                    "wallet": alias,
                    "reason": f"fetch_error:{type(exc).__name__}",
                    "notes": str(exc),
                },
            )
            continue
        for row in reversed(rows):
            sid = btc.source_id(alias, row)
            if sid in seen:
                continue
            reason = btc.should_copy_reason(row, filter_args)
            extra: dict[str, Any] = {}
            if reason == "TAKE":
                extra = shadow_snapshot(row, args.shadow_stake_usdc)
            append_row(
                args.csv,
                {
                    "ts": now_iso(),
                    "wallet": alias,
                    "id": sid,
                    "reason": reason,
                    "title": row.get("title") or "",
                    "slug": row.get("slug") or "",
                    "outcome": row.get("outcome") or "",
                    "source_price": f"{fnum(row.get('price')):.6f}",
                    "source_usdc": f"{fnum(row.get('usdcSize')):.4f}",
                    "signal_age_sec": f"{time.time() - fnum(row.get('timestamp')):.2f}",
                    **extra,
                    "notes": "shadow only; not included in realized ROI",
                },
            )
            seen.add(sid)
            new_rows += 1
            if new_rows >= args.max_new_rows:
                btc.write_seen(args.seen, seen)
                return new_rows
        time.sleep(0.1)
    btc.write_seen(args.seen, seen)
    return new_rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--wallet-candidates", type=Path, default=ROOT / "btc_directional_candidate_pool.csv")
    parser.add_argument("--candidate-limit", type=int, default=12)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--max-new-rows", type=int, default=200)
    parser.add_argument("--shadow-stake-usdc", type=float, default=1.0)
    parser.add_argument("--allowed-outcome", action="append", default=["No"])
    parser.add_argument("--block-market-keyword", action="append", default=["reach", "dip"])
    parser.add_argument("--max-source-age-sec", type=float, default=90.0)
    parser.add_argument("--min-source-usdc", type=float, default=3.0)
    parser.add_argument("--min-price", type=float, default=0.03)
    parser.add_argument("--max-price", type=float, default=0.80)
    parser.add_argument("--yes-max-price", type=float, default=0.65)
    parser.add_argument("--csv", type=Path, default=OUT_CSV)
    parser.add_argument("--seen", type=Path, default=SEEN)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    new_rows = run_once(args)
    print(f"btc_candidate_shadow_observer: new rows {new_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
