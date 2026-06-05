#!/usr/bin/env python3
"""Fee-aware live-like execution audit helpers for shadow simulations."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trade_audit import fnum, outcome_price, parse_dt


FIELDS = [
    "ts",
    "id",
    "strategy",
    "execution_source",
    "source_strategy",
    "source_id",
    "wallet_name",
    "signal_time",
    "title",
    "slug",
    "event_slug",
    "outcome",
    "intended_stake_usdc",
    "source_price",
    "best_bid",
    "best_ask",
    "ask_depth_shares",
    "ask_depth_usdc",
    "fill_status",
    "would_live_fill",
    "spent_usdc",
    "unfilled_usdc",
    "avg_fill_price",
    "shares",
    "levels_used",
    "fee_model",
    "fee_rate",
    "fee_usdc",
    "total_cost_usdc",
    "slippage_bps",
    "price_2m",
    "fee_adjusted_pnl_2m",
    "price_10m",
    "fee_adjusted_pnl_10m",
    "price_1h",
    "fee_adjusted_pnl_1h",
    "final_price",
    "final_result",
    "fee_adjusted_final_pnl",
    "status",
    "url",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def latest_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            if row.get("id"):
                rows[row["id"]] = row
    return rows


def append_row(path: Path, row: dict[str, Any]) -> None:
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in FIELDS})


def ensure_execution_open(
    path: Path,
    *,
    trade_id: str,
    strategy: str,
    source_strategy: str,
    source_id: str,
    source: dict[str, str],
    snapshot: dict[str, Any],
    fee_model: str,
    execution_source: str = "REALTIME_ORDERBOOK",
) -> None:
    if trade_id in latest_rows(path):
        return
    source_price = fnum(source.get("source_price")) or fnum(source.get("sim_fill_price"))
    fill_price = fnum(snapshot.get("sim_fill_price")) or source_price
    slippage_bps = ((fill_price - source_price) / source_price * 10000) if source_price > 0 else 0.0
    append_row(
        path,
        {
            "ts": now_utc(),
            "id": trade_id,
            "strategy": strategy,
            "execution_source": execution_source,
            "source_strategy": source_strategy,
            "source_id": source_id,
            "wallet_name": source.get("wallet_name", ""),
            "signal_time": source.get("signal_time", ""),
            "title": source.get("title", ""),
            "slug": source.get("slug", ""),
            "event_slug": source.get("event_slug", ""),
            "outcome": source.get("outcome", ""),
            "intended_stake_usdc": f"{fnum(source.get('shadow_stake')) or fnum(snapshot.get('intended_stake_usdc')):.4f}",
            "source_price": f"{source_price:.6f}",
            "best_bid": f"{fnum(snapshot.get('best_bid')):.6f}" if snapshot.get("best_bid") is not None else "",
            "best_ask": f"{fnum(snapshot.get('best_ask')):.6f}" if snapshot.get("best_ask") is not None else "",
            "ask_depth_shares": f"{fnum(snapshot.get('ask_depth_shares')):.4f}",
            "ask_depth_usdc": f"{fnum(snapshot.get('ask_depth_usdc')):.4f}",
            "fill_status": snapshot.get("fill_status", ""),
            "would_live_fill": "YES" if snapshot.get("would_live_fill") else "NO",
            "spent_usdc": f"{fnum(snapshot.get('spent_usdc')):.4f}",
            "unfilled_usdc": f"{fnum(snapshot.get('unfilled_usdc')):.4f}",
            "avg_fill_price": f"{fill_price:.6f}",
            "shares": f"{fnum(snapshot.get('sim_shares')):.4f}",
            "levels_used": snapshot.get("levels_used", ""),
            "fee_model": fee_model,
            "fee_rate": f"{fnum(snapshot.get('fee_rate')):.6f}",
            "fee_usdc": f"{fnum(snapshot.get('fee_usdc')):.6f}",
            "total_cost_usdc": f"{fnum(snapshot.get('total_cost_usdc')):.6f}",
            "slippage_bps": f"{slippage_bps:.2f}",
            "status": "OPEN",
            "url": source.get("url", ""),
        },
    )


def update_execution_marks(path: Path, market_loader: Any, max_rows: int | None = None) -> None:
    rows = latest_rows(path)
    now = datetime.now(timezone.utc)
    candidates = [row for row in rows.values() if row.get("final_result") not in {"WIN", "LOSS"}]
    candidates.sort(key=lambda row: parse_dt(row.get("ts", "")) or datetime.min.replace(tzinfo=timezone.utc))
    if max_rows is not None and max_rows > 0:
        candidates = candidates[:max_rows]
    for row in candidates:
        try:
            market = market_loader(row.get("slug") or "")
            current = outcome_price(market, row.get("outcome") or "") if market else None
        except Exception:
            continue
        if current is None:
            continue
        updated = dict(row)
        detected = parse_dt(row.get("ts", "")) or now
        elapsed = (now - detected.astimezone(timezone.utc)).total_seconds()
        shares = fnum(row.get("shares"))
        spent = fnum(row.get("spent_usdc"))
        fee = fnum(row.get("fee_usdc"))

        def set_mark(label: str) -> None:
            updated[f"price_{label}"] = f"{current:.6f}"
            updated[f"fee_adjusted_pnl_{label}"] = f"{(shares * current - spent - fee):.4f}"

        if elapsed >= 120 and not row.get("price_2m"):
            set_mark("2m")
        if elapsed >= 600 and not row.get("price_10m"):
            set_mark("10m")
        if elapsed >= 3600 and not row.get("price_1h"):
            set_mark("1h")

        final_result = ""
        if current >= 0.999:
            final_result = "WIN"
        elif current <= 0.001:
            final_result = "LOSS"
        if final_result:
            updated["final_price"] = f"{current:.6f}"
            updated["final_result"] = final_result
            updated["fee_adjusted_final_pnl"] = f"{(shares * current - spent - fee):.4f}"
            updated["status"] = "FINAL"
        elif updated != row:
            updated["status"] = "MARK"
        if updated != row:
            updated["ts"] = now_utc()
            append_row(path, updated)
