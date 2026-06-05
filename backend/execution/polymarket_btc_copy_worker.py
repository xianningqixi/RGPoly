#!/usr/bin/env python3
"""
polymarket_btc_copy_worker.py — Execute BTC No-dominant copy tickets ONLY.

Rules:
1. Read tickets from execution_outbox.csv (primary) or .jsonl (fallback)
2. Only execute: status=READY_FOR_MANUAL_OR_EXTERNAL_EXECUTION
3. Only execute: source_strategy=btc_no_dominant_candidate_copy
4. Only execute: intended_stake_usdc ~= 10U (8-11 range)
5. Skip: ETH, BNB, Weather, btc_directional_live_shadow, btc_directional_copy
6. Skip: already executed tickets (from receipts)
7. Skip: old tickets (market closed/expired)
8. Write results to external_execution_receipts.csv
9. If CSV empty AND no JSONL tickets available -> do nothing
10. No strategy scanning, no audit file reading

Env vars required: PRIVATE_KEY, POLY_API_KEY, POLY_API_SECRET,
                   POLY_API_PASSPHRASE, POLY_PROXY_ADDRESS, POLY_SIGNATURE_TYPE
"""

import csv, json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

from py_clob_client_v2 import (
    ClobClient, ApiCreds, BalanceAllowanceParams,
    MarketOrderArgs, OrderType, PartialCreateOrderOptions, Side,
)
from py_clob_client_v2.clob_types import AssetType

# === CONFIG ===
ROOT = Path.cwd()
OUTBOX_CSV = ROOT / "execution_outbox.csv"
OUTBOX_JSONL = ROOT / "execution_outbox.jsonl"
RECEIPTS = ROOT / "external_execution_receipts.csv"
CLOB_URL = "https://clob.polymarket.com"
EXECUTION_ACK = "I_UNDERSTAND_REAL_MONEY_RISK"
EXECUTION_ENV = "POLY_BTC_COPY_WORKER_ENABLED"
MAX_POSITIONS = 30
TRADE_AMOUNT = 10.0
STAKE_MIN = 8.0
STAKE_MAX = 11.0
ALLOWED_STRATEGY = "btc_no_dominant_candidate_copy"
FRESH_WINDOW_SECONDS = 300  # only execute tickets exported within last 5 min
DELAY = 1.5

RECEIPT_FIELDS = [
    "receipt_ts", "ticket_id", "intent_id", "source_strategy",
    "execution_status", "actual_order_id", "actual_fill_price",
    "actual_shares", "actual_spent_usdc", "actual_fee_usdc", "notes",
]


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def load_config():
    return {
        "private_key": os.environ.get("PRIVATE_KEY", ""),
        "api_key": os.environ.get("POLY_API_KEY", ""),
        "api_secret": os.environ.get("POLY_API_SECRET", ""),
        "api_passphrase": os.environ.get("POLY_API_PASSPHRASE", ""),
        "funder": os.environ.get("POLY_PROXY_ADDRESS", ""),
        "sig_type": int(os.environ.get("POLY_SIGNATURE_TYPE", "3")),
    }


def make_client(cfg):
    creds = ApiCreds(
        api_key=cfg["api_key"],
        api_secret=cfg["api_secret"],
        api_passphrase=cfg["api_passphrase"],
    )
    return ClobClient(
        host=CLOB_URL, chain_id=137, key=cfg["private_key"],
        creds=creds, signature_type=cfg["sig_type"], funder=cfg["funder"],
    )


def get_balance(client, cfg):
    bal = client.get_balance_allowance(
        BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, signature_type=cfg["sig_type"])
    )
    return float(bal["balance"]) / 1e6


def get_open_positions(client):
    """Get open positions via API trades. Returns (count, set_of_token_ids)."""
    trades = client.get_trades()
    by_asset = {}
    for t in trades:
        aid = t.get("asset_id", "")
        side = t.get("side", "")
        size = float(t.get("size", 0))
        if not aid:
            continue
        if aid not in by_asset:
            by_asset[aid] = 0.0
        by_asset[aid] += size if side == "BUY" else -size
    
    held = {aid for aid, net in by_asset.items() if net > 0.5}
    return len(held), held


def load_receipts():
    """Return set of (ticket_id, token_id) already executed."""
    if not RECEIPTS.exists():
        return set()
    done = set()
    with RECEIPTS.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tid = (row.get("ticket_id", "") or "").strip()
            if tid:
                done.add(tid)
    return done


