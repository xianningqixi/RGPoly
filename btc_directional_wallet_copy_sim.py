#!/usr/bin/env python3
"""Simulate copy-following BTC directional/price-level Polymarket wallets.

This is separate from short-window Up/Down copy trading. It watches wallets that
trade markets such as Bitcoin reach/dip/above/below a price level.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from portfolio_risk import portfolio_open_exposure
from trade_audit import ensure_audit_open, order_snapshot, signal_time_from_epoch, update_audit_marks


WATCH_WALLETS = {
    "creamcream_btc_directional": "0x6e1d5040d0ac73709b0621f620d2a60b80d2d0fa",
}

CHANGE_POINTS = Path("strategy_change_points.csv")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def fnum(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def parse_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def latest_strategy_cutoff(strategy: str) -> datetime | None:
    if not CHANGE_POINTS.exists():
        return None
    latest: datetime | None = None
    with CHANGE_POINTS.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            if row.get("strategy") != strategy:
                continue
            ts = parse_ts(row.get("cutoff_ts"))
            if ts and (latest is None or ts > latest):
                latest = ts
    return latest


def http_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Connection": "close"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            time.sleep(0.4 * (attempt + 1))
    raise last_error or RuntimeError(f"request failed: {url}")


def fetch_btc_spot_prices() -> dict[str, float]:
    prices: dict[str, float] = {}
    endpoints = {
        "binance": "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT",
        "coinbase": "https://api.coinbase.com/v2/prices/BTC-USD/spot",
        "okx": "https://www.okx.com/api/v5/market/ticker?instId=BTC-USDT",
    }
    for source, url in endpoints.items():
        try:
            data = http_json(url)
            if source == "binance":
                price = fnum(data.get("price"))
            elif source == "coinbase":
                price = fnum((data.get("data") or {}).get("amount"))
            else:
                rows = data.get("data") or []
                price = fnum((rows[0] if rows else {}).get("last"))
            if price > 0:
                prices[source] = price
        except Exception:
            continue
    return prices


def append_btc_price_history(path: Path, prices: dict[str, float]) -> float:
    valid = [value for value in prices.values() if value > 0]
    consensus = sum(valid) / len(valid) if valid else 0.0
    exists = path.exists()
    fields = ["ts", "consensus", "binance", "coinbase", "okx", "source_count"]
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "ts": now_utc(),
                "consensus": f"{consensus:.2f}" if consensus else "",
                "binance": f"{prices.get('binance', 0.0):.2f}" if prices.get("binance") else "",
                "coinbase": f"{prices.get('coinbase', 0.0):.2f}" if prices.get("coinbase") else "",
                "okx": f"{prices.get('okx', 0.0):.2f}" if prices.get("okx") else "",
                "source_count": len(valid),
            }
        )
    return consensus


def btc_momentum_bps(path: Path, current_price: float, window_sec: float) -> float:
    if current_price <= 0 or not path.exists():
        return 0.0
    cutoff = time.time() - max(1.0, window_sec)
    baseline = 0.0
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                ts = parse_ts(row.get("ts"))
                price = fnum(row.get("consensus"))
                if not ts or price <= 0:
                    continue
                if ts.timestamp() >= cutoff:
                    baseline = price
                    break
                baseline = price
    except Exception:
        return 0.0
    if baseline <= 0:
        return 0.0
    return (current_price - baseline) / baseline * 10000


def title_price_levels(title: str) -> list[float]:
    levels = []
    for match in re.findall(r"\$?\s*([0-9]{2,3}(?:,[0-9]{3})+(?:\.\d+)?|[0-9]{4,6}(?:\.\d+)?)", title):
        value = fnum(match.replace(",", ""))
        if value >= 1000:
            levels.append(value)
    return levels


def btc_momentum_reject_reason(row: dict[str, Any], args: argparse.Namespace, spot: float, momentum_bps: float) -> str:
    if spot <= 0:
        return ""
    outcome = str(row.get("outcome") or "")
    if outcome not in {"Yes", "No"}:
        return ""
    text = f"{row.get('title', '')} {row.get('slug', '')}".lower()
    levels = title_price_levels(text)
    buffer = args.btc_threshold_buffer_bps / 10000
    adverse = args.btc_max_adverse_momentum_bps

    if len(levels) >= 2 and ("between" in text or "range" in text):
        low, high = min(levels[:2]), max(levels[:2])
        inside = (low * (1 - buffer)) <= spot <= (high * (1 + buffer))
        if outcome == "No" and inside:
            return "btc_spot_inside_range_against_no"
        if outcome == "Yes" and not inside:
            return "btc_spot_outside_range_against_yes"
    elif levels:
        level = levels[0]
        is_above = any(word in text for word in ("above", "over", "greater"))
        is_below = any(word in text for word in ("below", "under", "less than"))
        if outcome == "No" and is_above and spot >= level * (1 - buffer):
            return "btc_spot_near_above_threshold_against_no"
        if outcome == "No" and is_below and spot <= level * (1 + buffer):
            return "btc_spot_near_below_threshold_against_no"
        if outcome == "Yes" and is_above and spot < level * (1 - buffer):
            return "btc_spot_below_threshold_against_yes"
        if outcome == "Yes" and is_below and spot > level * (1 + buffer):
            return "btc_spot_above_threshold_against_yes"

    if outcome == "No" and momentum_bps >= adverse:
        return "btc_up_momentum_against_no"
    if outcome == "Yes" and momentum_bps <= -adverse:
        return "btc_down_momentum_against_yes"
    return ""


def fetch_recent(wallet: str, limit: int) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"user": wallet, "limit": limit, "offset": 0})
    data = http_json(f"https://data-api.polymarket.com/activity?{query}")
    return data if isinstance(data, list) else []


def market_by_slug(slug: str) -> dict[str, Any] | None:
    if not slug:
        return None
    query = urllib.parse.urlencode({"slug": slug})
    data = http_json(f"https://gamma-api.polymarket.com/markets?{query}")
    if isinstance(data, list) and data:
        return data[0]
    data = http_json(f"https://gamma-api.polymarket.com/events?{query}")
    if isinstance(data, list) and data:
        markets = data[0].get("markets") or []
        for market in markets:
            if market.get("slug") == slug:
                return market
    parts = slug.split("-")
    for idx in range(len(parts) - 1, 4, -1):
        event_slug = "-".join(parts[:idx])
        query = urllib.parse.urlencode({"slug": event_slug})
        data = http_json(f"https://gamma-api.polymarket.com/events?{query}")
        if not (isinstance(data, list) and data):
            continue
        for market in data[0].get("markets") or []:
            if market.get("slug") == slug:
                return market
    return None


def latest_price(slug: str, outcome: str) -> float | None:
    market = market_by_slug(slug)
    if not market:
        return None
    try:
        outcomes = json.loads(market.get("outcomes") or "[]")
        prices = json.loads(market.get("outcomePrices") or "[]")
    except json.JSONDecodeError:
        return None
    for name, price in zip(outcomes, prices):
        if str(name).lower() == outcome.lower():
            return fnum(price)
    return None


def market_end_time(market: dict[str, Any] | None) -> datetime | None:
    if not market:
        return None
    for key in ("endDate", "endDateIso", "end_date", "endTime"):
        dt = parse_ts(market.get(key))
        if dt:
            return dt
    return None


def is_asset_directional(row: dict[str, Any], args: argparse.Namespace) -> bool:
    text = f"{row.get('title', '')} {row.get('slug', '')} {row.get('eventSlug', '')}".lower()
    asset_keywords = [str(item).lower() for item in (getattr(args, "asset_keyword", None) or ["bitcoin", "btc"])]
    short_keywords = [str(item).lower() for item in (getattr(args, "short_window_keyword", None) or ["up or down", "updown"])]
    if any(keyword and keyword in text for keyword in short_keywords):
        return False
    if not any(keyword and keyword in text for keyword in asset_keywords):
        return False
    markers = [
        "reach",
        "dip",
        "above",
        "below",
        "price of",
        " be ",
        "$",
    ]
    return any(marker in text for marker in markers)


def source_id(wallet_name: str, row: dict[str, Any]) -> str:
    tx = row.get("tx") or row.get("transactionHash") or ""
    return ":".join(
        [
            wallet_name,
            str(tx),
            str(row.get("slug") or ""),
            str(row.get("side") or ""),
            str(row.get("outcome") or ""),
            str(row.get("timestamp") or ""),
            str(row.get("usdcSize") or row.get("size") or ""),
        ]
    )


def read_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data if isinstance(data, list) else [])
    except Exception:
        return set()


def write_seen(path: Path, seen: set[str]) -> None:
    path.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")


def load_candidate_wallets(
    path: Path,
    limit: int,
    recommendations: set[str] | None = None,
    min_score: float = 0.0,
    min_trades: int = 0,
) -> dict[str, str]:
    if not path.exists() or limit <= 0:
        return {}
    recommendations = recommendations or {"OBSERVE_HIGH", "OBSERVE_SMALL"}
    wallets: dict[str, str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            recommendation = row.get("recommendation")
            action = row.get("action")
            if recommendation is not None and recommendation not in recommendations:
                continue
            if action is not None and action not in {"PROMOTE_CANDIDATE", "KEEP_OBSERVING", "ADD_TO_OBSERVATION"}:
                continue
            if fnum(row.get("score")) < min_score:
                continue
            if int(fnum(row.get("seed_trade_count"))) < min_trades:
                continue
            wallet = str(row.get("wallet") or "").strip().lower()
            if not wallet:
                continue
            alias = re.sub(r"[^A-Za-z0-9_]+", "_", str(row.get("alias") or wallet[:10])).strip("_") or wallet[:10]
            if not alias.startswith("candidate_"):
                alias = f"candidate_{alias[:32]}"
            suffix = 2
            base_alias = alias
            while alias in wallets:
                alias = f"{base_alias}_{suffix}"
                suffix += 1
            wallets[alias] = wallet
            if len(wallets) >= limit:
                break
    return wallets


def parse_watch_wallets(args: argparse.Namespace) -> dict[str, str]:
    if args.watch_wallet:
        wallets: dict[str, str] = {}
        for item in args.watch_wallet:
            if "=" in item:
                alias, wallet = item.split("=", 1)
            else:
                wallet = item
                alias = wallet[:10]
            alias = re.sub(r"[^A-Za-z0-9_]+", "_", alias).strip("_") or wallet[:10]
            wallets[alias] = wallet.lower()
        return wallets
    candidates = load_candidate_wallets(
        args.wallet_candidates,
        args.candidate_limit,
        set(args.candidate_recommendation or []),
        args.min_candidate_score,
        args.min_candidate_trades,
    )
    if candidates:
        return candidates
    if args.candidate_limit <= 0:
        return dict(WATCH_WALLETS)
    if not args.allow_default_wallets:
        return {}
    return candidates or dict(WATCH_WALLETS)


def read_latest_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            rows[row["id"]] = row
    return rows


def append_row(path: Path, row: dict[str, Any]) -> None:
    fields = [
        "ts",
        "id",
        "wallet_name",
        "source_ts",
        "side",
        "outcome",
        "source_price",
        "source_usdc",
        "sim_entry_price",
        "stake",
        "shares",
        "title",
        "slug",
        "event_slug",
        "status",
        "result",
        "current_price",
        "pnl",
        "url",
    ]
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in fields})


def append_reject(args: argparse.Namespace, wallet_name: str, row: dict[str, Any], reason: str, extra: dict[str, Any] | None = None) -> None:
    path = args.reject_log
    fields = [
        "ts",
        "wallet_name",
        "id",
        "reason",
        "slug",
        "title",
        "outcome",
        "source_price",
        "source_usdc",
        "signal_age_sec",
        "best_ask",
        "ask_depth_usdc",
        "slippage_bps",
        "source_to_ask_gap",
    ]
    exists = path.exists()
    data = extra or {}
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "ts": now_utc(),
                "wallet_name": wallet_name,
                "id": source_id(wallet_name, row),
                "reason": reason,
                "slug": row.get("slug") or "",
                "title": row.get("title") or "",
                "outcome": row.get("outcome") or "",
                "source_price": f"{fnum(row.get('price')):.6f}",
                "source_usdc": f"{fnum(row.get('usdcSize')):.4f}",
                "signal_age_sec": f"{time.time() - fnum(row.get('timestamp')):.2f}",
                "best_ask": data.get("best_ask", ""),
                "ask_depth_usdc": data.get("ask_depth_usdc", ""),
                "slippage_bps": data.get("slippage_bps", ""),
                "source_to_ask_gap": data.get("source_to_ask_gap", ""),
            }
        )


def append_exit_signal(args: argparse.Namespace, wallet_name: str, row: dict[str, Any]) -> None:
    path = args.exit_signal_log
    fields = [
        "ts",
        "wallet_name",
        "id",
        "side",
        "slug",
        "title",
        "outcome",
        "source_price",
        "source_usdc",
        "signal_age_sec",
        "url",
    ]
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "ts": now_utc(),
                "wallet_name": wallet_name,
                "id": source_id(wallet_name, row),
                "side": row.get("side") or "",
                "slug": row.get("slug") or "",
                "title": row.get("title") or "",
                "outcome": row.get("outcome") or "",
                "source_price": f"{fnum(row.get('price')):.6f}",
                "source_usdc": f"{fnum(row.get('usdcSize')):.4f}",
                "signal_age_sec": f"{time.time() - fnum(row.get('timestamp')):.2f}",
                "url": row.get("url") or "",
            }
        )


def opposite_outcome(outcome: str) -> str:
    return "Yes" if outcome == "No" else "No" if outcome == "Yes" else ""


def read_hedge_signal_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            signal_id = row.get("hedge_signal_id") or ""
            if signal_id:
                ids.add(signal_id)
    return ids


def matching_open_positions(args: argparse.Namespace, wallet_name: str, row: dict[str, Any]) -> list[dict[str, str]]:
    slug = str(row.get("slug") or "")
    hedge_outcome = str(row.get("outcome") or "")
    held_outcome = opposite_outcome(hedge_outcome)
    if not slug or not held_outcome:
        return []
    rows = read_latest_rows(args.audit_log)
    matched = []
    for item in rows.values():
        if item.get("wallet_name") != wallet_name:
            continue
        if item.get("slug") != slug:
            continue
        if item.get("outcome") != held_outcome:
            continue
        if item.get("final_result") in {"WIN", "LOSS"}:
            continue
        if item.get("status") not in {"OPEN", "MARK", "FINAL", ""}:
            continue
        matched.append(item)
    return matched


def append_hedge_exit_signals(args: argparse.Namespace, wallet_name: str, row: dict[str, Any]) -> int:
    path = args.hedge_signal_log
    positions = matching_open_positions(args, wallet_name, row)
    if not positions:
        return 0
    seen = read_hedge_signal_ids(path)
    market = market_by_slug(str(row.get("slug") or ""))
    fields = [
        "ts",
        "hedge_signal_id",
        "position_id",
        "strategy",
        "wallet_name",
        "signal_side",
        "signal_outcome",
        "held_outcome",
        "slug",
        "title",
        "source_price",
        "source_usdc",
        "signal_age_sec",
        "held_entry_price",
        "held_shares",
        "held_stake",
        "held_total_cost_usdc",
        "exit_price",
        "exit_price_source",
        "exit_pnl_usdc",
        "exit_roi_pct",
        "final_result",
        "final_pnl_usdc",
        "delta_vs_final_usdc",
        "decision",
        "url",
    ]
    exists = path.exists()
    written = 0
    with path.open("a", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        if not exists:
            writer.writeheader()
            exists = True
        for pos in positions:
            hedge_signal_id = f"{source_id(wallet_name, row)}::{pos.get('id', '')}"
            if hedge_signal_id in seen:
                continue
            held_outcome = pos.get("outcome") or ""
            try:
                snapshot = order_snapshot(market, held_outcome, fnum(pos.get("stake"))) if market else {}
            except Exception:
                snapshot = {}
            exit_price = fnum(snapshot.get("best_bid"))
            exit_price_source = "best_bid"
            if exit_price <= 0:
                latest = latest_price(pos.get("slug", ""), held_outcome)
                exit_price = latest or 0.0
                exit_price_source = "latest_price" if exit_price > 0 else ""
            held_shares = fnum(pos.get("sim_shares"))
            held_stake = fnum(pos.get("stake"))
            held_total_cost = fnum(pos.get("total_cost_usdc")) or held_stake
            exit_pnl = held_shares * exit_price - held_total_cost if exit_price > 0 and held_shares > 0 else 0.0
            exit_roi = exit_pnl / held_total_cost * 100 if held_total_cost > 0 else 0.0
            final_pnl = fnum(pos.get("fee_adjusted_final_pnl") or pos.get("slippage_final_pnl"))
            delta = exit_pnl - final_pnl if pos.get("final_result") in {"WIN", "LOSS"} else 0.0
            writer.writerow(
                {
                    "ts": now_utc(),
                    "hedge_signal_id": hedge_signal_id,
                    "position_id": pos.get("id", ""),
                    "strategy": args.strategy_key,
                    "wallet_name": wallet_name,
                    "signal_side": row.get("side") or "",
                    "signal_outcome": row.get("outcome") or "",
                    "held_outcome": held_outcome,
                    "slug": row.get("slug") or "",
                    "title": row.get("title") or "",
                    "source_price": f"{fnum(row.get('price')):.6f}",
                    "source_usdc": f"{fnum(row.get('usdcSize')):.4f}",
                    "signal_age_sec": f"{time.time() - fnum(row.get('timestamp')):.2f}",
                    "held_entry_price": pos.get("sim_fill_price") or pos.get("source_price") or "",
                    "held_shares": f"{held_shares:.6f}",
                    "held_stake": f"{held_stake:.4f}",
                    "held_total_cost_usdc": f"{held_total_cost:.6f}",
                    "exit_price": f"{exit_price:.6f}" if exit_price > 0 else "",
                    "exit_price_source": exit_price_source,
                    "exit_pnl_usdc": f"{exit_pnl:.6f}" if exit_price > 0 else "",
                    "exit_roi_pct": f"{exit_roi:.4f}" if exit_price > 0 else "",
                    "final_result": pos.get("final_result") or "",
                    "final_pnl_usdc": f"{final_pnl:.6f}" if pos.get("final_result") in {"WIN", "LOSS"} else "",
                    "delta_vs_final_usdc": f"{delta:.6f}" if pos.get("final_result") in {"WIN", "LOSS"} else "",
                    "decision": "EXIT_OR_HEDGE_SIGNAL",
                    "url": f"https://polymarket.com/event/{row.get('eventSlug') or ''}",
                }
            )
            written += 1
    return written


def should_copy_reason(row: dict[str, Any], args: argparse.Namespace) -> str:
    if row.get("type") != "TRADE":
        return "not_trade"
    if row.get("side") != "BUY":
        return "not_buy"
    outcome = str(row.get("outcome") or "")
    if outcome not in {"Yes", "No"}:
        return "bad_outcome"
    if args.allowed_outcome and outcome not in args.allowed_outcome:
        return "outcome_not_allowed"
    if not is_asset_directional(row, args):
        return "not_btc_directional"
    slug = str(row.get("slug") or "")
    title = str(row.get("title") or "")
    market_text = f"{slug} {title}".lower()
    for keyword in args.block_market_keyword:
        if keyword.lower() and keyword.lower() in market_text:
            return "blocked_market_type"
    signal_age = time.time() - fnum(row.get("timestamp"))
    if signal_age < 0 or signal_age > args.max_source_age_sec:
        return "source_too_old"
    price = fnum(row.get("price"))
    usdc = fnum(row.get("usdcSize"))
    max_price = args.yes_max_price if outcome == "Yes" else args.max_price
    if not (args.min_price <= price <= max_price):
        return "source_price_out_of_range"
    if usdc < args.min_source_usdc:
        return "source_size_too_small"
    return "TAKE"


def should_copy(row: dict[str, Any], args: argparse.Namespace) -> bool:
    return should_copy_reason(row, args) == "TAKE"


PERMANENT_SEEN_REASONS = {
    "not_trade",
    "not_buy",
    "bad_outcome",
    "not_btc_directional",
    "blocked_market_type",
    "source_too_old",
}


def outcome_stake(outcome: str, args: argparse.Namespace) -> float:
    if outcome == "Yes" and args.yes_stake_usdc is not None:
        return max(0.0, args.yes_stake_usdc)
    return max(0.0, args.stake_usdc)


def outcome_max_slippage_bps(outcome: str, args: argparse.Namespace) -> float:
    if outcome == "Yes" and args.yes_max_slippage_bps is not None:
        return args.yes_max_slippage_bps
    return args.max_slippage_bps


def outcome_max_source_to_ask_gap(outcome: str, args: argparse.Namespace) -> float:
    if outcome == "Yes" and args.yes_max_source_to_ask_gap is not None:
        return args.yes_max_source_to_ask_gap
    return args.max_source_to_ask_gap


def outcome_min_ask_depth_usdc(outcome: str, args: argparse.Namespace) -> float:
    if outcome == "Yes" and args.yes_min_ask_depth_usdc is not None:
        return args.yes_min_ask_depth_usdc
    return args.min_ask_depth_usdc


def market_exposure(
    log_path: Path,
    slug: str,
    wallet_name: str,
    outcome: str,
    cutoff: datetime | None,
) -> tuple[float, int]:
    rows = read_latest_rows(log_path)
    market_stake = 0.0
    wallet_market_count = 0
    for row in rows.values():
        if row.get("slug") != slug:
            continue
        if row.get("status") not in {"OPEN", "MARK"}:
            continue
        row_ts = parse_ts(row.get("ts"))
        if cutoff and row_ts and row_ts < cutoff:
            continue
        market_stake += fnum(row.get("stake"))
        if row.get("wallet_name") == wallet_name and row.get("outcome") == outcome:
            wallet_market_count += 1
    return market_stake, wallet_market_count


def open_exposure(log_path: Path, cutoff: datetime | None) -> tuple[int, float]:
    rows = read_latest_rows(log_path)
    open_count = 0
    open_stake = 0.0
    for row in rows.values():
        if row.get("status") not in {"OPEN", "MARK"}:
            continue
        row_ts = parse_ts(row.get("ts"))
        if cutoff and row_ts and row_ts < cutoff:
            continue
        open_count += 1
        open_stake += fnum(row.get("stake"))
    return open_count, open_stake


def open_copy(wallet_name: str, row: dict[str, Any], args: argparse.Namespace) -> bool:
    cutoff = latest_strategy_cutoff(args.strategy_key)
    open_count, open_stake = open_exposure(args.log, cutoff)
    portfolio_count, portfolio_stake = portfolio_open_exposure([args.audit_log]) if args.isolated_portfolio_risk else portfolio_open_exposure()
    if portfolio_stake >= args.bankroll_usdc:
        append_reject(args, wallet_name, row, "portfolio_bankroll_full")
        print(
            f"跳过BTC方向信号：模拟仓总本金已满 {portfolio_stake:.2f}U/{args.bankroll_usdc:.2f}U "
            f"({portfolio_count}笔未结算) | {wallet_name} | {row.get('title')}",
            flush=True,
        )
        return False
    if open_stake >= args.bankroll_usdc:
        append_reject(args, wallet_name, row, "bankroll_exposure_full")
        print(f"跳过BTC方向信号：模拟本金已满 {open_stake:.2f}U/{args.bankroll_usdc:.2f}U | {wallet_name} | {row.get('title')}", flush=True)
        return False
    if open_count >= args.max_open_positions:
        append_reject(args, wallet_name, row, "open_position_cap_full")
        print(f"跳过BTC方向信号：全局未结算仓位已满 {open_count}笔/{open_stake:.2f}U | {wallet_name} | {row.get('title')}", flush=True)
        return False
    source_price = fnum(row.get("price"))
    slug = str(row.get("slug") or "")
    outcome = str(row.get("outcome") or "")
    market_stake, wallet_market_count = market_exposure(args.log, slug, wallet_name, outcome, cutoff)
    if market_stake >= args.max_market_stake_usdc:
        append_reject(args, wallet_name, row, "market_exposure_full", {"source_to_ask_gap": "", "slippage_bps": ""})
        print(f"跳过BTC方向信号：单市场模拟暴露已满 {market_stake:.2f}U | {wallet_name} | {row.get('title')}", flush=True)
        return False
    if wallet_market_count >= args.max_wallet_market_entries:
        append_reject(args, wallet_name, row, "wallet_market_entries_full")
        print(f"跳过BTC方向信号：同钱包同市场重复过多 {wallet_market_count}次 | {wallet_name} | {row.get('title')}", flush=True)
        return False
    market = market_by_slug(slug)
    end_time = market_end_time(market)
    if end_time:
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)
        hours_to_end = (end_time.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds() / 3600
        if hours_to_end < args.min_hours_to_end:
            append_reject(args, wallet_name, row, "market_too_close_to_end")
            print(f"跳过BTC方向信号：市场距离结算过近 {hours_to_end:.1f}h | {wallet_name} | {row.get('title')}", flush=True)
            return False
        if args.max_hours_to_end > 0 and hours_to_end > args.max_hours_to_end:
            append_reject(args, wallet_name, row, "market_too_far_to_end")
            print(f"跳过BTC方向信号：市场距离结算过远 {hours_to_end:.1f}h | {wallet_name} | {row.get('title')}", flush=True)
            return False
    stake = min(
        outcome_stake(outcome, args),
        max(0.0, args.bankroll_usdc - portfolio_stake),
        max(0.0, args.bankroll_usdc - open_stake),
        max(0.0, args.max_market_stake_usdc - market_stake),
    )
    if stake <= 0:
        return False
    try:
        snapshot = order_snapshot(market, outcome, stake) if market else {}
    except Exception:
        snapshot = {}
    fill_price = fnum(snapshot.get("sim_fill_price")) or source_price
    best_ask = fnum(snapshot.get("best_ask"))
    ask_depth_usdc = fnum(snapshot.get("ask_depth_usdc"))
    would_live_fill = bool(snapshot.get("would_live_fill"))
    slippage_bps = ((fill_price - source_price) / source_price * 10000) if source_price > 0 else 0.0
    source_to_ask_gap = best_ask - source_price if best_ask > 0 and source_price > 0 else 999.0
    reject_extra = {
        "best_ask": f"{best_ask:.6f}",
        "ask_depth_usdc": f"{ask_depth_usdc:.4f}",
        "slippage_bps": f"{slippage_bps:.2f}",
        "source_to_ask_gap": f"{source_to_ask_gap:.6f}",
    }
    if args.require_live_fill and not would_live_fill:
        append_reject(args, wallet_name, row, "insufficient_book_depth", reject_extra)
        print(f"跳过BTC方向信号：盘口深度不足 | {wallet_name} | {row.get('title')}", flush=True)
        return False
    min_ask_depth_usdc = outcome_min_ask_depth_usdc(outcome, args)
    max_slippage_bps = outcome_max_slippage_bps(outcome, args)
    max_source_to_ask_gap = outcome_max_source_to_ask_gap(outcome, args)
    if ask_depth_usdc < min_ask_depth_usdc:
        append_reject(args, wallet_name, row, "ask_depth_too_low", reject_extra)
        print(f"跳过BTC方向信号：ask深度不足 {ask_depth_usdc:.2f}U | {wallet_name} | {row.get('title')}", flush=True)
        return False
    if slippage_bps > max_slippage_bps:
        append_reject(args, wallet_name, row, "slippage_too_high", reject_extra)
        print(f"跳过BTC方向信号：滑点过高 {slippage_bps:.0f}bps | {wallet_name} | {row.get('title')}", flush=True)
        return False
    if source_to_ask_gap > max_source_to_ask_gap:
        append_reject(args, wallet_name, row, "source_to_ask_gap_too_wide", reject_extra)
        print(f"跳过BTC方向信号：源价到ask差距 {source_to_ask_gap:.3f} | {wallet_name} | {row.get('title')}", flush=True)
        return False

    if args.btc_momentum_filter:
        btc_prices = fetch_btc_spot_prices()
        btc_spot = append_btc_price_history(args.btc_price_history, btc_prices)
        btc_momentum = btc_momentum_bps(args.btc_price_history, btc_spot, args.btc_momentum_window_sec)
        reason = btc_momentum_reject_reason(row, args, btc_spot, btc_momentum)
        if reason:
            append_reject(args, wallet_name, row, reason, reject_extra)
            print(
                f"Skip BTC signal by external momentum filter: {reason} "
                f"spot={btc_spot:.2f} momentum={btc_momentum:.2f}bps | {wallet_name} | {row.get('title')}",
                flush=True,
            )
            return False

    shares = fnum(snapshot.get("sim_shares")) or (stake / fill_price if fill_price > 0 else 0.0)
    trade_id = source_id(wallet_name, row)
    event_slug = str(row.get("eventSlug") or "")
    ensure_audit_open(
        args.audit_log,
        trade_id=trade_id,
        strategy=args.strategy_key,
        wallet_name=wallet_name,
        signal_time=signal_time_from_epoch(row.get("timestamp")),
        title=str(row.get("title") or ""),
        slug=slug,
        event_slug=event_slug,
        outcome=outcome,
        stake=stake,
        source_price=source_price,
        market=market,
        extra={
            "best_bid": snapshot.get("best_bid"),
            "best_ask": snapshot.get("best_ask"),
            "ask_depth_shares": snapshot.get("ask_depth_shares"),
            "ask_depth_usdc": snapshot.get("ask_depth_usdc"),
            "sim_fill_price": fill_price,
            "sim_shares": shares,
            "would_live_fill": would_live_fill,
            "slippage_bps": slippage_bps,
            "ev": "",
            "price_bucket": "",
            "recommended_stake": f"{stake:.4f}",
        },
    )
    append_row(
        args.log,
        {
            "ts": now_utc(),
            "id": trade_id,
            "wallet_name": wallet_name,
            "source_ts": row.get("timestamp"),
            "side": row.get("side"),
            "outcome": outcome,
            "source_price": f"{source_price:.6f}",
            "source_usdc": row.get("usdcSize"),
            "sim_entry_price": f"{fill_price:.6f}",
            "stake": f"{stake:.4f}",
            "shares": f"{shares:.4f}",
            "title": row.get("title"),
            "slug": slug,
            "event_slug": event_slug,
            "status": "OPEN",
            "url": f"https://polymarket.com/event/{event_slug}",
        },
    )
    args.alert_file.write_text(
        (
            "BTC DIRECTIONAL COPY SIM\n"
            f"time: {now_utc()}\n"
            f"wallet: {wallet_name}\n"
            f"outcome: {outcome}\n"
            f"entry_price: {fill_price:.4f}\n"
            f"source_price: {source_price:.4f}\n"
            f"slippage_bps: {slippage_bps:.0f}\n"
            f"stake: {stake:.2f}U\n"
            f"market: {row.get('title')}\n"
            f"url: https://polymarket.com/event/{event_slug}\n"
        ),
        encoding="utf-8",
    )
    print(f"BTC方向跟单模拟：{wallet_name} BUY {outcome} {stake:.2f}U @ {fill_price:.3f} | {row.get('title')}", flush=True)
    return True


def mark_open(args: argparse.Namespace) -> None:
    rows = read_latest_rows(args.log)
    for row in rows.values():
        if row.get("status") != "OPEN":
            continue
        current = latest_price(row["slug"], row["outcome"])
        if current is None:
            continue
        stake = fnum(row.get("stake"))
        shares = fnum(row.get("shares"))
        pnl = shares * current - stake
        append_row(
            args.log,
            {
                **row,
                "ts": now_utc(),
                "status": "MARK",
                "result": "MARK",
                "current_price": f"{current:.6f}",
                "pnl": f"{pnl:.4f}",
            },
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=float, default=45.0)
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--stake-usdc", type=float, default=2.0)
    parser.add_argument("--bankroll-usdc", type=float, default=1000.0)
    parser.add_argument("--yes-stake-usdc", type=float, default=None)
    parser.add_argument("--min-source-usdc", type=float, default=10.0)
    parser.add_argument("--min-price", type=float, default=0.03)
    parser.add_argument("--max-price", type=float, default=0.98)
    parser.add_argument("--yes-max-price", type=float, default=0.65)
    parser.add_argument("--max-slippage-bps", type=float, default=500.0)
    parser.add_argument("--yes-max-slippage-bps", type=float, default=None)
    parser.add_argument("--min-ask-depth-usdc", type=float, default=20.0)
    parser.add_argument("--yes-min-ask-depth-usdc", type=float, default=None)
    parser.add_argument("--max-source-to-ask-gap", type=float, default=0.05)
    parser.add_argument("--yes-max-source-to-ask-gap", type=float, default=None)
    parser.add_argument("--max-source-age-sec", type=float, default=30.0)
    parser.add_argument("--min-hours-to-end", type=float, default=0.0)
    parser.add_argument("--max-hours-to-end", type=float, default=0.0, help="0 disables max end-time filter")
    parser.add_argument("--max-market-stake-usdc", type=float, default=8.0)
    parser.add_argument("--max-wallet-market-entries", type=int, default=1)
    parser.add_argument("--max-open-positions", type=int, default=100)
    parser.add_argument("--allowed-outcome", action="append", default=[])
    parser.add_argument("--block-market-keyword", action="append", default=[])
    parser.add_argument("--require-live-fill", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--log", type=Path, default=Path("btc_directional_wallet_copy_sim.csv"))
    parser.add_argument("--audit-log", type=Path, default=Path("btc_directional_trade_audit.csv"))
    parser.add_argument("--reject-log", type=Path, default=Path("btc_directional_rejects.csv"))
    parser.add_argument("--exit-signal-log", type=Path, default=Path("btc_directional_exit_signals.csv"))
    parser.add_argument("--hedge-signal-log", type=Path, default=Path("btc_directional_hedge_exit_signals.csv"))
    parser.add_argument("--btc-momentum-filter", action="store_true")
    parser.add_argument("--btc-price-history", type=Path, default=Path("btc_external_price_history.csv"))
    parser.add_argument("--btc-momentum-window-sec", type=float, default=60.0)
    parser.add_argument("--btc-max-adverse-momentum-bps", type=float, default=15.0)
    parser.add_argument("--btc-threshold-buffer-bps", type=float, default=25.0)
    parser.add_argument("--seen", type=Path, default=Path("btc_directional_seen.json"))
    parser.add_argument("--alert-file", type=Path, default=Path("latest_btc_directional_copy_alert.txt"))
    parser.add_argument("--live-only", action="store_true")
    parser.add_argument("--max-audit-updates", type=int, default=50)
    parser.add_argument("--watch-wallet", action="append", default=[], help="Wallet to watch as alias=0x...")
    parser.add_argument("--wallet-candidates", type=Path, default=Path("btc_directional_wallet_candidates.csv"))
    parser.add_argument("--candidate-limit", type=int, default=0, help="Load top N OBSERVE candidates from wallet-candidates")
    parser.add_argument("--candidate-recommendation", action="append", default=[], help="Allowed candidate recommendation")
    parser.add_argument("--min-candidate-score", type=float, default=0.0)
    parser.add_argument("--min-candidate-trades", type=int, default=0)
    parser.add_argument("--reload-wallets-each-scan", action="store_true", help="Reload wallet-candidates before each scan")
    parser.add_argument("--strategy-key", default="btc_directional_copy")
    parser.add_argument("--asset-name", default="BTC")
    parser.add_argument("--asset-keyword", action="append", default=[])
    parser.add_argument("--short-window-keyword", action="append", default=[])
    parser.add_argument("--allow-default-wallets", action="store_true")
    parser.add_argument("--once", action="store_true", help="Run one scan loop and exit.")
    parser.add_argument("--isolated-portfolio-risk", action="store_true", help="Use only this audit log for bankroll exposure checks.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.allowed_outcome = set(args.allowed_outcome or [])
    args.block_market_keyword = list(args.block_market_keyword or [])
    if not args.asset_keyword:
        args.asset_keyword = ["bitcoin", "btc"]
    if not args.short_window_keyword:
        args.short_window_keyword = ["up or down", "updown"]
    if not args.candidate_recommendation:
        args.candidate_recommendation = ["OBSERVE_HIGH", "OBSERVE_SMALL"]
    seen = read_seen(args.seen)
    initialized = bool(seen)
    watch_wallets = parse_watch_wallets(args)
    while True:
        try:
            if args.reload_wallets_each_scan and not args.watch_wallet:
                updated_wallets = parse_watch_wallets(args)
                if updated_wallets:
                    watch_wallets = updated_wallets
            copied = read_latest_rows(args.log)
            fresh_seen = set(seen)
            opened = 0
            for name, wallet in watch_wallets.items():
                rows = fetch_recent(wallet, args.limit)
                for row in reversed(rows):
                    sid = source_id(name, row)
                    if sid in copied or sid in seen:
                        continue
                    if args.live_only and not initialized:
                        fresh_seen.add(sid)
                        continue
                    if row.get("type") == "TRADE" and row.get("side") == "SELL" and is_asset_directional(row, args):
                        append_exit_signal(args, name, row)
                        fresh_seen.add(sid)
                        continue
                    if (
                        row.get("type") == "TRADE"
                        and row.get("side") == "BUY"
                        and str(row.get("outcome") or "") not in args.allowed_outcome
                        and is_asset_directional(row, args)
                    ):
                        if append_hedge_exit_signals(args, name, row):
                            fresh_seen.add(sid)
                            continue
                    reason = should_copy_reason(row, args)
                    if reason != "TAKE":
                        if reason not in {"not_trade", "not_buy", "bad_outcome", "not_btc_directional"}:
                            append_reject(args, name, row, reason)
                        if reason in PERMANENT_SEEN_REASONS:
                            fresh_seen.add(sid)
                        continue
                    if open_copy(name, row, args):
                        copied[sid] = row
                        fresh_seen.add(sid)
                        opened += 1
                time.sleep(0.15)
            seen = fresh_seen
            write_seen(args.seen, seen)
            initialized = True
            mark_open(args)
            update_audit_marks(args.audit_log, market_by_slug, max_rows=args.max_audit_updates)
            if args.once:
                return 0
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] BTC方向跟单扫描 | 新开仓 {opened} 条", flush=True)
        except KeyboardInterrupt:
            return 130
        except Exception as exc:
            print(f"BTC方向跟单错误：{exc}", flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
