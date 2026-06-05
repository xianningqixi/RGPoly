#!/usr/bin/env python3
"""Bond-style Polymarket candidate scanner.

Read-only simulation. This does not follow wallets and does not place orders.
It searches for binary markets that are close to settlement, already priced in a
high-probability range, and still have acceptable execution cost.

The output is a candidate list, not a buy signal. A real entry still requires a
separate fair-probability layer.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scan_polymarket_arbitrage import (
    all_token_ids,
    collect_active_markets,
    fetch_books,
    market_url,
    normalize_levels,
    parse_json_list,
)


FIELDS = [
    "ts",
    "scan_id",
    "title",
    "slug",
    "category",
    "outcome",
    "end_date",
    "hours_to_end",
    "best_bid",
    "best_ask",
    "spread",
    "ask_depth_usdc",
    "sim_fill_price",
    "stake",
    "shares",
    "break_even_prob",
    "upside_if_win",
    "loss_if_wrong",
    "execution_ok",
    "reason",
    "url",
]


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_text() -> str:
    return now_utc().isoformat()


def fnum(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def category_of(market: dict[str, Any]) -> str:
    text = " ".join(
        str(market.get(key) or "")
        for key in ["question", "title", "slug", "description", "category"]
    ).lower()
    if "highest temperature" in text or "lowest temperature" in text or "weather" in text:
        return "weather"
    if "bitcoin up or down" in text or "ethereum up or down" in text or "solana up or down" in text or "xrp up or down" in text:
        return "crypto_updown"
    if "bitcoin" in text or "ethereum" in text or "solana" in text or "xrp" in text:
        return "crypto"
    return str(market.get("category") or "other").lower() or "other"


def binary_outcomes(market: dict[str, Any]) -> list[tuple[str, str]]:
    outcomes = [str(item) for item in parse_json_list(market.get("outcomes"))]
    token_ids = [str(item) for item in parse_json_list(market.get("clobTokenIds"))]
    pairs = [(name, token_id) for name, token_id in zip(outcomes, token_ids) if token_id]
    return pairs if len(pairs) == 2 else []


def fill_buy(asks: list[Any], stake: float) -> tuple[float, float] | None:
    remaining = stake
    shares = 0.0
    spent = 0.0
    for level in asks:
        max_usdc = level.price * level.size
        use_usdc = min(remaining, max_usdc)
        if use_usdc <= 0:
            continue
        shares += use_usdc / level.price
        spent += use_usdc
        remaining -= use_usdc
        if remaining <= 1e-9:
            break
    if remaining > 1e-6 or shares <= 0:
        return None
    return spent / shares, shares


def evaluate_market(market: dict[str, Any], books: dict[str, dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    end_dt = parse_dt(market.get("endDateIso") or market.get("endDate"))
    if end_dt is None:
        return []
    hours_to_end = (end_dt - now_utc()).total_seconds() / 3600.0
    if hours_to_end < args.min_hours_to_end or hours_to_end > args.max_hours_to_end:
        return []

    rows: list[dict[str, Any]] = []
    pairs = binary_outcomes(market)
    if not pairs:
        return rows

    category = category_of(market)
    title = str(market.get("question") or market.get("title") or "")
    slug = str(market.get("slug") or "")
    for outcome, token_id in pairs:
        book = books.get(token_id, {})
        asks = normalize_levels(book, "asks")
        bids = normalize_levels(book, "bids")
        if not asks or not bids:
            continue
        best_ask = asks[0].price
        best_bid = bids[0].price
        spread = best_ask - best_bid
        if best_ask < args.min_price or best_ask > args.max_price:
            continue
        if spread > args.max_spread:
            continue
        ask_depth_usdc = sum(level.price * level.size for level in asks)
        if ask_depth_usdc < args.min_ask_depth_usdc:
            continue
        filled = fill_buy(asks, args.stake_usdc)
        if filled is None:
            continue
        fill_price, shares = filled
        if fill_price > args.max_price:
            continue
        slippage_to_ask = fill_price - best_ask
        if slippage_to_ask > args.max_fill_over_ask:
            continue
        upside = shares * 1.0 - args.stake_usdc
        loss = args.stake_usdc
        rows.append(
            {
                "title": title,
                "slug": slug,
                "category": category,
                "outcome": outcome,
                "end_date": end_dt.isoformat(),
                "hours_to_end": hours_to_end,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread": spread,
                "ask_depth_usdc": ask_depth_usdc,
                "sim_fill_price": fill_price,
                "stake": args.stake_usdc,
                "shares": shares,
                "break_even_prob": fill_price,
                "upside_if_win": upside,
                "loss_if_wrong": loss,
                "execution_ok": "YES",
                "reason": "near_settlement_high_probability_cost_ok",
                "url": market_url(market),
            }
        )
    return rows


def append_rows(path: Path, rows: list[dict[str, Any]], scan_id: int) -> None:
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        ts = now_text()
        for row in rows:
            out = dict(row)
            out["ts"] = ts
            out["scan_id"] = scan_id
            for key in [
                "hours_to_end",
                "best_bid",
                "best_ask",
                "spread",
                "ask_depth_usdc",
                "sim_fill_price",
                "stake",
                "shares",
                "break_even_prob",
                "upside_if_win",
                "loss_if_wrong",
            ]:
                out[key] = f"{fnum(out.get(key)):.6f}"
            writer.writerow({field: out.get(field, "") for field in FIELDS})


def write_alert(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text(f"BOND STYLE SCANNER\n{now_text()}\nNo candidates matched.\n", encoding="utf-8")
        return
    best = rows[0]
    text = (
        "BOND STYLE SCANNER\n"
        f"time: {now_text()}\n"
        f"candidate_count: {len(rows)}\n"
        f"best: {best['outcome']} @ {fnum(best['sim_fill_price']):.4f}\n"
        f"break_even_prob: {fnum(best['break_even_prob']):.4f}\n"
        f"hours_to_end: {fnum(best['hours_to_end']):.2f}\n"
        f"spread: {fnum(best['spread']):.4f}\n"
        f"depth: {fnum(best['ask_depth_usdc']):.2f}U\n"
        f"market: {best['title']}\n"
        f"url: {best['url']}\n"
        "note: candidate only; no fair-probability layer yet.\n"
    )
    path.write_text(text, encoding="utf-8")


def run_once(args: argparse.Namespace, scan_id: int) -> list[dict[str, Any]]:
    markets = collect_active_markets(args.sample_size, args.page_size)
    token_ids = all_token_ids(markets)
    books = fetch_books(token_ids, args.book_chunk_size) if token_ids else {}
    candidates: list[dict[str, Any]] = []
    for market in markets:
        candidates.extend(evaluate_market(market, books, args))
    candidates.sort(
        key=lambda row: (
            fnum(row.get("hours_to_end")),
            fnum(row.get("spread")),
            -fnum(row.get("ask_depth_usdc")),
        )
    )
    if candidates:
        append_rows(args.log, candidates[: args.max_log_rows], scan_id)
    write_alert(args.alert_file, candidates[: args.max_alert_rows])
    print(
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] bond scan #{scan_id} | markets {len(markets)} | candidates {len(candidates)}",
        flush=True,
    )
    for row in candidates[: args.print_rows]:
        print(
            f"  {row['outcome']} @{fnum(row['sim_fill_price']):.3f} "
            f"spread={fnum(row['spread']):.3f} end={fnum(row['hours_to_end']):.1f}h | {str(row['title'])[:90]}",
            flush=True,
        )
    return candidates


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-size", type=int, default=500)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--book-chunk-size", type=int, default=100)
    parser.add_argument("--interval", type=float, default=60.0)
    parser.add_argument("--max-scans", type=int, default=0)
    parser.add_argument("--stake-usdc", type=float, default=5.0)
    parser.add_argument("--min-hours-to-end", type=float, default=0.0)
    parser.add_argument("--max-hours-to-end", type=float, default=36.0)
    parser.add_argument("--min-price", type=float, default=0.75)
    parser.add_argument("--max-price", type=float, default=0.97)
    parser.add_argument("--max-spread", type=float, default=0.03)
    parser.add_argument("--max-fill-over-ask", type=float, default=0.01)
    parser.add_argument("--min-ask-depth-usdc", type=float, default=50.0)
    parser.add_argument("--max-log-rows", type=int, default=50)
    parser.add_argument("--max-alert-rows", type=int, default=5)
    parser.add_argument("--print-rows", type=int, default=5)
    parser.add_argument("--log", type=Path, default=Path("bond_style_candidates.csv"))
    parser.add_argument("--alert-file", type=Path, default=Path("latest_bond_style_alert.txt"))
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    scan_id = 0
    while True:
        scan_id += 1
        try:
            run_once(args, scan_id)
        except KeyboardInterrupt:
            return 130
        except Exception as exc:
            print(f"bond scan error: {exc}", flush=True)
        if args.once or (args.max_scans and scan_id >= args.max_scans):
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