def read_tickets_from_csv():
    """Read tickets from CSV. Return None if file missing, [] if empty, else ticket list."""
    if not OUTBOX_CSV.exists():
        return None  # file doesn't exist at all
    
    with OUTBOX_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    if not rows:
        return []  # file exists but empty (0 data rows)
    
    results = []
    for r in rows:
        status = (r.get("status") or "").strip()
        if status != "READY_FOR_MANUAL_OR_EXTERNAL_EXECUTION":
            continue
        strategy = (r.get("source_strategy") or "").strip()
        if strategy != ALLOWED_STRATEGY:
            continue
        stake = float(r.get("intended_stake_usdc", 0) or 0)
        if stake < STAKE_MIN or stake > STAKE_MAX:
            continue
        
        results.append({
            "ticket_id": (r.get("ticket_id") or "").strip(),
            "intent_id": (r.get("intent_id") or "").strip(),
            "source_strategy": strategy,
            "token_id": (r.get("token_id") or "").strip(),
            "outcome": (r.get("outcome") or "").strip(),
            "title": (r.get("title") or "").strip(),
            "intended_stake_usdc": stake,
            "tick_size": r.get("tick_size", "0.01"),
            "source_id": (r.get("source_id") or "").strip(),
            "exported_at": (r.get("exported_at") or "").strip(),
        })
    return results


def read_tickets_from_jsonl():
    """Read tickets from JSONL."""
    if not OUTBOX_JSONL.exists():
        return []
    
    results = []
    with OUTBOX_JSONL.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            t = obj.get("ticket", obj)
            status = (t.get("status") or "").strip()
            if status != "READY_FOR_MANUAL_OR_EXTERNAL_EXECUTION":
                continue
            strategy = (t.get("source_strategy") or "").strip()
            if strategy != ALLOWED_STRATEGY:
                continue
            stake = float(t.get("intended_stake_usdc", 0) or 0)
            if stake < STAKE_MIN or stake > STAKE_MAX:
                continue
            
            results.append({
                "ticket_id": (t.get("ticket_id") or "").strip(),
                "intent_id": (t.get("intent_id") or "").strip(),
                "source_strategy": strategy,
                "token_id": (t.get("token_id") or "").strip(),
                "outcome": (t.get("outcome") or "").strip(),
                "title": (t.get("title") or "").strip(),
                "intended_stake_usdc": stake,
                "tick_size": t.get("tick_size", "0.01"),
                "source_id": (t.get("source_id") or "").strip(),
                "exported_at": (t.get("exported_at") or "").strip(),
            })
    return results


def market_still_open(token_id):
    """Check if market has an orderbook (= not yet resolved)."""
    url = f"{CLOB_URL}/book?token_id={token_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            book = json.loads(r.read().decode())
        if book and (book.get("asks") or book.get("bids")):
            return True
        return False
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        log(f"  HTTP error {e.code} for {token_id[:20]}")
        return None  # uncertain


