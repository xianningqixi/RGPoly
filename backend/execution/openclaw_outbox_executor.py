#!/usr/bin/env python3
"""
openclaw_outbox_executor.py — Consume execution_outbox.jsonl and place real FOK orders.
NEW wallet config: uses PRIVATE_KEY env var + POLY_PROXY_ADDRESS + POLY_API creds.

Usage:
  python openclaw_outbox_executor.py --dry-run       # Preview only
  python openclaw_outbox_executor.py --execute       # Place orders
  python openclaw_outbox_executor.py --execute --max-trades 3  # Limit
"""

from __future__ import annotations
import argparse, csv, json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import urllib.request

from py_clob_client_v2 import (
    ClobClient, ApiCreds, BalanceAllowanceParams,
    MarketOrderArgs, OrderType, PartialCreateOrderOptions, Side,
)
from py_clob_client_v2.clob_types import AssetType
from eth_account import Account

ROOT = Path.cwd()
CLOB_BASE = "https://clob.polymarket.com"
EXECUTION_ACK = "I_UNDERSTAND_REAL_MONEY_RISK"
EXECUTION_ENV = "POLY_CLOB_EXECUTION_ENABLED"
RECEIPT_FIELDS = [
    "receipt_ts", "ticket_id", "intent_id", "source_strategy",
    "execution_status", "actual_order_id", "actual_fill_price",
    "actual_shares", "actual_spent_usdc", "actual_fee_usdc", "notes",
]


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def get_ask_price(token_id: str) -> float | None:
    """Get best ask from CLOB book via public endpoint."""
    url = f"https://clob.polymarket.com/book?token_id={token_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "openclaw-executor/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            book = json.loads(r.read().decode())
        if book and book.get("asks"):
            return float(book["asks"][0]["price"])
        return None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def market_open(token_id: str) -> bool:
    """Check if market has an order book."""
    return get_ask_price(token_id) is not None


def load_config() -> dict:
    """Load wallet config from env vars only.

    Do not hardcode API credentials in this file. Migration packages and skills
    may include this executor, so credentials must come from the operator's
    local environment.
    """
    config = {
        "private_key": os.environ.get("PRIVATE_KEY", ""),
        "api_key": os.environ.get("POLY_API_KEY", ""),
        "api_secret": os.environ.get("POLY_API_SECRET", ""),
        "api_passphrase": os.environ.get("POLY_API_PASSPHRASE", ""),
        "funder": os.environ.get("POLY_PROXY_ADDRESS", ""),
        "signature_type": int(os.environ.get("POLY_SIGNATURE_TYPE", "3")),
    }

    return config


def make_client(config: dict) -> ClobClient:
    """Create authenticated ClobClient."""
    pk = config["private_key"]
    acct = Account.from_key(pk)
    log(f"Signer: {acct.address}")

    creds = ApiCreds(
        api_key=config["api_key"],
        api_secret=config["api_secret"],
        api_passphrase=config["api_passphrase"],
    )

    return ClobClient(
        host=CLOB_BASE, chain_id=137, key=pk,
        creds=creds,
        signature_type=config["signature_type"],
        funder=config["funder"],
    )


def check_balance(client: ClobClient, config: dict) -> float:
    """Check CLOB USDC balance."""
    bal = client.get_balance_allowance(
        BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, signature_type=config["signature_type"])
    )
    return float(bal["balance"]) / 1e6


def read_outbox(path: Path) -> list[dict]:
    """Read execution_outbox.jsonl."""
    tickets = []
    if not path.exists():
        log(f"[!] {path} not found")
        return tickets
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                t = obj.get("ticket", obj)
                tickets.append(t)
            except json.JSONDecodeError:
                pass
    return tickets


def deduplicate(tickets: list[dict]) -> list[dict]:
    """Deduplicate by token_id (keep latest)."""
    seen = {}
    for t in tickets:
        key = (t.get("token_id", ""), t.get("intended_stake_usdc", ""))
        seen[key] = t
    return list(seen.values())


