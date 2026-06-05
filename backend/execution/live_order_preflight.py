#!/usr/bin/env python3
"""Generate locked live-order preflight intents for selected strategies.

This module intentionally does not place orders, read private keys, or call any
authenticated trading endpoint. It converts active simulated source entries into
live-order intent rows and checks geoblock status, token id, order-book depth,
fill feasibility, and slippage.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trade_audit import order_snapshot

import btc_directional_wallet_copy_sim as btc_base
import weather_wallet_copy_sim as weather_base


ROOT = Path.cwd()

SOURCES = {
    "btc_directional_copy": {
        "audit": ROOT / "btc_directional_trade_audit.csv",
        "loader": btc_base.market_by_slug,
        "stake": 10.0,
        "fee_rate": 0.07,
        "fee_model": "polymarket_taker_crypto_fee",
    },
    "eth_directional_copy": {
        "audit": ROOT / "eth_directional_trade_audit.csv",
        "loader": btc_base.market_by_slug,
        "stake": 10.0,
        "fee_rate": 0.07,
        "fee_model": "polymarket_taker_crypto_fee",
    },
    "bnb_directional_copy": {
        "audit": ROOT / "bnb_directional_trade_audit.csv",
        "loader": btc_base.market_by_slug,
        "stake": 10.0,
        "fee_rate": 0.07,
        "fee_model": "polymarket_taker_crypto_fee",
    },
    "btc_no_dominant_candidate_copy": {
        "audit": ROOT / "btc_no_dominant_trade_audit.csv",
        "loader": btc_base.market_by_slug,
        "stake": 10.0,
        "fee_rate": 0.07,
        "fee_model": "polymarket_taker_crypto_fee",
    },
    "weather_high_prob_wallet_copy": {
        "audit": ROOT / "weather_high_prob_trade_audit.csv",
        "loader": weather_base.market_by_slug,
        "stake": 10.0,
        "fee_rate": 0.05,
        "fee_model": "polymarket_taker_weather_fee",
    },
    "btc_directional_live_shadow": {
        "audit": ROOT / "btc_directional_live_shadow_trade_audit.csv",
        "loader": btc_base.market_by_slug,
        "stake": 30.0,
        "fee_rate": 0.07,
        "fee_model": "polymarket_taker_crypto_fee",
    },
    "weather_high_prob_live_shadow": {
        "audit": ROOT / "weather_high_prob_live_shadow_trade_audit.csv",
        "loader": weather_base.market_by_slug,
        "stake": 30.0,
        "fee_rate": 0.05,
        "fee_model": "polymarket_taker_weather_fee",
    },
}

FIELDS = [
    "ts",
    "source_strategy",
    "source_id",
    "intent_id",
    "status",
    "reason",
    "live_trading_enabled",
    "geoblock_blocked",
    "source_age_sec",
    "wallet_name",
    "title",
    "slug",
    "event_slug",
    "outcome",
    "token_id",
    "tick_size",
    "neg_risk",
    "order_price_min",
    "order_price_max",
    "source_price",
    "best_bid",
    "best_ask",
    "source_to_ask_gap",
    "ask_depth_shares",
    "ask_depth_usdc",
    "intended_stake_usdc",
    "fill_status",
    "sim_fill_price",
    "sim_shares",
    "levels_used",
    "spent_usdc",
    "unfilled_usdc",
    "fee_model",
    "fee_rate",
    "fee_usdc",
    "total_cost_usdc",
    "would_live_fill",
    "slippage_bps",
    "btc_spot",
    "btc_momentum_bps",
    "url",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def fnum(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def bool_text(value: Any) -> str:
    if value in {True, "true", "True", "TRUE", "1", 1}:
        return "TRUE"
    if value in {False, "false", "False", "FALSE", "0", 0}:
        return "FALSE"
    return ""


def market_order_options(market: dict[str, Any] | None) -> dict[str, Any]:
    if not market:
        return {"tick_size": "0.01", "neg_risk": "", "order_price_min": 0.01, "order_price_max": 0.99}
    tick = (
        market.get("minimum_tick_size")
        or market.get("minimumTickSize")
        or market.get("orderPriceMinTickSize")
        or market.get("min_tick_size")
        or "0.01"
    )
    tick_value = fnum(tick) or 0.01
    return {
        "tick_size": str(tick),
        "neg_risk": bool_text(market.get("neg_risk", market.get("negRisk"))),
        "order_price_min": tick_value,
        "order_price_max": max(0.0, 1.0 - tick_value),
    }


def parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def source_time(row: dict[str, str]) -> datetime | None:
    for key in ("detected_time", "audit_ts", "ts", "signal_time"):
        dt = parse_dt(row.get(key))
        if dt:
            return dt.astimezone(timezone.utc)
    return None


def read_latest_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            if row.get("id"):
                rows[row["id"]] = row
    return rows


def intended_states(path: Path = ROOT / "runtime_strategy_status.csv") -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return {row.get("strategy", ""): row.get("intended_state", "") for row in csv.DictReader(file)}


def geoblock_blocked() -> tuple[str, str]:
    req = urllib.request.Request(
        "https://polymarket.com/api/geoblock",
        headers={"User-Agent": "Mozilla/5.0", "Connection": "close"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return "UNKNOWN", f"geoblock_check_unavailable:{exc}"
    blocked = data.get("blocked")
    return ("YES" if blocked is True else "NO" if blocked is False else "UNKNOWN"), ""


def intent_id(strategy: str, source_id: str) -> str:
    return f"locked_live_preflight:{strategy}:{source_id}"


def evaluate_source(strategy: str, source: dict[str, str], args: argparse.Namespace, geo_blocked: str, geo_reason: str) -> dict[str, Any]:
    config = SOURCES[strategy]
    slug = source.get("slug", "")
    outcome = source.get("outcome", "")
    stake = min(args.max_stake_usdc, fnum(source.get("stake")) or float(config["stake"]))
    source_price = fnum(source.get("source_price")) or fnum(source.get("sim_fill_price"))
    status = "BLOCKED"
    reason = "LIVE_TRADING_DISABLED"
    snapshot: dict[str, Any] = {}
    token_id = ""
    market: dict[str, Any] | None = None
    order_options = market_order_options(None)
    seen_at = source_time(source)
    source_age_sec = (datetime.now(timezone.utc) - seen_at).total_seconds() if seen_at else 999999.0

    if geo_blocked == "YES":
        reason = "GEOBLOCK_BLOCKED"
    elif source.get("status") not in {"OPEN", "MARK"} or source.get("final_result") in {"WIN", "LOSS"}:
        reason = "SOURCE_NOT_ACTIVE"
    elif source_age_sec > args.max_source_age_sec:
        reason = "SOURCE_STALE"
    elif outcome not in {"Yes", "No"}:
        reason = "BAD_OUTCOME"
    else:
        try:
            market = config["loader"](slug)  # type: ignore[index,operator]
            order_options = market_order_options(market)
            snapshot = order_snapshot(market, outcome, stake, fee_rate=float(config.get("fee_rate", 0.0))) if market else {}
            token_id = str(snapshot.get("token_id") or "")
        except Exception as exc:
            reason = f"order_book_error:{exc}"
        else:
            fill_price = fnum(snapshot.get("sim_fill_price")) or source_price
            best_ask = fnum(snapshot.get("best_ask"))
            ask_depth = fnum(snapshot.get("ask_depth_usdc"))
            would_fill = bool(snapshot.get("would_live_fill"))
            slippage_bps = ((fill_price - source_price) / source_price * 10000) if source_price > 0 else 0.0
            source_to_ask_gap = best_ask - source_price if best_ask > 0 and source_price > 0 else 999.0
            if not token_id:
                reason = "TOKEN_ID_MISSING"
            elif not would_fill:
                reason = "INSUFFICIENT_DEPTH"
            elif ask_depth < args.min_ask_depth_usdc:
                reason = "ASK_DEPTH_TOO_LOW"
            elif slippage_bps > args.max_slippage_bps:
                reason = "SLIPPAGE_TOO_HIGH"
            elif source_to_ask_gap > args.max_source_to_ask_gap:
                reason = "SOURCE_TO_ASK_GAP_TOO_WIDE"
            elif best_ask <= 0:
                reason = "NO_BEST_ASK"
            elif fill_price < fnum(order_options.get("order_price_min")) or fill_price > fnum(order_options.get("order_price_max")):
                reason = "ORDER_PRICE_OUT_OF_RANGE_FOR_TICK"
            else:
                btc_spot = 0.0
                btc_momentum = 0.0
                btc_reason = ""
                if args.btc_momentum_filter and strategy.startswith("btc_"):
                    btc_prices = btc_base.fetch_btc_spot_prices()
                    btc_spot = btc_base.append_btc_price_history(args.btc_price_history, btc_prices)
                    btc_momentum = btc_base.btc_momentum_bps(args.btc_price_history, btc_spot, args.btc_momentum_window_sec)
                    btc_reason = btc_base.btc_momentum_reject_reason(source, args, btc_spot, btc_momentum)
                if btc_reason:
                    reason = btc_reason.upper()
                elif geo_reason or geo_blocked == "UNKNOWN":
                    reason = geo_reason or "GEOBLOCK_CHECK_UNAVAILABLE"
                else:
                    status = "PREVIEW_ONLY_WOULD_PLACE"
                    reason = "LOCKED_PREVIEW_PASS"

    fill_price = fnum(snapshot.get("sim_fill_price")) or source_price
    slippage_bps = ((fill_price - source_price) / source_price * 10000) if source_price > 0 else 0.0
    best_ask = fnum(snapshot.get("best_ask"))
    source_to_ask_gap = best_ask - source_price if best_ask > 0 and source_price > 0 else 999.0
    btc_spot = locals().get("btc_spot", 0.0)
    btc_momentum = locals().get("btc_momentum", 0.0)
    return {
        "ts": now_utc(),
        "source_strategy": strategy,
        "source_id": source.get("id", ""),
        "intent_id": intent_id(strategy, source.get("id", "")),
        "status": status,
        "reason": reason,
        "live_trading_enabled": "NO",
        "geoblock_blocked": geo_blocked,
        "source_age_sec": f"{source_age_sec:.2f}",
        "wallet_name": source.get("wallet_name", ""),
        "title": source.get("title", ""),
        "slug": slug,
        "event_slug": source.get("event_slug", ""),
        "outcome": outcome,
        "token_id": token_id,
        "tick_size": order_options.get("tick_size", ""),
        "neg_risk": order_options.get("neg_risk", ""),
        "order_price_min": f"{fnum(order_options.get('order_price_min')):.6f}",
        "order_price_max": f"{fnum(order_options.get('order_price_max')):.6f}",
        "source_price": f"{source_price:.6f}",
        "best_bid": f"{fnum(snapshot.get('best_bid')):.6f}" if snapshot.get("best_bid") is not None else "",
        "best_ask": f"{fnum(snapshot.get('best_ask')):.6f}" if snapshot.get("best_ask") is not None else "",
        "source_to_ask_gap": f"{source_to_ask_gap:.6f}" if source_to_ask_gap < 999 else "",
        "ask_depth_shares": f"{fnum(snapshot.get('ask_depth_shares')):.4f}",
        "ask_depth_usdc": f"{fnum(snapshot.get('ask_depth_usdc')):.4f}",
        "intended_stake_usdc": f"{stake:.4f}",
        "fill_status": snapshot.get("fill_status", ""),
        "sim_fill_price": f"{fill_price:.6f}",
        "sim_shares": f"{fnum(snapshot.get('sim_shares')):.4f}",
        "levels_used": snapshot.get("levels_used", ""),
        "spent_usdc": f"{fnum(snapshot.get('spent_usdc')):.4f}",
        "unfilled_usdc": f"{fnum(snapshot.get('unfilled_usdc')):.4f}",
        "fee_model": config.get("fee_model", ""),
        "fee_rate": f"{fnum(snapshot.get('fee_rate')):.6f}",
        "fee_usdc": f"{fnum(snapshot.get('fee_usdc')):.6f}",
        "total_cost_usdc": f"{fnum(snapshot.get('total_cost_usdc')):.6f}",
        "would_live_fill": "YES" if snapshot.get("would_live_fill") else "NO",
        "slippage_bps": f"{slippage_bps:.2f}",
        "btc_spot": f"{fnum(btc_spot):.2f}" if fnum(btc_spot) > 0 else "",
        "btc_momentum_bps": f"{fnum(btc_momentum):.2f}",
        "url": source.get("url", ""),
    }


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDS})


def run_once(args: argparse.Namespace) -> list[dict[str, Any]]:
    geo_blocked, geo_reason = geoblock_blocked()
    states = intended_states()
    rows: list[dict[str, Any]] = []
    for strategy in args.strategy:
        if states.get(strategy, "ACTIVE") == "PAUSED":
            continue
        config = SOURCES.get(strategy)
        if not config:
            continue
        latest = read_latest_rows(config["audit"])  # type: ignore[index]
        active = [
            row
            for row in latest.values()
            if row.get("strategy") == strategy
            and row.get("status") in {"OPEN", "MARK"}
            and row.get("final_result") not in {"WIN", "LOSS"}
        ]
        active.sort(key=lambda row: row.get("detected_time") or row.get("audit_ts") or "")
        for source in active[-args.max_rows_per_strategy :]:
            rows.append(evaluate_source(strategy, source, args, geo_blocked, geo_reason))
    write_rows(args.output, rows)
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", action="append", default=list(SOURCES.keys()))
    parser.add_argument("--output", type=Path, default=ROOT / "live_order_intents.csv")
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--max-rows-per-strategy", type=int, default=50)
    parser.add_argument("--max-stake-usdc", type=float, default=30.0)
    parser.add_argument("--min-ask-depth-usdc", type=float, default=30.0)
    parser.add_argument("--max-slippage-bps", type=float, default=250.0)
    parser.add_argument("--max-source-to-ask-gap", type=float, default=0.03)
    parser.add_argument("--max-source-age-sec", type=float, default=120.0)
    parser.add_argument("--btc-momentum-filter", action="store_true")
    parser.add_argument("--btc-price-history", type=Path, default=ROOT / "btc_external_price_history.csv")
    parser.add_argument("--btc-momentum-window-sec", type=float, default=60.0)
    parser.add_argument("--btc-max-adverse-momentum-bps", type=float, default=15.0)
    parser.add_argument("--btc-threshold-buffer-bps", type=float, default=25.0)
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    while True:
        rows = run_once(args)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] live preflight intents: {len(rows)} rows", flush=True)
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
