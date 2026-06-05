#!/usr/bin/env python3
"""Audit helpers for simulated Polymarket copy trades."""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scan_polymarket_arbitrage import fetch_books, normalize_levels, parse_json_list


AUDIT_FIELDS = [
    "audit_ts",
    "id",
    "strategy",
    "wallet_name",
    "signal_time",
    "detected_time",
    "title",
    "slug",
    "event_slug",
    "outcome",
    "stake",
    "source_price",
    "best_bid",
    "best_ask",
    "ask_depth_shares",
    "ask_depth_usdc",
    "sim_fill_price",
    "sim_shares",
    "would_live_fill",
    "slippage_bps",
    "estimated_q",
    "ev",
    "price_bucket",
    "wallet_sample_size",
    "wallet_win_rate_1h",
    "recommended_stake",
    "price_2m",
    "pnl_2m",
    "slippage_pnl_2m",
    "price_10m",
    "pnl_10m",
    "slippage_pnl_10m",
    "price_1h",
    "pnl_1h",
    "slippage_pnl_1h",
    "final_price",
    "final_result",
    "final_pnl",
    "slippage_final_pnl",
    "execution_source",
    "token_id",
    "fill_status",
    "spent_usdc",
    "unfilled_usdc",
    "levels_used",
    "fee_rate",
    "fee_usdc",
    "total_cost_usdc",
    "fee_adjusted_final_pnl",
    "status",
    "url",
]


STRICT_SIM_EXECUTION = os.getenv("POLY_STRICT_SIM_EXECUTION", "1").lower() not in {"0", "false", "no"}


def fnum(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def signal_time_from_epoch(value: Any) -> str:
    ts = fnum(value)
    if ts <= 0:
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def inferred_fee_rate(strategy: str = "", title: str = "", slug: str = "", event_slug: str = "") -> float:
    text = " ".join([strategy, title, slug, event_slug]).lower()
    if any(term in text for term in ("bitcoin", "btc", "ethereum", "eth", "solana", " sol", "bnb", "xrp", "crypto")):
        return 0.07
    if any(term in text for term in ("weather", "temperature", "highest-temperature", "lowest-temperature")):
        return 0.05
    return 0.0


def latest_audit_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            rows[row["id"]] = row
    return rows


def audit_header(path: Path) -> list[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        return next(reader, [])


def append_audit_row(path: Path, row: dict[str, Any]) -> None:
    exists = path.exists() and audit_header(path) == AUDIT_FIELDS
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=AUDIT_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in AUDIT_FIELDS})


def token_for_outcome(market: dict[str, Any], outcome: str) -> str:
    outcomes = [str(item) for item in parse_json_list(market.get("outcomes"))]
    token_ids = [str(item) for item in parse_json_list(market.get("clobTokenIds"))]
    for name, token_id in zip(outcomes, token_ids):
        if name.lower() == outcome.lower():
            return token_id
    return ""


def outcome_price(market: dict[str, Any], outcome: str) -> float | None:
    outcomes = [str(item) for item in parse_json_list(market.get("outcomes"))]
    prices = parse_json_list(market.get("outcomePrices"))
    for name, price in zip(outcomes, prices):
        if name.lower() == outcome.lower():
            return fnum(price)
    return None


def order_snapshot(market: dict[str, Any], outcome: str, stake: float, fee_rate: float = 0.0) -> dict[str, Any]:
    token_id = token_for_outcome(market, outcome)
    if not token_id:
        return {}
    books = fetch_books([token_id], chunk_size=1)
    book = books.get(token_id, {})
    asks = normalize_levels(book, "asks")
    bids = normalize_levels(book, "bids")
    best_ask = asks[0].price if asks else None
    best_bid = bids[0].price if bids else None
    ask_depth_shares = sum(level.size for level in asks)
    ask_depth_usdc = sum(level.price * level.size for level in asks)

    remaining = stake
    shares = 0.0
    spent = 0.0
    fee_usdc = 0.0
    levels_used = 0
    for level in asks:
        max_usdc = level.price * level.size
        use_usdc = min(remaining, max_usdc)
        if use_usdc <= 0:
            continue
        take_shares = use_usdc / level.price
        shares += take_shares
        spent += use_usdc
        fee_usdc += take_shares * fee_rate * level.price * (1.0 - level.price)
        remaining -= use_usdc
        levels_used += 1
        if remaining <= 1e-9:
            break
    fill_price = spent / shares if shares > 0 else None
    would_live_fill = remaining <= 1e-9
    return {
        "token_id": token_id,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "ask_depth_shares": ask_depth_shares,
        "ask_depth_usdc": ask_depth_usdc,
        "sim_fill_price": fill_price,
        "sim_shares": shares,
        "would_live_fill": would_live_fill,
        "spent_usdc": spent,
        "unfilled_usdc": max(0.0, remaining),
        "fee_rate": fee_rate,
        "fee_usdc": fee_usdc,
        "total_cost_usdc": spent + fee_usdc,
        "levels_used": levels_used,
        "fill_status": "FULL" if would_live_fill else "PARTIAL" if shares > 0 else "NO_FILL",
    }


