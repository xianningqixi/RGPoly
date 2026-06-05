#!/usr/bin/env python3
"""Explain why crypto lead-lag candidates are or are not produced.

Read-only diagnostic. It does not call the AI decision engine and never opens
simulated trades.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from crypto_lead_lag_signal import (
    ASSETS,
    DURATIONS,
    consensus,
    discover_markets,
    estimated_probability,
    fnum,
    open_price,
    price_sources,
    token_snapshot,
)


FIELDS = [
    "asset",
    "slug",
    "duration",
    "stage",
    "reason",
    "move_bps",
    "source_spread_bps",
    "estimated_q",
    "best_ask",
    "sim_fill_price",
    "source_to_ask_gap",
    "expected_edge_bps",
    "seconds_to_end",
]


def record(rows: list[dict[str, Any]], market: Any, stage: str, reason: str, **extra: Any) -> None:
    row = {
        "asset": getattr(market, "asset", ""),
        "slug": getattr(market, "slug", ""),
        "duration": getattr(market, "duration", ""),
        "stage": stage,
        "reason": reason,
        **extra,
    }
    rows.append(row)


def diagnose(args: argparse.Namespace) -> list[dict[str, Any]]:
    assets = [item.strip().upper() for item in args.assets.split(",") if item.strip()]
    durations = {item.strip() for item in args.durations.split(",") if item.strip()}
    rows: list[dict[str, Any]] = []
    try:
        markets = discover_markets(assets, args.lookahead_seconds, durations)
    except Exception as exc:
        rows.append({"stage": "discover", "reason": str(exc)})
        return rows

    now = int(time.time())
    for market in markets:
        seconds_to_end = market.end_ts - now
        if now < market.start_ts + args.min_seconds_after_start:
            record(rows, market, "time_filter", "too_early", seconds_to_end=seconds_to_end)
            continue
        if now > market.end_ts - args.min_seconds_before_end:
            record(rows, market, "time_filter", "too_late", seconds_to_end=seconds_to_end)
            continue
        try:
            start = open_price(market.asset, market.start_ts)
        except Exception as exc:
            record(rows, market, "open_price", str(exc), seconds_to_end=seconds_to_end)
            continue
        if not start:
            record(rows, market, "open_price", "missing", seconds_to_end=seconds_to_end)
            continue
        try:
            prices = price_sources(market.asset)
        except Exception as exc:
            record(rows, market, "price_sources", str(exc), seconds_to_end=seconds_to_end)
            continue
        if len(prices) < args.min_price_sources:
            record(rows, market, "price_sources", "not_enough_sources", seconds_to_end=seconds_to_end)
            continue
        current, source_spread = consensus(prices)
        move_bps = (current / start - 1.0) * 10000
        if source_spread > args.max_source_spread_bps:
            record(rows, market, "source_spread", "too_wide", move_bps=move_bps, source_spread_bps=source_spread, seconds_to_end=seconds_to_end)
            continue
        if abs(move_bps) < args.min_move_bps:
            record(rows, market, "move", "too_small", move_bps=move_bps, source_spread_bps=source_spread, seconds_to_end=seconds_to_end)
            continue
        direction = "Up" if move_bps > 0 else "Down"
        token_id = market.up_token if direction == "Up" else market.down_token
        q_up = estimated_probability(move_bps, args.min_move_bps, seconds_to_end, DURATIONS[market.duration])
        estimated_q = q_up if direction == "Up" else 1.0 - q_up
        try:
            snap = token_snapshot(token_id, args.stake_usdc)
        except Exception as exc:
            record(rows, market, "order_book", str(exc), move_bps=move_bps, source_spread_bps=source_spread, estimated_q=estimated_q, seconds_to_end=seconds_to_end)
            continue
        best_ask = fnum(snap.get("best_ask"))
        fill = fnum(snap.get("sim_fill_price"))
        source_to_ask_gap = best_ask - estimated_q
        expected_edge_bps = (estimated_q - fill) * 10000
        payload = {
            "move_bps": move_bps,
            "source_spread_bps": source_spread,
            "estimated_q": estimated_q,
            "best_ask": best_ask,
            "sim_fill_price": fill,
            "source_to_ask_gap": source_to_ask_gap,
            "expected_edge_bps": expected_edge_bps,
            "seconds_to_end": seconds_to_end,
        }
        if best_ask <= 0:
            record(rows, market, "order_book", "missing_ask", **payload)
        elif best_ask > args.max_entry_price:
            record(rows, market, "entry_price", "too_expensive", **payload)
        elif expected_edge_bps < args.min_expected_edge_bps:
            record(rows, market, "edge", "too_low", **payload)
        elif source_to_ask_gap > args.max_source_to_ask_gap:
            record(rows, market, "gap", "too_wide", **payload)
        else:
            record(rows, market, "pass", "candidate", **payload)
    return rows


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDS})


def render(rows: list[dict[str, Any]]) -> str:
    counts = Counter(f"{row.get('stage')}:{row.get('reason')}" for row in rows)
    lines = [
        "# Crypto Lead-Lag Diagnostics",
        "",
        "Read-only. Shows why candidates pass or fail local filters.",
        "",
        "| stage | reason | count |",
        "|---|---|---:|",
    ]
    for key, count in counts.most_common():
        stage, reason = key.split(":", 1)
        lines.append(f"| {stage} | {reason} | {count} |")
    lines.extend(["", "## Closest Edge Rows", "", "| asset | duration | stage | move_bps | ask | q | edge_bps | gap | slug |", "|---|---|---|---:|---:|---:|---:|---:|---|"])
    ranked = sorted(rows, key=lambda row: fnum(row.get("expected_edge_bps")), reverse=True)
    for row in ranked[:20]:
        lines.append(
            f"| {row.get('asset','')} | {row.get('duration','')} | {row.get('stage','')} | "
            f"{fnum(row.get('move_bps')):.2f} | {fnum(row.get('best_ask')):.4f} | "
            f"{fnum(row.get('estimated_q')):.4f} | {fnum(row.get('expected_edge_bps')):.1f} | "
            f"{fnum(row.get('source_to_ask_gap')):.4f} | {row.get('slug','')} |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", default="BTC,ETH")
    parser.add_argument("--durations", default="5m,15m")
    parser.add_argument("--lookahead-seconds", type=int, default=1200)
    parser.add_argument("--stake-usdc", type=float, default=1.0)
    parser.add_argument("--min-move-bps", type=float, default=8.0)
    parser.add_argument("--min-expected-edge-bps", type=float, default=25.0)
    parser.add_argument("--min-price-sources", type=int, default=2)
    parser.add_argument("--max-source-spread-bps", type=float, default=8.0)
    parser.add_argument("--max-source-to-ask-gap", type=float, default=0.015)
    parser.add_argument("--max-entry-price", type=float, default=0.70)
    parser.add_argument("--min-seconds-after-start", type=int, default=15)
    parser.add_argument("--min-seconds-before-end", type=int, default=35)
    parser.add_argument("--csv", type=Path, default=Path("crypto_lead_lag_diagnostics.csv"))
    parser.add_argument("--md", type=Path, default=Path("crypto_lead_lag_diagnostics.md"))
    parser.add_argument("--once", action="store_true", help="Compatibility flag; diagnostics always run once")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = diagnose(args)
    write_csv(rows, args.csv)
    text = render(rows)
    args.md.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
