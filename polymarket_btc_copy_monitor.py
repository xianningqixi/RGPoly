#!/usr/bin/env python3
"""
polymarket_btc_copy_monitor.py — Monitor & auto-execute BTC No-dominant wallet copy.

Runs via cron every 30-60 minutes:
1. Check open positions via CLOB API
2. Read outbox for unexecuted BTC-only tickets
3. If < 10 positions, execute pending tickets (10U each)
4. Log everything to monitor_log.csv

Requirements: PRIVATE_KEY, POLY_API_KEY, POLY_API_SECRET, POLY_API_PASSPHRASE,
              POLY_PROXY_ADDRESS, POLY_SIGNATURE_TYPE env vars.
"""

import csv, json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import urllib.request

from py_clob_client_v2 import (
    ClobClient, ApiCreds, BalanceAllowanceParams,
    MarketOrderArgs, OrderType, PartialCreateOrderOptions, Side,
)
from py_clob_client_v2.clob_types import AssetType

# --- CONFIG ---
ROOT = Path(__file__).resolve().parent
OUTBOX = ROOT / "execution_outbox.jsonl"
RECEIPTS = ROOT / "external_execution_receipts.csv"
MONITOR_LOG = ROOT / "btc_copy_monitor_log.csv"
CLOB_URL = "https://clob.polymarket.com"
EXECUTION_ACK = "I_UNDERSTAND_REAL_MONEY_RISK"
EXECUTION_ENV = "POLY_BTC_COPY_MONITOR_ENABLED"
MAX_POSITIONS = 10
TRADE_AMOUNT = 10.0
ALLOWED_STRATEGIES = ["btc_no_dominant_candidate_copy"]
DELAY_BETWEEN_TRADES = 1.5

MONITOR_FIELDS = [
    "ts", "action", "open_positions", "balance", "tickets_pending",
    "tickets_executed", "spent", "details",
]


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def load_config() -> dict:
    return {
        "private_key": os.environ.get("PRIVATE_KEY", ""),
        "api_key": os.environ.get("POLY_API_KEY", ""),
        "api_secret": os.environ.get("POLY_API_SECRET", ""),
        "api_passphrase": os.environ.get("POLY_API_PASSPHRASE", ""),
        "funder": os.environ.get("POLY_PROXY_ADDRESS", ""),
        "signature_type": int(os.environ.get("POLY_SIGNATURE_TYPE", "3")),
    }


def make_client(config: dict) -> ClobClient:
    creds = ApiCreds(
        api_key=config["api_key"],
        api_secret=config["api_secret"],
        api_passphrase=config["api_passphrase"],
    )
    return ClobClient(
        host=CLOB_URL, chain_id=137, key=config["private_key"],
        creds=creds,
        signature_type=config["signature_type"],
        funder=config["funder"],
    )


def get_balance(client: ClobClient, config: dict) -> float:
    bal = client.get_balance_allowance(
        BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, signature_type=config["signature_type"])
    )
    return float(bal["balance"]) / 1e6


def get_open_positions(client: ClobClient) -> list[dict]:
    """Get open positions from CLOB via get_trades."""
    trades = client.get_trades()
    by_asset: dict[str, dict[str, float]] = {}
    for t in trades:
        asset_id = t.get("asset_id", "")
        side = t.get("side", "")
        size = float(t.get("size", 0))
        if not asset_id:
            continue
        if asset_id not in by_asset:
            by_asset[asset_id] = {"bought": 0.0, "spent": 0.0}
        if side == "BUY":
            by_asset[asset_id]["bought"] += size
            by_asset[asset_id]["spent"] += size * float(t.get("price", 0))
        else:
            by_asset[asset_id]["bought"] -= size

    open_pos = []
    for asset_id, data in by_asset.items():
        net = data["bought"]
        if net > 0.5:
            open_pos.append({"asset_id": asset_id, "shares": round(net, 2), "spent": round(data["spent"], 2)})
    return open_pos


def check_market_open(token_id: str) -> float | None:
    """Check if market has an order book, return best ask."""
    url = f"{CLOB_URL}/book?token_id={token_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "polymarket-monitor/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            book = json.loads(r.read().decode())
        if book and book.get("asks"):
            return float(book["asks"][0]["price"])
        return None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def load_executed_set() -> set[str]:
    """Load executed ticket_ids from receipts."""
    if not RECEIPTS.exists():
        return set()
    s = set()
    with RECEIPTS.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tid = row.get("ticket_id", "").strip()
            if tid:
                s.add(tid)
    return s


def read_pending_tickets(executed: set[str]) -> list[dict]:
    """Read outbox for pending, BTC-only, non-executed tickets."""
    if not OUTBOX.exists():
        return []
    pending = []
    with OUTBOX.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = obj.get("ticket", obj)
            tid = t.get("ticket_id", "")
            if tid in executed:
                continue
            strategy = t.get("source_strategy", "")
            if strategy not in ALLOWED_STRATEGIES:
                continue
            token_id = t.get("token_id", "")
            if not token_id or token_id == "0":
                continue
            pending.append(t)

    # Dedup by token_id (keep last)
    seen: dict[str, dict] = {}
    for t in pending:
        seen[t.get("token_id", "")] = t
    return list(seen.values())


