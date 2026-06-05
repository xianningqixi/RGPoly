#!/usr/bin/env python3
"""
polymarket_btc_copy_worker_daemon.py — Local persistent worker v2.

Only reads execution_outbox.csv / .jsonl.
No strategy scanning. No wallet discovery. No self-selection.

Rules (2026-06-04):
- Only source_strategy = btc_no_dominant_candidate_copy
- Only status = READY_FOR_MANUAL_OR_EXTERNAL_EXECUTION
- Only action = BUY
- Only intended_stake_usdc ∈ [9.99, 10.01]
- Ticket freshness: exported_at within 120 seconds
- Dedup: ticket_id once; token_id+outcome not held; max 30 positions
- Failed orders: write receipt with status=EXCEPTION
- Optional fields: source_to_ask_gap, btc_spot, btc_momentum_bps

Env: PRIVATE_KEY, POLY_API_KEY, POLY_API_SECRET, POLY_API_PASSPHRASE,
     POLY_PROXY_ADDRESS, POLY_SIGNATURE_TYPE
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
ROOT = Path(r"C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket")
OUTBOX_CSV = ROOT / "execution_outbox.csv"
OUTBOX_JSONL = ROOT / "execution_outbox.jsonl"
RECEIPTS = ROOT / "external_execution_receipts.csv"
SEEN_FILE = ROOT / ".seen_ticket_ids.json"
CLOB_URL = "https://clob.polymarket.com"
EXECUTION_ACK = "I_UNDERSTAND_REAL_MONEY_RISK"
EXECUTION_ENV = "POLY_BTC_COPY_WORKER_ENABLED"
POLL_INTERVAL = 5
MAX_POSITIONS = 30
STAKE_MIN = 9.99
STAKE_MAX = 10.01
FRESH_WINDOW = 120  # seconds
ALLOWED_STRATEGY = "btc_no_dominant_candidate_copy"
ALLOWED_STATUS = "READY_FOR_MANUAL_OR_EXTERNAL_EXECUTION"
ALLOWED_ACTIONS = {"BUY"}
DELAY = 1.5

RECEIPT_FIELDS = [
    "ts", "ticket_id", "source_strategy", "source_id", "wallet_name",
    "action", "outcome", "token_id", "intended_stake_usdc", "sim_fill_price",
    "executed_price", "executed_size", "status", "tx_hash", "error",
    "source_to_ask_gap", "btc_spot", "btc_momentum_bps",
]

OPTIONAL_FIELDS = ["source_to_ask_gap", "btc_spot", "btc_momentum_bps"]


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


# --- Dedup helpers ---

def load_seen():
    if not SEEN_FILE.exists():
        return set()
    try:
        data = json.loads(SEEN_FILE.read_text("utf-8"))
        return set(data.get("executed", []))
    except Exception:
        return set()


def save_seen(seen):
    SEEN_FILE.write_text(json.dumps({"executed": sorted(seen)}, indent=2), "utf-8")


def load_receipts():
    """Return set of ticket_ids from receipts file."""
    if not RECEIPTS.exists():
        return set()
    done = set()
    try:
        with RECEIPTS.open("r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                tid = (row.get("ticket_id") or "").strip()
                if tid:
                    done.add(tid)
    except Exception:
        pass
    return done


def write_receipt(ticket, result):
    """Append a receipt row. result: dict with price/shares/tx/error fields."""
    exists = RECEIPTS.exists()
    with RECEIPTS.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(RECEIPT_FIELDS)

        status = "EXECUTED" if result.get("ok") else "EXCEPTION"
        error = result.get("error", "")
        tx = result.get("tx_hash", "")

        row = [
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            ticket.get("ticket_id", ""),
            ticket.get("source_strategy", ""),
            ticket.get("source_id", ""),
            ticket.get("wallet_name", ""),
            ticket.get("action", ""),
            ticket.get("outcome", ""),
            ticket.get("token_id", ""),
            ticket.get("intended_stake_usdc", ""),
            ticket.get("sim_fill_price", ""),
            result.get("price", ""),
            result.get("shares", ""),
            status,
            tx,
            error,
            result.get("source_to_ask_gap", ""),
            result.get("btc_spot", ""),
            result.get("btc_momentum_bps", ""),
        ]
        w.writerow(row)


# --- CLOB API ---

def get_balance(client, cfg):
    bal = client.get_balance_allowance(
        BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, signature_type=cfg["sig_type"])
    )
    return float(bal["balance"]) / 1e6


def get_open_positions(client):
    """Return (count, set_of_asset_ids)."""
    trades = client.get_trades()
    by_asset = {}
    for t in trades:
        aid = t.get("asset_id", "")
        side = t.get("side", "")
        size = float(t.get("size", 0))
        if not aid:
            continue
        by_asset[aid] = by_asset.get(aid, 0.0) + (size if side == "BUY" else -size)
    held = {a for a, n in by_asset.items() if n > 0.5}
    return len(held), held


def market_still_open(token_id):
    url = f"{CLOB_URL}/book?token_id={token_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            book = json.loads(r.read().decode())
        if book and (book.get("asks") or book.get("bids")):
            return True
        return False
    except urllib.error.HTTPError as e:
        return False if e.code == 404 else None


def place_order(client, token_id, tick_size):
    """Place 10U FOK BUY. Return result dict."""
    try:
        resp = client.create_and_post_market_order(
            order_args=MarketOrderArgs(
                token_id=token_id, amount=10.0,
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
                "price": resp.get("makingAmount", ""),
                "shares": resp.get("takingAmount", ""),
                "fee": fee,
                "spent": float(resp.get("makingAmount", 0) or 0),
                "tx_hash": (resp.get("transactionsHashes") or [""])[0],
                "error": resp.get("errorMsg", ""),
            }
        return {"ok": False, "error": f"unexpected response: {type(resp).__name__}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


# --- Ticket reader ---

def read_tickets():
    """Return (list_of_tickets, source_name) or (None, 'EMPTY') or ([], 'NONE')."""
    if OUTBOX_CSV.exists():
        with OUTBOX_CSV.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        if not rows:
            return None, "EMPTY"  # exists but empty → don't order

        tickets = []
        for r in rows:
            t = {
                "ticket_id": (r.get("ticket_id") or "").strip(),
                "source_strategy": (r.get("source_strategy") or "").strip(),
                "source_id": (r.get("source_id") or "").strip(),
                "wallet_name": (r.get("wallet_name") or "").strip(),
                "status": (r.get("status") or "").strip(),
                "action": (r.get("action") or "").strip(),
                "outcome": (r.get("outcome") or "").strip(),
                "token_id": (r.get("token_id") or "").strip(),
                "intended_stake_usdc": (r.get("intended_stake_usdc") or "").strip(),
                "sim_fill_price": (r.get("sim_fill_price") or "").strip(),
                "tick_size": r.get("tick_size", "0.01"),
                "exported_at": (r.get("exported_at") or "").strip(),
                "title": (r.get("title") or "").strip(),
                "source_to_ask_gap": (r.get("source_to_ask_gap") or "").strip(),
                "btc_spot": (r.get("btc_spot") or "").strip(),
                "btc_momentum_bps": (r.get("btc_momentum_bps") or "").strip(),
            }
            tickets.append(t)
        return tickets, "CSV"

    # JSONL fallback
    if not OUTBOX_JSONL.exists():
        return [], "NONE"
    tickets = []
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
            tickets.append({
                "ticket_id": (t.get("ticket_id") or "").strip(),
                "source_strategy": (t.get("source_strategy") or "").strip(),
                "source_id": (t.get("source_id") or "").strip(),
                "wallet_name": (t.get("wallet_name") or "").strip(),
                "status": (t.get("status") or "").strip(),
                "action": (t.get("action") or "").strip(),
                "outcome": (t.get("outcome") or "").strip(),
                "token_id": (t.get("token_id") or "").strip(),
                "intended_stake_usdc": (t.get("intended_stake_usdc") or "").strip(),
                "sim_fill_price": (t.get("sim_fill_price") or "").strip(),
                "tick_size": t.get("tick_size", "0.01"),
                "exported_at": (t.get("exported_at") or "").strip(),
                "title": (t.get("title") or "").strip(),
                "source_to_ask_gap": (t.get("source_to_ask_gap") or "").strip(),
                "btc_spot": (t.get("btc_spot") or "").strip(),
                "btc_momentum_bps": (t.get("btc_momentum_bps") or "").strip(),
            })
    return tickets, "JSONL"


# --- Skip reasons ---

SKIP_STATUS = "wrong_status"
SKIP_STRATEGY = "wrong_strategy"
SKIP_ACTION = "wrong_action"
SKIP_STAKE = "wrong_stake"
SKIP_AGE = "too_old"
SKIP_EXECUTED = "already_executed"
SKIP_HELD = "token_id_held"
SKIP_MAX = "max_positions"
SKIP_NO_BALANCE = "no_balance"

SKIP_MARKET_CLOSED = "market_closed"
SKIP_MARKET_ERROR = "market_query_error"
SKIP_MARKET_LIVE = "LIVE"


def filter_tickets(tickets, seen, receipts_set, now, n_pos, held_assets, balance, dry_run=False):
    """Filter tickets and return (eligible, skipped_with_reason)."""
    eligible = []
    skipped = []  # list of (ticket, reason)

    for tk in tickets:
        # Strategy
        if tk["source_strategy"] != ALLOWED_STRATEGY:
            skipped.append((tk, SKIP_STRATEGY))
            continue

        # Status
        if tk["status"] != ALLOWED_STATUS:
            skipped.append((tk, SKIP_STATUS))
            continue

        # Action
        if tk["action"] not in ALLOWED_ACTIONS:
            skipped.append((tk, SKIP_ACTION))
            continue

        # Stake
        try:
            stake = float(tk["intended_stake_usdc"] or 0)
        except ValueError:
            skipped.append((tk, SKIP_STAKE))
            continue
        if stake < STAKE_MIN or stake > STAKE_MAX:
            skipped.append((tk, SKIP_STAKE))
            continue

        # Freshness
        exported_str = tk.get("exported_at", "")
        if exported_str:
            try:
                dt = datetime.fromisoformat(exported_str.replace("Z", "+00:00"))
                age = (now - dt).total_seconds()
                if age < 0 or age > FRESH_WINDOW:
                    skipped.append((tk, SKIP_AGE))
                    continue
            except ValueError:
                skipped.append((tk, SKIP_AGE))
                continue
        else:
            skipped.append((tk, SKIP_AGE))
            continue

        # Dedup ticket_id
        if tk["ticket_id"] in seen or tk["ticket_id"] in receipts_set:
            skipped.append((tk, SKIP_EXECUTED))
            continue

        # Dedup token_id
        if tk["token_id"] in held_assets:
            skipped.append((tk, SKIP_HELD))
            continue

        # Max positions
        if n_pos >= MAX_POSITIONS:
            skipped.append((tk, SKIP_MAX))
            continue

        # Balance
        slots = MAX_POSITIONS - n_pos
        can_afford = max(0, int(balance // 10.0))
        capacity = min(slots, can_afford)
        if len(eligible) >= capacity:
            skipped.append((tk, SKIP_NO_BALANCE))
            continue

        eligible.append(tk)

    return eligible, skipped


# --- Main loop ---

def main_loop(dry_run=False):
    if not dry_run and os.environ.get(EXECUTION_ENV) != EXECUTION_ACK:
        log(f"[FATAL] Refusing live execution. Set {EXECUTION_ENV}={EXECUTION_ACK} to acknowledge real-money risk.")
        sys.exit(1)

    cfg = load_config()
    if not all([cfg["private_key"], cfg["api_key"], cfg["api_secret"],
                cfg["api_passphrase"], cfg["funder"]]):
        log("[FATAL] Missing env vars")
        sys.exit(1)

    client = make_client(cfg)
    seen = load_seen()

    if dry_run:
        log("[DRY-RUN MODE] No orders will be placed.")
        _dry_run_pass(client, cfg, seen)
        return

    log(f"Worker started. Polling every {POLL_INTERVAL}s. Max {MAX_POSITIONS} positions.")
    log(f"Seen: {len(seen)} tickets. Freshness: {FRESH_WINDOW}s. Stake: {STAKE_MIN}-{STAKE_MAX}")

    while True:
        cycle_start = time.time()
        try:
            _do_cycle(client, cfg, seen)
        except Exception as e:
            log(f"[ERROR] {e}")

        elapsed = time.time() - cycle_start
        time.sleep(max(0.1, POLL_INTERVAL - elapsed))


def _do_cycle(client, cfg, seen):
    """One poll cycle."""
    tickets, source = read_tickets()

    if tickets is None and source == "EMPTY":
        return
    if not tickets:
        return

    now = datetime.now(timezone.utc)
    receipts_set = load_receipts()

    try:
        n_pos, held_assets = get_open_positions(client)
        balance = get_balance(client, cfg)
    except Exception as e:
        log(f"[WARN] CLOB query failed: {e}")
        return

    eligible, _ = filter_tickets(tickets, seen, receipts_set, now, n_pos, held_assets, balance)

    if not eligible:
        return

    log(f"Found {len(eligible)} ticket(s) to execute (pos={n_pos}, bal={balance:.1f}U)")

    for i, ticket in enumerate(eligible, 1):
        token_id = ticket["token_id"]
        if not token_id or token_id == "0":
            continue

        # Check market open
        open_ok = market_still_open(token_id)
        if open_ok is False:
            write_receipt(ticket, {"ok": False, "error": "market_closed"})
            seen.add(ticket["ticket_id"])
            save_seen(seen)
            log(f"  [{i}] SKIP (closed): {ticket.get('title', '?')[:40]}")
            continue
        elif open_ok is None:
            log(f"  [{i}] SKIP (query err): {ticket.get('title', '?')[:40]}")
            continue

        wallet = ticket.get("wallet_name") or ticket.get("source_id", "?").split(":")[0]
        log(f"  [{i}] {ticket.get('title', '?')[:40]:40s} | 10U | {wallet}")

        result = place_order(client, token_id, ticket.get("tick_size", "0.01"))
        # Add optional fields
        for f in OPTIONAL_FIELDS:
            result[f] = ticket.get(f, "")
        write_receipt(ticket, result)
        seen.add(ticket["ticket_id"])
        save_seen(seen)

        if result.get("ok"):
            log(f"    [OK] tx={result.get('tx_hash', '')[:20]}...")
        else:
            log(f"    [EXCEPTION] {result.get('error', '?')[:80]}")

        time.sleep(DELAY)

        # Re-check positions mid-batch
        try:
            n_pos, held_assets = get_open_positions(client)
            if n_pos >= MAX_POSITIONS:
                log("Max positions reached mid-batch, stopping.")
                break
        except Exception:
            pass


def _dry_run_pass(client, cfg, seen):
    """Single dry-run pass: show eligible/skipped details."""
    tickets, source = read_tickets()
    log(f"Source: {source} | Total raw tickets: {len(tickets) if isinstance(tickets, list) else 0}")

    if tickets is None:
        log("CSV exists but empty. No tickets to process.")
        return
    if not tickets:
        log("No tickets found.")
        return

    now = datetime.now(timezone.utc)
    receipts_set = load_receipts()

    try:
        n_pos, held_assets = get_open_positions(client)
        balance = get_balance(client, cfg)
    except Exception as e:
        log(f"[WARN] CLOB query failed: {e}")
        n_pos, held_assets, balance = 0, set(), 0.0

    log(f"Current positions: {n_pos}/{MAX_POSITIONS} | Balance: {balance:.2f} USDC")
    log(f"Receipts file: {len(receipts_set)} ticket_ids tracked")
    log(f"Seen file: {len(seen)} ticket_ids tracked")
    log("")

    eligible, skipped = filter_tickets(tickets, seen, receipts_set, now, n_pos, held_assets, balance, dry_run=True)

    # Summarize skip reasons
    skip_count = {}
    for _, reason in skipped:
        skip_count[reason] = skip_count.get(reason, 0) + 1

    print("=" * 60)
    print(f"  ELIGIBLE: {len(eligible)}")
    print(f"  SKIPPED:  {len(skipped)}")
    print("-" * 60)
    print("  Skip reasons:")
    for reason, count in sorted(skip_count.items(), key=lambda x: -x[1]):
        print(f"    {reason}: {count}")
    print("=" * 60)
    print()

    if eligible:
        print("=== ELIGIBLE TICKETS ===")
        for i, tk in enumerate(eligible, 1):
            age_sec = "?"
            if tk.get("exported_at"):
                try:
                    dt = datetime.fromisoformat(tk["exported_at"].replace("Z", "+00:00"))
                    age_sec = f"{(now - dt).total_seconds():.0f}s"
                except ValueError:
                    pass
            wallet = tk.get("wallet_name") or tk.get("source_id", "?").split(":")[0]
            print(f"  {i:2d}. {tk.get('title', '?')[:45]:45s} | {age_sec:5s} | {wallet}")

    if skipped:
        print()
        print(f"=== SKIPPED TICKETS (sample, max 15) ===")
        shown = 0
        for tk, reason in skipped:
            if shown >= 15:
                print(f"  ... and {len(skipped) - shown} more")
                break
            wallet = tk.get("wallet_name") or tk.get("source_id", "?").split(":")[0]
            print(f"  {reason:20s} | {tk.get('title', '?')[:40]:40s} | {wallet}")
            shown += 1


if __name__ == "__main__":
    if "--dry-run" in sys.argv or "-d" in sys.argv:
        main_loop(dry_run=True)
    else:
        try:
            main_loop()
        except KeyboardInterrupt:
            log("Worker stopped.")
            sys.exit(0)
