#!/usr/bin/env python3
"""Read-only Polymarket basket-arbitrage monitor.

No orders, no keys, no wallet access. The scanner fetches public Gamma markets
and CLOB order books, then looks for markets where buying one share of every
outcome costs less than the guaranteed 1 USDC redemption value.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
USER_AGENT = "polymarket-arb-monitor/0.2"

# Polymarket fees can vary by market/category. Use --fee-rate for a strict
# override. Defaults are intentionally conservative for screening.
DEFAULT_FEE_RATES = {
    "crypto": 0.07,
    "sports": 0.03,
    "finance": 0.04,
    "politics": 0.04,
    "economics": 0.05,
    "culture": 0.05,
    "weather": 0.05,
    "mentions": 0.04,
    "tech": 0.04,
    "geopolitics": 0.0,
    "other": 0.05,
}


@dataclass(frozen=True)
class Level:
    price: float
    size: float


@dataclass(frozen=True)
class Outcome:
    name: str
    token_id: str
    ask: float | None
    ask_size: float
    bid: float | None
    bid_size: float
    ask_depth: float


@dataclass(frozen=True)
class Opportunity:
    question: str
    slug: str
    category: str
    outcomes: list[Outcome]
    gross_edge: float
    fee_estimate: float
    net_edge: float
    basket_shares: float
    best_ask_shares: float
    avg_cost_per_set: float
    total_cost: float
    total_profit: float
    url: str


class PolymarketError(RuntimeError):
    pass


def http_json(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    body: Any | None = None,
    timeout: float = 20.0,
    retries: int = 2,
) -> Any:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    data = None
    headers = {"User-Agent": USER_AGENT}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = PolymarketError(f"HTTP {exc.code} from {url}: {detail[:500]}")
        except urllib.error.URLError as exc:
            last_error = PolymarketError(f"Network error for {url}: {exc}")
        if attempt < retries:
            time.sleep(0.5 * (attempt + 1))

    raise last_error or PolymarketError(f"Request failed for {url}")


def parse_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except (TypeError, ValueError):
        return default


def fetch_markets(limit: int, offset: int) -> list[dict[str, Any]]:
    return http_json(
        "GET",
        f"{GAMMA_BASE}/markets",
        params={
            "active": "true",
            "closed": "false",
            "enableOrderBook": "true",
            "limit": limit,
            "offset": offset,
        },
    )


def collect_active_markets(sample_size: int, page_size: int) -> list[dict[str, Any]]:
    markets: list[dict[str, Any]] = []
    offset = 0
    while len(markets) < sample_size:
        batch = fetch_markets(min(page_size, sample_size - len(markets)), offset)
        if not isinstance(batch, list) or not batch:
            break
        markets.extend(batch)
        offset += len(batch)
        time.sleep(0.05)
    return markets


def fetch_books(token_ids: list[str], chunk_size: int = 100) -> dict[str, dict[str, Any]]:
    books: dict[str, dict[str, Any]] = {}
    for index in range(0, len(token_ids), chunk_size):
        chunk = token_ids[index : index + chunk_size]
        payload = [{"token_id": token_id} for token_id in chunk]
        response = http_json("POST", f"{CLOB_BASE}/books", body=payload)
        if isinstance(response, list):
            for book in response:
                asset_id = str(book.get("asset_id", ""))
                if asset_id:
                    books[asset_id] = book
        time.sleep(0.05)
    return books


def normalize_levels(book: dict[str, Any], side: str) -> list[Level]:
    raw = book.get(side)
    if not isinstance(raw, list):
        return []

    levels: dict[float, float] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        price = as_float(item.get("price"))
        size = as_float(item.get("size"), 0.0) or 0.0
        if price is None or size <= 0:
            continue
        levels[price] = levels.get(price, 0.0) + size

    reverse = side == "bids"
    return [Level(price, size) for price, size in sorted(levels.items(), reverse=reverse)]


def best_level(levels: list[Level]) -> tuple[float | None, float]:
    if not levels:
        return None, 0.0
    return levels[0].price, levels[0].size


def cumulative_breakpoints(levels: list[Level], max_qty: float) -> list[float]:
    total = 0.0
    points: list[float] = []
    for level in levels:
        total += level.size
        if total <= max_qty:
            points.append(total)
        else:
            points.append(max_qty)
            break
    return points


def fill_cost(levels: list[Level], quantity: float, fee_rate: float) -> tuple[float, float] | None:
    remaining = quantity
    cost = 0.0
    fee = 0.0
    for level in levels:
        if remaining <= 1e-9:
            break
        take = min(remaining, level.size)
        cost += take * level.price
        fee += take * fee_rate * level.price * (1.0 - level.price)
        remaining -= take
    if remaining > 1e-6:
        return None
    return cost, fee


def category_fee_rate(category: str, fees_enabled: bool, override: float | None) -> float:
    if override is not None:
        return override
    if not fees_enabled:
        return 0.0
    return DEFAULT_FEE_RATES.get(category.lower().strip(), DEFAULT_FEE_RATES["other"])


def market_url(market: dict[str, Any]) -> str:
    slug = market.get("slug")
    if slug:
        return f"https://polymarket.com/market/{slug}"
    return "https://polymarket.com/markets"


def analyze_market(
    market: dict[str, Any],
    books: dict[str, dict[str, Any]],
    min_shares: float,
    fee_rate_override: float | None,
) -> Opportunity | None:
    token_ids = [str(token_id) for token_id in parse_json_list(market.get("clobTokenIds"))]
    outcome_names = [str(name) for name in parse_json_list(market.get("outcomes"))]
    if len(token_ids) < 2 or len(token_ids) != len(outcome_names):
        return None

    ask_ladders: list[list[Level]] = []
    outcomes: list[Outcome] = []
    for name, token_id in zip(outcome_names, token_ids):
        book = books.get(token_id, {})
        asks = normalize_levels(book, "asks")
        bids = normalize_levels(book, "bids")
        ask, ask_size = best_level(asks)
        bid, bid_size = best_level(bids)
        if ask is None or not asks:
            return None
        ask_ladders.append(asks)
        outcomes.append(
            Outcome(
                name=name,
                token_id=token_id,
                ask=ask,
                ask_size=ask_size,
                bid=bid,
                bid_size=bid_size,
                ask_depth=sum(level.size for level in asks),
            )
        )

    max_qty = min(outcome.ask_depth for outcome in outcomes)
    if max_qty < min_shares:
        return None

    category = str(market.get("category") or market.get("categorySlug") or "other")
    fees_enabled = bool(market.get("feesEnabled", False))
    fee_rate = category_fee_rate(category, fees_enabled, fee_rate_override)

    breakpoints = {min_shares, max_qty}
    for ladder in ask_ladders:
        breakpoints.update(cumulative_breakpoints(ladder, max_qty))

    best: tuple[float, float, float, float, float] | None = None
    for quantity in sorted(point for point in breakpoints if point >= min_shares):
        total_cost = 0.0
        total_fee = 0.0
        for ladder in ask_ladders:
            filled = fill_cost(ladder, quantity, fee_rate)
            if filled is None:
                total_cost = math.inf
                break
            cost, fee = filled
            total_cost += cost
            total_fee += fee
        if total_cost == math.inf:
            continue

        redemption = quantity
        gross_profit = redemption - total_cost
        total_profit = gross_profit - total_fee
        avg_cost = total_cost / quantity
        gross_edge = gross_profit / quantity
        fee_per_set = total_fee / quantity
        net_edge = total_profit / quantity

        if best is None or total_profit > best[0]:
            best = (total_profit, net_edge, gross_edge, fee_per_set, avg_cost)
            best_quantity = quantity
            best_total_cost = total_cost

    if best is None:
        return None

    total_profit, net_edge, gross_edge, fee_per_set, avg_cost = best
    return Opportunity(
        question=str(market.get("question") or market.get("title") or "(untitled)"),
        slug=str(market.get("slug") or ""),
        category=category,
        outcomes=outcomes,
        gross_edge=gross_edge,
        fee_estimate=fee_per_set,
        net_edge=net_edge,
        basket_shares=best_quantity,
        best_ask_shares=min(outcome.ask_size for outcome in outcomes),
        avg_cost_per_set=avg_cost,
        total_cost=best_total_cost,
        total_profit=total_profit,
        url=market_url(market),
    )


def scan_markets(
    markets: list[dict[str, Any]],
    books: dict[str, dict[str, Any]],
    min_gross_edge: float,
    min_net_edge: float,
    min_shares: float,
    fee_rate_override: float | None,
) -> list[Opportunity]:
    opportunities: list[Opportunity] = []
    for market in markets:
        opportunity = analyze_market(market, books, min_shares, fee_rate_override)
        if opportunity is None:
            continue
        if opportunity.gross_edge < min_gross_edge:
            continue
        if opportunity.net_edge < min_net_edge:
            continue
        opportunities.append(opportunity)
    return sorted(opportunities, key=lambda item: item.total_profit, reverse=True)


def all_token_ids(markets: list[dict[str, Any]]) -> list[str]:
    token_ids: list[str] = []
    seen: set[str] = set()
    for market in markets:
        for token_id in parse_json_list(market.get("clobTokenIds")):
            token_id = str(token_id)
            if token_id not in seen:
                seen.add(token_id)
                token_ids.append(token_id)
    return token_ids


def render_table(opportunities: list[Opportunity], max_rows: int) -> str:
    if not opportunities:
        return "No basket-buy opportunities matched the thresholds."

    header = "#  net/set  gross  fees   qty      profit    avgcost  bestasks                 question"
    lines = [header, "-" * len(header)]
    for index, item in enumerate(opportunities[:max_rows], start=1):
        outcome_text = " + ".join(
            f"{outcome.name}@{outcome.ask:.3f}" for outcome in item.outcomes if outcome.ask is not None
        )
        lines.append(
            f"{index:<2} {item.net_edge:>7.4f}  "
            f"{item.gross_edge:>5.4f}  "
            f"{item.fee_estimate:>5.4f}  "
            f"{item.basket_shares:>7.1f}  "
            f"{item.total_profit:>8.3f}  "
            f"{item.avg_cost_per_set:>7.4f}  "
            f"{outcome_text[:24]:<24}  "
            f"{item.question[:78]}"
        )
        lines.append(f"   {item.url}")
    return "\n".join(lines)


def opportunity_to_json(item: Opportunity) -> dict[str, Any]:
    return {
        "question": item.question,
        "slug": item.slug,
        "category": item.category,
        "gross_edge": item.gross_edge,
        "fee_estimate": item.fee_estimate,
        "net_edge": item.net_edge,
        "basket_shares": item.basket_shares,
        "best_ask_shares": item.best_ask_shares,
        "avg_cost_per_set": item.avg_cost_per_set,
        "total_cost": item.total_cost,
        "total_profit": item.total_profit,
        "url": item.url,
        "outcomes": [
            {
                "name": outcome.name,
                "token_id": outcome.token_id,
                "ask": outcome.ask,
                "ask_size": outcome.ask_size,
                "bid": outcome.bid,
                "bid_size": outcome.bid_size,
                "ask_depth": outcome.ask_depth,
            }
            for outcome in item.outcomes
        ],
    }


def append_csv(path: Path, opportunities: list[Opportunity], scan_id: int) -> None:
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "ts",
                "scan",
                "question",
                "slug",
                "category",
                "net_edge",
                "gross_edge",
                "fee_per_set",
                "basket_shares",
                "total_profit",
                "avg_cost_per_set",
                "url",
                "outcomes",
            ],
        )
        if not exists:
            writer.writeheader()
        ts = datetime.now(timezone.utc).isoformat()
        for item in opportunities:
            writer.writerow(
                {
                    "ts": ts,
                    "scan": scan_id,
                    "question": item.question,
                    "slug": item.slug,
                    "category": item.category,
                    "net_edge": f"{item.net_edge:.8f}",
                    "gross_edge": f"{item.gross_edge:.8f}",
                    "fee_per_set": f"{item.fee_estimate:.8f}",
                    "basket_shares": f"{item.basket_shares:.4f}",
                    "total_profit": f"{item.total_profit:.8f}",
                    "avg_cost_per_set": f"{item.avg_cost_per_set:.8f}",
                    "url": item.url,
                    "outcomes": " | ".join(
                        f"{outcome.name}@{outcome.ask:.4f}" for outcome in item.outcomes if outcome.ask is not None
                    ),
                }
            )


def run_scan(args: argparse.Namespace, markets: list[dict[str, Any]]) -> list[Opportunity]:
    token_ids = all_token_ids(markets)
    books = fetch_books(token_ids, chunk_size=args.book_chunk_size)
    return scan_markets(
        markets,
        books,
        min_gross_edge=args.min_gross_edge,
        min_net_edge=args.min_net_edge,
        min_shares=args.min_shares,
        fee_rate_override=args.fee_rate,
    )


def self_test() -> None:
    market = {
        "question": "Will the demo resolve Yes?",
        "slug": "demo-market",
        "category": "Crypto",
        "feesEnabled": True,
        "outcomes": json.dumps(["Yes", "No"]),
        "clobTokenIds": json.dumps(["yes-token", "no-token"]),
    }
    books = {
        "yes-token": {
            "asks": [{"price": "0.47", "size": "20"}, {"price": "0.60", "size": "100"}],
            "bids": [{"price": "0.45", "size": "5"}],
        },
        "no-token": {
            "asks": [{"price": "0.50", "size": "15"}, {"price": "0.52", "size": "10"}],
            "bids": [{"price": "0.49", "size": "7"}],
        },
    }
    opportunities = scan_markets([market], books, 0.0, -1.0, 1.0, fee_rate_override=0.0)
    assert len(opportunities) == 1
    assert round(opportunities[0].gross_edge, 6) == 0.025
    assert opportunities[0].basket_shares == 20.0
    assert round(opportunities[0].total_profit, 6) == 0.5
    print("self-test passed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only Polymarket basket-arbitrage scanner and monitor."
    )
    parser.add_argument("--sample-size", type=int, default=300, help="active markets to inspect")
    parser.add_argument("--page-size", type=int, default=100, help="Gamma API page size")
    parser.add_argument("--book-chunk-size", type=int, default=100, help="CLOB books per request")
    parser.add_argument("--min-gross-edge", type=float, default=0.002, help="minimum edge before fees")
    parser.add_argument("--min-net-edge", type=float, default=0.001, help="minimum edge after fees")
    parser.add_argument("--min-shares", type=float, default=10.0, help="minimum complete baskets")
    parser.add_argument("--fee-rate", type=float, default=None, help="override taker fee rate, e.g. 0.04")
    parser.add_argument("--max-rows", type=int, default=20, help="rows to print")
    parser.add_argument("--json", action="store_true", help="print raw opportunity JSON")
    parser.add_argument("--csv", type=Path, default=None, help="append matching opportunities to CSV")
    parser.add_argument("--loop", action="store_true", help="run continuously")
    parser.add_argument("--interval", type=float, default=15.0, help="seconds between loop scans")
    parser.add_argument("--max-scans", type=int, default=0, help="stop after this many scans in loop mode")
    parser.add_argument("--refresh-markets-every", type=int, default=20, help="loop scans per market refresh")
    parser.add_argument("--self-test", action="store_true", help="run local calculation test")
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    if args.self_test:
        self_test()
        return 0

    markets: list[dict[str, Any]] = []
    scan_id = 0
    while True:
        scan_id += 1
        started = time.time()
        try:
            if not markets or scan_id == 1 or scan_id % args.refresh_markets_every == 0:
                markets = collect_active_markets(args.sample_size, args.page_size)
            opportunities = run_scan(args, markets)
            elapsed = time.time() - started

            if args.csv and opportunities:
                append_csv(args.csv, opportunities, scan_id)

            if args.json:
                print(json.dumps([opportunity_to_json(item) for item in opportunities], indent=2))
            else:
                stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(
                    f"[{stamp}] scan={scan_id} markets={len(markets)} "
                    f"found={len(opportunities)} elapsed={elapsed:.1f}s"
                )
                print(render_table(opportunities, args.max_rows))
        except KeyboardInterrupt:
            print("Stopped.")
            return 130
        except Exception as exc:
            print(f"scan={scan_id} error: {exc}", file=sys.stderr)

        if not args.loop:
            return 0
        if args.max_scans and scan_id >= args.max_scans:
            return 0

        sleep_for = max(0.0, args.interval - (time.time() - started))
        time.sleep(sleep_for)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