def place_order(client: ClobClient, token_id: str, ts: str) -> dict | None:
    """Place 10U FOK order. Return result dict or None on failure."""
    try:
        response = client.create_and_post_market_order(
            order_args=MarketOrderArgs(
                token_id=token_id, amount=TRADE_AMOUNT,
                side=Side.BUY, order_type=OrderType.FOK,
            ),
            options=PartialCreateOrderOptions(tick_size=ts),
            order_type=OrderType.FOK,
        )
        if isinstance(response, dict):
            ok = response.get("success") is True and response.get("status") == "matched"
            return {
                "ok": ok, "order_id": response.get("orderID", ""),
                "price": response.get("makingAmount", ""),
                "shares": response.get("takingAmount", ""),
                "tx_hash": (response.get("transactionsHashes") or [""])[0],
                "error": response.get("errorMsg", ""),
            }
        return None
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def write_receipt(ticket: dict, result: dict) -> None:
    """Append to receipts CSV."""
    exists = RECEIPTS.exists()
    with RECEIPTS.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["receipt_ts", "ticket_id", "intent_id", "source_strategy",
                        "execution_status", "actual_order_id", "actual_fill_price",
                        "actual_shares", "actual_spent_usdc", "notes"])
        w.writerow([
            datetime.now(timezone.utc).isoformat(),
            ticket.get("ticket_id", ""),
            ticket.get("source_id", ticket.get("intent_id", "")),
            ticket.get("source_strategy", ""),
            "EXECUTED" if result.get("ok") else ("FAILED" if result.get("error") else "PARTIAL"),
            result.get("order_id", ""),
            result.get("price", ""),
            result.get("shares", ""),
            str(TRADE_AMOUNT),
            f"Tx: {result.get('tx_hash', '')}" if result.get("ok") else result.get("error", ""),
        ])


def log_monitor(entry: dict) -> None:
    """Append to monitor log."""
    exists = MONITOR_LOG.exists()
    with MONITOR_LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MONITOR_FIELDS)
        if not exists:
            w.writeheader()
        w.writerow({k: entry.get(k, "") for k in MONITOR_FIELDS})


def main() -> int:
    if os.environ.get(EXECUTION_ENV) != EXECUTION_ACK:
        log(f"[!] Refusing live execution. Set {EXECUTION_ENV}={EXECUTION_ACK} to acknowledge real-money risk.")
        return 1

    config = load_config()
    if not config["private_key"]:
        log("[!] No PRIVATE_KEY. Set env vars.")
        return 1
    if not all([config["api_key"], config["api_secret"], config["api_passphrase"],
                 config["funder"]]):
        log("[!] Missing API creds or funder.")
        return 1

    client = make_client(config)

    # Step 1: Check balance
    try:
        balance = get_balance(client, config)
    except Exception as e:
        log(f"[!] Balance check failed: {e}")
        return 1
    log(f"Balance: {balance:.2f} USDC")

    # Step 2: Check open positions via API
    try:
        open_pos = get_open_positions(client)
    except Exception as e:
        log(f"[!] Positions check failed: {e}")
        return 1

    n_pos = len(open_pos)
    log(f"Open positions: {n_pos}/{MAX_POSITIONS}")

    # Step 3: Read pending tickets
    executed_set = load_executed_set()
    pending = read_pending_tickets(executed_set)
    log(f"Pending BTC tickets: {len(pending)}")

    details = f"balance={balance:.1f}, positions={n_pos}"
    entries = []

    if n_pos >= MAX_POSITIONS:
        log(f"Max positions reached. Skipping.")
        log_monitor({
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": "SKIP_MAX",
            "open_positions": str(n_pos),
            "balance": f"{balance:.2f}",
            "tickets_pending": str(len(pending)),
            "tickets_executed": "0",
            "spent": "0",
            "details": f"At max {MAX_POSITIONS} positions",
        })
        return 0

    # Step 4: Check each pending ticket and execute
    slots = MAX_POSITIONS - n_pos
    capacity = min(slots, int(balance // TRADE_AMOUNT))
    to_execute = pending[:capacity]

    if not to_execute:
        log("No tickets to execute (insufficient slots or balance).")
        log_monitor({
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": "NO_TICKETS",
            "open_positions": str(n_pos),
            "balance": f"{balance:.2f}",
            "tickets_pending": str(len(pending)),
            "tickets_executed": "0",
            "spent": "0",
            "details": f"slots={slots}, can_afford={int(balance//TRADE_AMOUNT)}",
        })
        return 0

    executed_count = 0
    total_spent = 0.0

    for idx, ticket in enumerate(to_execute, 1):
        token_id = ticket.get("token_id", "")
        title = ticket.get("title", "?")[:50]
        outcome = ticket.get("outcome", "?")
        ts = ticket.get("tick_size", "0.01")
        candidate = ticket.get("source_id", "").split(":")[0] if ticket.get("source_id") else "?"

        # Verify market is open
        ask = check_market_open(token_id)
        if ask is None:
            log(f"  [{idx}/{len(to_execute)}] SKIP (closed): {title[:40]}")
            continue

        log(f"  [{idx}/{len(to_execute)}] {title[:40]:40s} | {outcome} | {TRADE_AMOUNT}U @ {ask:.4f} | {candidate[:20]}")

        # Place order
        result = place_order(client, token_id, ts)

        if result and result.get("ok"):
            total_spent += TRADE_AMOUNT
            executed_count += 1
            write_receipt(ticket, result)
            log(f"    [OK] order={result['order_id'][:20]}... tx={result['tx_hash'][:20]}...")
        else:
            err = result.get("error", "unknown") if result else "no response"
            log(f"    [FAIL] {err[:80]}")
            write_receipt(ticket, {
                "ok": False,
                "error": err,
                "order_id": "", "price": "", "shares": "", "tx_hash": "",
            })

        time.sleep(DELAY_BETWEEN_TRADES)

    log(f"Done. Executed: {executed_count}, spent: {total_spent:.1f}U")
    log_monitor({
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": "EXECUTED",
        "open_positions": str(n_pos),
        "balance": f"{balance:.2f}",
        "tickets_pending": str(len(pending)),
        "tickets_executed": str(executed_count),
        "spent": f"{total_spent:.1f}",
        "details": details,
    })

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