def ensure_audit_open(
    path: Path,
    *,
    trade_id: str,
    strategy: str,
    wallet_name: str,
    signal_time: str,
    title: str,
    slug: str,
    event_slug: str,
    outcome: str,
    stake: float,
    source_price: float,
    market: dict[str, Any] | None,
    fee_rate: float | None = None,
    extra: dict[str, Any] | None = None,
) -> bool:
    if trade_id in latest_audit_rows(path):
        return False
    extra = extra or {}
    effective_fee_rate = (
        fee_rate
        if fee_rate is not None
        else fnum(extra.get("fee_rate"))
        if extra.get("fee_rate") not in {"", None}
        else inferred_fee_rate(strategy, title, slug, event_slug)
    )
    if extra.get("sim_fill_price") not in {"", None}:
        snapshot = {
            "token_id": extra.get("token_id"),
            "best_bid": extra.get("best_bid"),
            "best_ask": extra.get("best_ask"),
            "ask_depth_shares": extra.get("ask_depth_shares"),
            "ask_depth_usdc": extra.get("ask_depth_usdc"),
            "sim_fill_price": extra.get("sim_fill_price"),
            "sim_shares": extra.get("sim_shares"),
            "would_live_fill": extra.get("would_live_fill") in {True, "YES", "true", "True", "1", 1},
            "spent_usdc": extra.get("spent_usdc"),
            "unfilled_usdc": extra.get("unfilled_usdc"),
            "fee_rate": effective_fee_rate,
            "fee_usdc": extra.get("fee_usdc"),
            "total_cost_usdc": extra.get("total_cost_usdc"),
            "levels_used": extra.get("levels_used"),
            "fill_status": extra.get("fill_status"),
        }
    else:
        try:
            snapshot = order_snapshot(market, outcome, stake, fee_rate=effective_fee_rate) if market else {}
        except Exception:
            snapshot = {}
    if not snapshot.get("token_id") and market:
        snapshot["token_id"] = token_for_outcome(market, outcome)
    if STRICT_SIM_EXECUTION:
        if not snapshot.get("token_id") and not extra.get("token_id"):
            raise RuntimeError(f"strict_sim_execution_failed: token_id_missing trade_id={trade_id}")
        if not snapshot.get("sim_fill_price") or not snapshot.get("sim_shares"):
            raise RuntimeError(f"strict_sim_execution_failed: no_orderbook_fill trade_id={trade_id}")
        if not snapshot.get("would_live_fill"):
            raise RuntimeError(f"strict_sim_execution_failed: not_full_live_fill trade_id={trade_id}")
    fill_price = fnum(snapshot.get("sim_fill_price")) or source_price
    sim_shares = fnum(snapshot.get("sim_shares")) or (stake / fill_price if fill_price > 0 else 0)
    spent_usdc = fnum(snapshot.get("spent_usdc")) or stake
    fee_usdc = fnum(snapshot.get("fee_usdc"))
    if fee_usdc <= 0 and effective_fee_rate > 0 and fill_price > 0 and sim_shares > 0:
        fee_usdc = sim_shares * effective_fee_rate * fill_price * (1.0 - fill_price)
    total_cost_usdc = fnum(snapshot.get("total_cost_usdc")) or (spent_usdc + fee_usdc)
    slippage_bps = ((fill_price - source_price) / source_price * 10000) if source_price > 0 else 0.0
    url = f"https://polymarket.com/event/{event_slug}" if event_slug else ""
    append_audit_row(
        path,
        {
            "audit_ts": now_utc(),
            "id": trade_id,
            "strategy": strategy,
            "wallet_name": wallet_name,
            "signal_time": signal_time,
            "detected_time": now_utc(),
            "title": title,
            "slug": slug,
            "event_slug": event_slug,
            "outcome": outcome,
            "stake": f"{stake:.4f}",
            "source_price": f"{source_price:.6f}",
            "best_bid": f"{fnum(snapshot.get('best_bid')):.6f}" if snapshot.get("best_bid") is not None else "",
            "best_ask": f"{fnum(snapshot.get('best_ask')):.6f}" if snapshot.get("best_ask") is not None else "",
            "ask_depth_shares": f"{fnum(snapshot.get('ask_depth_shares')):.4f}",
            "ask_depth_usdc": f"{fnum(snapshot.get('ask_depth_usdc')):.4f}",
            "sim_fill_price": f"{fill_price:.6f}",
            "sim_shares": f"{sim_shares:.4f}",
            "would_live_fill": "YES" if snapshot.get("would_live_fill") else "NO",
            "slippage_bps": f"{slippage_bps:.2f}",
            "estimated_q": extra.get("estimated_q", ""),
            "ev": extra.get("ev", ""),
            "price_bucket": extra.get("price_bucket", ""),
            "wallet_sample_size": extra.get("wallet_sample_size", ""),
            "wallet_win_rate_1h": extra.get("wallet_win_rate_1h", ""),
            "recommended_stake": extra.get("recommended_stake", ""),
            "execution_source": "REALTIME_ORDERBOOK",
            "token_id": snapshot.get("token_id", ""),
            "fill_status": snapshot.get("fill_status") or ("FULL" if snapshot.get("would_live_fill") else "NO_FILL"),
            "spent_usdc": f"{spent_usdc:.4f}",
            "unfilled_usdc": f"{fnum(snapshot.get('unfilled_usdc')):.4f}",
            "levels_used": snapshot.get("levels_used", ""),
            "fee_rate": f"{effective_fee_rate:.6f}",
            "fee_usdc": f"{fee_usdc:.6f}",
            "total_cost_usdc": f"{total_cost_usdc:.6f}",
            "fee_adjusted_final_pnl": "",
            "status": "OPEN",
            "url": url,
        },
    )
    return True