def place_order(client, token_id, tick_size):
    """Place 10U FOK BUY. Return result dict."""
    try:
        resp = client.create_and_post_market_order(
            order_args=MarketOrderArgs(
                token_id=token_id, amount=TRADE_AMOUNT,
                side=Side.BUY, order_type=OrderType.FOK,
            ),
            options=PartialCreateOrderOptions(tick_size=tick_size),
            order_type=OrderType.FOK,
        )
        if isinstance(resp, dict):
            success = resp.get("success") is True and resp.get("status") == "matched"
            fee = float(resp.get("fee", 0) or 0)
            return {
                "ok": success,
                "order_id": resp.get("orderID", ""),
                "price": resp.get("makingAmount", ""),
                "shares": resp.get("takingAmount", ""),
                "fee": fee,
                "spent": float(resp.get("makingAmount", 0) or 0),
                "tx_hash": (resp.get("transactionsHashes") or [""])[0],
                "error": resp.get("errorMsg", ""),
            }
        return {"ok": False, "error": "unexpected response type"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def write_receipt(ticket, result):
    """Append receipt row."""
    exists = RECEIPTS.exists()
    with RECEIPTS.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(RECEIPT_FIELDS)
        status = "EXECUTED" if result.get("ok") else "FAILED"
        notes = result.get("error", "")
        if result.get("ok") and result.get("tx_hash"):
            notes = f"tx={result['tx_hash']}"
        w.writerow([
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            ticket["ticket_id"],
            ticket["intent_id"],
            ticket["source_strategy"],
            status,
            result.get("order_id", ""),
            result.get("price", ""),
            result.get("shares", ""),
            result.get("spent", TRADE_AMOUNT),
            result.get("fee", 0),
            notes,
        ])


def main():
    if os.environ.get(EXECUTION_ENV) != EXECUTION_ACK:
        log(f"[!] Refusing live execution. Set {EXECUTION_ENV}={EXECUTION_ACK} to acknowledge real-money risk.")
        return 1

    cfg = load_config()
    if not all([cfg["private_key"], cfg["api_key"], cfg["api_secret"],
                cfg["api_passphrase"], cfg["funder"]]):
        log("[!] Missing env vars")
        return 1

    client = make_client(cfg)

    # 1. Read tickets from CSV (primary) or JSONL (fallback when CSV doesn't exist)
    csv_data = read_tickets_from_csv()
    
    if csv_data is not None and len(csv_data) == 0:
        # CSV exists but has 0 data rows -> don't order (user rule)
        log("[!] CSV exists but empty. Nothing to do.")
        return 0
    elif csv_data is not None and len(csv_data) > 0:
        tickets = csv_data
        source = "CSV"
    else:
        # CSV file doesn't exist -> fallback to JSONL
        tickets = read_tickets_from_jsonl()
        source = "JSONL"
        if not tickets:
            log("[!] No tickets in CSV or JSONL. Nothing to do.")
            return 0

    log(f"Found {len(tickets)} {ALLOWED_STRATEGY} tickets in {source}")

    # 2. Filter out already executed
    done = load_receipts()
    pending = [t for t in tickets if t["ticket_id"] not in done]
    log(f"After receipt filter: {len(pending)} pending")

    if not pending:
        log("[!] All tickets already processed. Nothing to do.")
        return 0

    # 3. Filter by freshness: only tickets exported within last 300 seconds
    now = datetime.now(timezone.utc)
    fresh = []
    for t in pending:
        exported_str = t.get("exported_at", "")
        if not exported_str:
            continue
        try:
            exported_dt = datetime.fromisoformat(exported_str.replace("Z", "+00:00"))
            age = (now - exported_dt).total_seconds()
            if 0 <= age <= FRESH_WINDOW_SECONDS:
                fresh.append(t)
            else:
                pass  # skip old tickets silently
        except ValueError:
            continue
    
    pending = fresh
    log(f"After freshness filter ({FRESH_WINDOW_SECONDS}s): {len(pending)} pending")

    if not pending:
        log("[!] No fresh tickets. Nothing to do.")
        return 0

    # 4. Check positions, balance, and held token_ids
    try:
        n_pos, held_tokens = get_open_positions(client)
    except Exception as e:
        log(f"[!] Failed to get positions: {e}")
        n_pos, held_tokens = MAX_POSITIONS, set()  # cautious

    try:
        balance = get_balance(client, cfg)
    except Exception as e:
        log(f"[!] Failed to get balance: {e}")
        return 1

    log(f"Positions: {n_pos}/{MAX_POSITIONS} | Balance: {balance:.2f} USDC")

    # 5. Dedup: skip if token_id already held in current positions
    orig_count = len(pending)
    pending = [t for t in pending if t["token_id"] not in held_tokens]
    if len(pending) < orig_count:
        log(f"Skipped {orig_count - len(pending)} tickets: token_id already held")

    # Also dedup multiple tickets for same token_id (keep newest)
    seen_tokens = {}
    for t in pending:
        tid = t.get("token_id", "")
        if tid:
            seen_tokens[tid] = t
    pending = list(seen_tokens.values())
    log(f"After token_id dedup: {len(pending)} unique tickets")

    if not pending:
        log("[!] No new tickets to execute.")
        return 0

    slots = MAX_POSITIONS - n_pos
    can_afford = max(0, int(balance // TRADE_AMOUNT))
    capacity = min(slots, can_afford)

    if capacity <= 0:
        log(f"[!] No capacity. slots={slots}, can_afford={can_afford}")
        return 0

    to_execute = pending[:capacity]
    log(f"Will execute {len(to_execute)} tickets")

    # 4. Execute
    executed = 0
    total_spent = 0.0

    for i, ticket in enumerate(to_execute, 1):
        token_id = ticket["token_id"]
        if not token_id or token_id == "0":
            log(f"  [{i}] SKIP (no token_id): {ticket['ticket_id']}")
            continue

        # Check market still open
        open_status = market_still_open(token_id)
        if open_status is False:
            log(f"  [{i}] SKIP (market closed): {ticket['title'][:45]}")
            # Still write receipt to mark it as processed
            write_receipt(ticket, {"ok": False, "error": "market_closed"})
            continue
        elif open_status is None:
            log(f"  [{i}] SKIP (market query failed): {ticket['title'][:45]}")
            continue

        title = ticket["title"][:45]
        candidate = (ticket["source_id"] or "").split(":")[0] or "?"
        log(f"  [{i}/{len(to_execute)}] {title:45s} | No | 10U | {candidate}")

        result = place_order(client, token_id, ticket.get("tick_size", "0.01"))
        write_receipt(ticket, result)

        if result.get("ok"):
            executed += 1
            total_spent += result.get("spent", TRADE_AMOUNT)
            log(f"    [OK] order={result['order_id'][:20]}...")
        else:
            log(f"    [FAIL] {result.get('error', '?')[:80]}")

        if executed >= capacity:
            break

        time.sleep(DELAY)

    # Summary
    log(f"DONE: {executed} executed, {total_spent:.1f}U spent, balance left: {balance - total_spent:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