def place_fok(client: ClobClient, token_id: str, amount: float, tick_size: str) -> dict:
    """Place FOK market buy order."""
    response = client.create_and_post_market_order(
        order_args=MarketOrderArgs(
            token_id=token_id,
            amount=amount,
            side=Side.BUY,
            order_type=OrderType.FOK,
        ),
        options=PartialCreateOrderOptions(tick_size=tick_size),
        order_type=OrderType.FOK,
    )
    return response if isinstance(response, dict) else {}


def extract_result(response: dict) -> dict:
    """Parse response into standard result fields."""
    ok = response.get("success") is True and response.get("status") == "matched"
    return {
        "ok": ok,
        "order_id": response.get("orderID", ""),
        "status": response.get("status", ""),
        "price": response.get("makingAmount", ""),
        "shares": response.get("takingAmount", ""),
        "tx_hash": (response.get("transactionsHashes") or [""])[0],
        "error_msg": response.get("errorMsg", ""),
    }


def load_receipts(path: Path) -> set[str]:
    """Set of already-processed ticket_ids."""
    if not path.exists():
        return set()
    ids = set()
    with path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tid = row.get("ticket_id", "").strip()
            if tid:
                ids.add(tid)
    return ids


def write_receipt(path: Path, receipt: dict) -> None:
    """Append one receipt row."""
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RECEIPT_FIELDS)
        if not exists:
            w.writeheader()
        w.writerow({k: receipt.get(k, "") for k in RECEIPT_FIELDS})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outbox", type=Path, default=ROOT / "execution_outbox.jsonl")
    parser.add_argument("--receipts", type=Path, default=ROOT / "external_execution_receipts.csv")
    parser.add_argument("--dry-run", action="store_true", help="Preview only; this is the default")
    parser.add_argument("--execute", action="store_true", help="Place real orders")
    parser.add_argument("--max-trades", type=int, default=0, help="Max trades (0=all)")
    parser.add_argument("--max-usdc", type=float, default=30.0, help="Max total USDC to spend")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between trades")
    parser.add_argument("--dedupe", action="store_true", default=True)
    args = parser.parse_args()

    live = args.execute
    mode = "LIVE" if live else "DRY"
    if live and os.environ.get(EXECUTION_ENV) != EXECUTION_ACK:
        log(f"[!] Refusing live execution. Set {EXECUTION_ENV}={EXECUTION_ACK} to acknowledge real-money risk.")
        return 1

    # Load config + client
    config = load_config()
    if not config["private_key"]:
        log("[!] No PRIVATE_KEY found. Set PRIVATE_KEY in the environment.")
        return 1
    missing = [name for name, key in [
        ("POLY_API_KEY", "api_key"),
        ("POLY_API_SECRET", "api_secret"),
        ("POLY_API_PASSPHRASE", "api_passphrase"),
        ("POLY_PROXY_ADDRESS", "funder"),
    ] if not config.get(key)]
    if missing:
        log("[!] Missing env vars: " + ", ".join(missing))
        return 1

    client = make_client(config) if live else None

    # Check balance
    if live:
        balance = check_balance(client, config)
        log(f"CLOB USDC: {balance:.2f}")
        if balance < 1:
            log("[!] Balance too low")
            return 1
    else:
        balance = 999.0

    # Read + dedup outbox
    tickets = read_outbox(args.outbox)
    if args.dedupe:
        tickets = deduplicate(tickets)
    log(f"Tickets: {len(tickets)} unique")

    # Load existing receipts
    seen = load_receipts(args.receipts)
    if seen:
        log(f"Skipping {len(seen)} already-processed tickets")

    total_spent = 0.0
    done = 0
    failed = 0

    for idx, t in enumerate(tickets, 1):
        ticket_id = t.get("ticket_id", "")
        if ticket_id in seen:
            continue

        if args.max_trades > 0 and done >= args.max_trades:
            break
        if live and total_spent >= args.max_usdc:
            log(f"Max USDC reached ({args.max_usdc})")
            break

        token_id = t.get("token_id", "")
        if not token_id or token_id == "0":
            continue

        stake = float(t.get("intended_stake_usdc", "10"))
        tsize = t.get("tick_size", "0.01")
        title = t.get("title", "?")
        outcome = t.get("outcome", "?")
        intent_id = t.get("intent_id", "")
        strategy = t.get("source_strategy", "")

        # Check market open
        ask = get_ask_price(token_id)
        if ask is None:
            log(f"[{idx}/{len(tickets)}] SKIP (closed): {ticket_id[:20]}...")
            write_receipt(args.receipts, {
                "receipt_ts": datetime.now(timezone.utc).isoformat(),
                "ticket_id": ticket_id, "intent_id": intent_id,
                "source_strategy": strategy, "execution_status": "MARKET_CLOSED",
                "actual_order_id": "", "actual_fill_price": "", "actual_shares": "",
                "actual_spent_usdc": "", "actual_fee_usdc": "",
                "notes": f"Market has no order book",
            })
            seen.add(ticket_id)
            continue

        log(f"[{idx}/{len(tickets)}] {title[:40]:40s} | {outcome:6s} | "
            f"{stake:.1f}U @ {ask:.4f}")

        if not live:
            # Dry-run
            done += 1
            write_receipt(args.receipts, {
                "receipt_ts": datetime.now(timezone.utc).isoformat(),
                "ticket_id": ticket_id, "intent_id": intent_id,
                "source_strategy": strategy, "execution_status": "DRY_RUN",
                "actual_order_id": "", "actual_fill_price": str(ask),
                "actual_shares": "", "actual_spent_usdc": str(stake),
                "actual_fee_usdc": "", "notes": f"Would FOK buy {stake}U",
            })
            seen.add(ticket_id)
            continue

        # LIVE execution
        try:
            response = place_fok(client, token_id, stake, tsize)
            result = extract_result(response)

            if result["ok"]:
                total_spent += stake
                done += 1
                log(f"  [OK] order={result['order_id'][:20]}... "
                    f"tx={result['tx_hash'][:20]}...")

                write_receipt(args.receipts, {
                    "receipt_ts": datetime.now(timezone.utc).isoformat(),
                    "ticket_id": ticket_id, "intent_id": intent_id,
                    "source_strategy": strategy, "execution_status": "EXECUTED",
                    "actual_order_id": result["order_id"],
                    "actual_fill_price": result["price"],
                    "actual_shares": result["shares"],
                    "actual_spent_usdc": str(stake),
                    "actual_fee_usdc": "",
                    "notes": f"Tx: {result['tx_hash']}",
                })
            else:
                failed += 1
                log(f"  [FAIL] {result['error_msg'] or result['status']}")
                write_receipt(args.receipts, {
                    "receipt_ts": datetime.now(timezone.utc).isoformat(),
                    "ticket_id": ticket_id, "intent_id": intent_id,
                    "source_strategy": strategy, "execution_status": "FAILED",
                    "actual_order_id": "",
                    "actual_fill_price": "", "actual_shares": "",
                    "actual_spent_usdc": "", "actual_fee_usdc": "",
                    "notes": json.dumps(response)[:200],
                })

        except Exception as e:
            failed += 1
            log(f"  [EXCEPTION] {e}")
            write_receipt(args.receipts, {
                "receipt_ts": datetime.now(timezone.utc).isoformat(),
                "ticket_id": ticket_id, "intent_id": intent_id,
                "source_strategy": strategy, "execution_status": "EXCEPTION",
                "actual_order_id": "", "actual_fill_price": "",
                "actual_shares": "", "actual_spent_usdc": "",
                "actual_fee_usdc": "",
                "notes": str(e)[:200],
            })

        seen.add(ticket_id)
        if live:
            time.sleep(args.delay)

    log(f"[{mode}] Done. {done} executed, {failed} failed, "
        f"spent: {total_spent:.2f}U (balance: {balance:.2f}U)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