def update_audit_marks(path: Path, market_loader: Any, max_rows: int | None = None) -> None:
    rows = latest_audit_rows(path)
    now = datetime.now(timezone.utc)
    candidates = [row for row in rows.values() if row.get("final_result") not in {"WIN", "LOSS"}]
    candidates.sort(key=lambda row: parse_dt(row.get("audit_ts", "")) or datetime.min.replace(tzinfo=timezone.utc))
    if max_rows is not None and max_rows > 0:
        candidates = candidates[:max_rows]
    for row in candidates:
        detected = parse_dt(row.get("detected_time", ""))
        if detected is None:
            continue
        try:
            market = market_loader(row.get("slug") or "")
            if not market:
                continue
            current = outcome_price(market, row.get("outcome") or "")
            if current is None:
                continue
        except Exception:
            continue
        updated = dict(row)
        elapsed = (now - detected).total_seconds()
        stake = fnum(row.get("stake"))
        no_slip_shares = stake / fnum(row.get("source_price")) if fnum(row.get("source_price")) > 0 else 0.0
        slip_shares = fnum(row.get("sim_shares"))
        spent_usdc = fnum(row.get("spent_usdc")) or stake
        fee_usdc = fnum(row.get("fee_usdc"))

        def fill_milestone(label: str) -> None:
            updated[f"price_{label}"] = f"{current:.6f}"
            updated[f"pnl_{label}"] = f"{(no_slip_shares * current - stake):.4f}"
            updated[f"slippage_pnl_{label}"] = f"{(slip_shares * current - spent_usdc - fee_usdc):.4f}"

        if elapsed >= 120 and not row.get("price_2m"):
            fill_milestone("2m")
        if elapsed >= 600 and not row.get("price_10m"):
            fill_milestone("10m")
        if elapsed >= 3600 and not row.get("price_1h"):
            fill_milestone("1h")

        final_result = ""
        if current >= 0.999:
            final_result = "WIN"
        elif current <= 0.001:
            final_result = "LOSS"
        if final_result and row.get("final_result") not in {"WIN", "LOSS"}:
            updated["final_price"] = f"{current:.6f}"
            updated["final_result"] = final_result
            updated["final_pnl"] = f"{(no_slip_shares * current - stake):.4f}"
            updated["slippage_final_pnl"] = f"{(slip_shares * current - spent_usdc - fee_usdc):.4f}"
            updated["fee_adjusted_final_pnl"] = updated["slippage_final_pnl"]
            updated["status"] = "FINAL"
        elif updated != row:
            updated["status"] = "MARK"

        if updated != row:
            updated["audit_ts"] = now_utc()
            append_audit_row(path, updated)
