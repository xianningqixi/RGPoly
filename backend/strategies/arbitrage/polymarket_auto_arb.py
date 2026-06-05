#!/usr/bin/env python3
"""Automated Polymarket basket-arbitrage runner.

The default mode is DRY RUN. Real-money execution requires both:

1. command-line flag: --execute
2. environment variable: POLY_EXECUTION_ENABLED=I_UNDERSTAND_REAL_MONEY_RISK

This extra gate is intentional. Sequential multi-leg execution is not atomic,
so a failed leg can leave directional exposure even when each individual order
uses FOK.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scan_polymarket_arbitrage import (
    CLOB_BASE,
    Opportunity,
    all_token_ids,
    collect_active_markets,
    fetch_books,
    opportunity_to_json,
    render_table,
    scan_markets,
)


EXECUTION_ACK = "I_UNDERSTAND_REAL_MONEY_RISK"


@dataclass(frozen=True)
class PlannedLeg:
    name: str
    token_id: str
    ask: float
    usdc_amount: float


@dataclass(frozen=True)
class ExecutionResult:
    ts: str
    mode: str
    question: str
    slug: str
    url: str
    net_edge: float
    basket_shares: float
    expected_profit: float
    status: str
    responses: list[dict[str, Any]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry-run or execute Polymarket basket-arbitrage opportunities."
    )
    parser.add_argument("--sample-size", type=int, default=500, help="active markets to inspect")
    parser.add_argument("--page-size", type=int, default=100, help="Gamma API page size")
    parser.add_argument("--book-chunk-size", type=int, default=100, help="CLOB books per request")
    parser.add_argument("--interval", type=float, default=8.0, help="seconds between scans")
    parser.add_argument("--max-scans", type=int, default=0, help="0 means run forever")
    parser.add_argument("--max-trades", type=int, default=1, help="stop after this many executions")
    parser.add_argument("--min-gross-edge", type=float, default=0.004, help="minimum edge before fees")
    parser.add_argument("--min-net-edge", type=float, default=0.003, help="minimum edge after fees")
    parser.add_argument("--min-total-profit", type=float, default=0.25, help="minimum expected USDC profit")
    parser.add_argument("--min-shares", type=float, default=10.0, help="minimum complete baskets")
    parser.add_argument("--max-usdc-per-trade", type=float, default=25.0, help="hard cap per opportunity")
    parser.add_argument("--fee-rate", type=float, default=None, help="override taker fee rate")
    parser.add_argument("--max-rows", type=int, default=5, help="candidate rows to print")
    parser.add_argument("--execute", action="store_true", help="place real FOK buy orders")
    parser.add_argument("--log", type=Path, default=Path("auto_arb_log.csv"), help="execution log path")
    parser.add_argument("--json-log", type=Path, default=Path("auto_arb_log.jsonl"), help="raw log path")
    parser.add_argument("--alert-file", type=Path, default=Path("latest_arb_alert.txt"), help="latest alert text path")
    parser.add_argument("--beep-on-opportunity", action="store_true", help="play a Windows beep when an opportunity is selected")
    parser.add_argument("--host", default=CLOB_BASE, help="Polymarket CLOB host")
    parser.add_argument("--chain-id", type=int, default=137, help="Polygon mainnet chain id")
    parser.add_argument("--fok-tick-size", default="0.01", help="tick size passed to py-clob-client-v2")
    parser.add_argument("--lang", choices=["en", "zh"], default="en", help="console output language")
    return parser


def execution_enabled(args: argparse.Namespace) -> bool:
    return args.execute and os.environ.get("POLY_EXECUTION_ENABLED") == EXECUTION_ACK


def make_client(args: argparse.Namespace) -> Any:
    try:
        from py_clob_client_v2 import ApiCreds, ClobClient
    except ImportError as exc:
        raise RuntimeError("Install dependencies first: python -m pip install -r requirements.txt") from exc

    private_key = os.environ.get("POLY_PRIVATE_KEY") or os.environ.get("PK")
    if not private_key:
        raise RuntimeError("Missing POLY_PRIVATE_KEY environment variable")
    funder = os.environ.get("POLY_PROXY_ADDRESS") or None
    signature_type_raw = os.environ.get("POLY_SIGNATURE_TYPE")
    signature_type = int(signature_type_raw) if signature_type_raw else None

    api_key = os.environ.get("POLY_API_KEY") or os.environ.get("CLOB_API_KEY")
    api_secret = os.environ.get("POLY_API_SECRET") or os.environ.get("CLOB_SECRET")
    api_passphrase = os.environ.get("POLY_API_PASSPHRASE") or os.environ.get("CLOB_PASS_PHRASE")

    if api_key and api_secret and api_passphrase:
        creds = ApiCreds(
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=api_passphrase,
        )
    else:
        client = ClobClient(
            host=args.host,
            chain_id=args.chain_id,
            key=private_key,
            signature_type=signature_type,
            funder=funder,
        )
        creds = client.create_or_derive_api_key()

    return ClobClient(
        host=args.host,
        chain_id=args.chain_id,
        key=private_key,
        creds=creds,
        signature_type=signature_type,
        funder=funder,
        retry_on_error=True,
    )


def cap_opportunity(item: Opportunity, max_usdc: float) -> tuple[float, float]:
    if item.total_cost <= max_usdc:
        return item.basket_shares, item.total_cost
    if item.avg_cost_per_set <= 0:
        return 0.0, 0.0
    capped_qty = max_usdc / item.avg_cost_per_set
    return capped_qty, max_usdc


def planned_legs(item: Opportunity, max_usdc: float) -> list[PlannedLeg]:
    quantity, _ = cap_opportunity(item, max_usdc)
    legs: list[PlannedLeg] = []
    for outcome in item.outcomes:
        if outcome.ask is None:
            continue
        legs.append(
            PlannedLeg(
                name=outcome.name,
                token_id=outcome.token_id,
                ask=outcome.ask,
                usdc_amount=round(quantity * outcome.ask, 2),
            )
        )
    # Execute the smallest dollar legs first; this reduces stranded capital if a
    # later FOK leg fails, but does not make the basket atomic.
    return sorted((leg for leg in legs if leg.usdc_amount >= 1.0), key=lambda leg: leg.usdc_amount)


def execute_fok_buys(client: Any, args: argparse.Namespace, legs: list[PlannedLeg]) -> list[dict[str, Any]]:
    from py_clob_client_v2 import MarketOrderArgs, OrderType, PartialCreateOrderOptions, Side

    responses: list[dict[str, Any]] = []
    for leg in legs:
        response = client.create_and_post_market_order(
            order_args=MarketOrderArgs(
                token_id=leg.token_id,
                amount=leg.usdc_amount,
                side=Side.BUY,
                order_type=OrderType.FOK,
            ),
            options=PartialCreateOrderOptions(tick_size=args.fok_tick_size),
            order_type=OrderType.FOK,
        )
        normalized = normalize_response(response)
        normalized["leg_name"] = leg.name
        normalized["planned_usdc_amount"] = leg.usdc_amount
        responses.append(normalized)
        if not response_looks_filled(normalized):
            break
    return responses


def normalize_response(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    try:
        return json.loads(json.dumps(response, default=lambda value: getattr(value, "__dict__", str(value))))
    except TypeError:
        return {"raw": str(response)}


def response_looks_filled(response: dict[str, Any]) -> bool:
    if response.get("success") is False:
        return False
    status = str(response.get("status") or response.get("state") or "").lower()
    if any(word in status for word in ["failed", "cancel", "reject", "error"]):
        return False
    return True


def append_execution_log(path: Path, result: ExecutionResult) -> None:
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "ts",
                "mode",
                "status",
                "question",
                "slug",
                "net_edge",
                "basket_shares",
                "expected_profit",
                "url",
            ],
        )
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "ts": result.ts,
                "mode": result.mode,
                "status": result.status,
                "question": result.question,
                "slug": result.slug,
                "net_edge": f"{result.net_edge:.8f}",
                "basket_shares": f"{result.basket_shares:.4f}",
                "expected_profit": f"{result.expected_profit:.8f}",
                "url": result.url,
            }
        )


def append_json_log(path: Path, result: ExecutionResult) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(result.__dict__, ensure_ascii=False) + "\n")


def write_alert(path: Path, result: ExecutionResult) -> None:
    text = (
        f"ARBITRAGE ALERT\n"
        f"time: {result.ts}\n"
        f"mode: {result.mode}\n"
        f"status: {result.status}\n"
        f"expected_profit: {result.expected_profit:.6f} USDC\n"
        f"net_edge: {result.net_edge:.6f} USDC per basket\n"
        f"basket_shares: {result.basket_shares:.4f}\n"
        f"market: {result.question}\n"
        f"url: {result.url}\n"
    )
    path.write_text(text, encoding="utf-8")


def beep() -> None:
    try:
        import winsound

        for _ in range(3):
            winsound.Beep(1200, 250)
            time.sleep(0.08)
    except Exception:
        print("\a\a\a", end="", flush=True)


def latest_opportunities(args: argparse.Namespace, markets: list[dict[str, Any]]) -> list[Opportunity]:
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


def choose_trade(args: argparse.Namespace, candidates: list[Opportunity]) -> Opportunity | None:
    for item in candidates:
        quantity, _ = cap_opportunity(item, args.max_usdc_per_trade)
        expected_profit = item.net_edge * quantity
        if expected_profit >= args.min_total_profit:
            return item
    return None


def result_from_item(
    args: argparse.Namespace,
    item: Opportunity,
    mode: str,
    status: str,
    responses: list[dict[str, Any]],
) -> ExecutionResult:
    quantity, _ = cap_opportunity(item, args.max_usdc_per_trade)
    return ExecutionResult(
        ts=datetime.now(timezone.utc).isoformat(),
        mode=mode,
        question=item.question,
        slug=item.slug,
        url=item.url,
        net_edge=item.net_edge,
        basket_shares=quantity,
        expected_profit=item.net_edge * quantity,
        status=status,
        responses=responses,
    )


def zh_summary(candidates: list[Opportunity], max_rows: int) -> str:
    if not candidates:
        return "当前没有发现满足安全阈值的套利机会，继续等待。"

    lines = ["发现候选套利机会："]
    for index, item in enumerate(candidates[:max_rows], start=1):
        outcomes = " + ".join(
            f"{outcome.name}@{outcome.ask:.3f}" for outcome in item.outcomes if outcome.ask is not None
        )
        lines.append(
            f"{index}. 每套净利 {item.net_edge:.4f} U，数量 {item.basket_shares:.1f} 套，"
            f"预计总利润 {item.total_profit:.4f} U，平均成本 {item.avg_cost_per_set:.4f}"
        )
        lines.append(f"   市场：{item.question}")
        lines.append(f"   价格：{outcomes}")
        lines.append(f"   链接：{item.url}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    live = execution_enabled(args)
    if args.execute and not live:
        print(
            "Execution flag was set, but POLY_EXECUTION_ENABLED is not the required acknowledgement. "
            "Running in dry-run mode.",
            file=sys.stderr,
        )

    client = make_client(args) if live else None
    markets: list[dict[str, Any]] = []
    trades = 0
    scan_id = 0

    while True:
        scan_id += 1
        started = time.time()
        try:
            if not markets or scan_id % 20 == 1:
                markets = collect_active_markets(args.sample_size, args.page_size)

            candidates = latest_opportunities(args, markets)
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if args.lang == "zh":
                mode_text = "实盘" if live else "模拟盘"
                print(f"[{stamp}] 第 {scan_id} 次扫描 | 模式：{mode_text} | 候选机会：{len(candidates)} 个")
                print(zh_summary(candidates, args.max_rows))
            else:
                print(f"[{stamp}] scan={scan_id} mode={'LIVE' if live else 'DRY'} candidates={len(candidates)}")
                print(render_table(candidates, args.max_rows))

            item = choose_trade(args, candidates)
            if item is not None:
                # Refresh the market immediately before action. This is the key
                # stale-quote guard for both dry-run and live modes.
                fresh = latest_opportunities(args, [market for market in markets if market.get("slug") == item.slug])
                item = choose_trade(args, fresh) if fresh else None

            if item is not None:
                legs = planned_legs(item, args.max_usdc_per_trade)
                if len(legs) != len(item.outcomes):
                    result = result_from_item(args, item, "LIVE" if live else "DRY", "SKIP_MIN_LEG_AMOUNT", [])
                elif live:
                    responses = execute_fok_buys(client, args, legs)
                    status = "EXECUTED" if len(responses) == len(legs) and all(response_looks_filled(r) for r in responses) else "PARTIAL_OR_FAILED"
                    result = result_from_item(args, item, "LIVE", status, responses)
                    trades += 1
                else:
                    responses = [{"leg": leg.__dict__, "dry_run": True} for leg in legs]
                    result = result_from_item(args, item, "DRY", "WOULD_EXECUTE", responses)
                    trades += 1

                append_execution_log(args.log, result)
                append_json_log(args.json_log, result)
                write_alert(args.alert_file, result)
                if args.beep_on_opportunity:
                    beep()
                if args.lang == "zh":
                    status_map = {
                        "WOULD_EXECUTE": "模拟盘：如果是实盘会执行",
                        "EXECUTED": "实盘：已尝试执行",
                        "PARTIAL_OR_FAILED": "实盘：部分成交或失败",
                        "SKIP_MIN_LEG_AMOUNT": "跳过：单条腿金额低于最小下单额",
                    }
                    print(
                        f"{status_map.get(result.status, result.status)}：{result.question} | "
                        f"预计利润 {result.expected_profit:.4f} U | {result.url}"
                    )
                else:
                    print(f"{result.status}: {result.question} expected_profit={result.expected_profit:.4f} {result.url}")

        except KeyboardInterrupt:
            print("Stopped.")
            return 130
        except Exception as exc:
            print(f"scan={scan_id} error: {exc}", file=sys.stderr)

        if args.max_trades and trades >= args.max_trades:
            return 0
        if args.max_scans and scan_id >= args.max_scans:
            return 0

        sleep_for = max(0.0, args.interval - (time.time() - started))
        time.sleep(sleep_for)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
