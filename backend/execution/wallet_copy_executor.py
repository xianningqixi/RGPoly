#!/usr/bin/env python3
"""
wallet_copy_executor.py — Polymarket wallet-copy live execution module.

Places real FOK buy orders on Polymarket CLOB, mirroring signals from the
btc_directional or weather_high_prob wallet-copy simulators.

SAFETY:
  --dry-run (default)  → logs what WOULD execute, no orders placed
  --execute             → places real FOK orders (requires env gate)

ENV GATE (required for --execute):
  POLY_WALLET_COPY_ENABLED=I_UNDERSTAND_REAL_MONEY_RISK

AUTH (pick one):
  A) POLY_PRIVATE_KEY / PK          → wallet private key (Polygon)
  B) POLY_API_KEY + POLY_API_SECRET + POLY_API_PASSPHRASE  → derived CLOB creds

USAGE:
  # Dry-run: scan OPEN trades, log what would execute
  python wallet_copy_executor.py --strategy btc_directional --dry-run

  # Live: place real FOK orders (small stakes)
  python wallet_copy_executor.py --strategy btc_directional --execute --max-usdc 10

  # Weather wallet copy
  python wallet_copy_executor.py --strategy weather_high_prob --execute --max-usdc 5
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Fix console encoding for Chinese Windows (GBK→UTF-8)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import urllib.request
import urllib.parse

# ── constants ───────────────────────────────────────────────────────────────

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
USER_AGENT = "wallet-copy-executor/0.1"
ACK_ENVVAR = "I_UNDERSTAND_REAL_MONEY_RISK"
PROJECT_DIR = Path.cwd()

STRATEGY_CONFIG = {
    "btc_directional": {
        "audit_csv": PROJECT_DIR / "btc_directional_trade_audit.csv",
        "max_usdc_default": 10.0,
        "min_usdc": 1.0,
        "label": "BTC directional copy",
        # Match strategies that START with any of these prefixes
        "strategy_prefixes": ["btc_directional_wallet_copy", "btc_directional_copy"],
    },
    "weather_high_prob": {
        "audit_csv": PROJECT_DIR / "weather_high_prob_trade_audit.csv",
        "max_usdc_default": 5.0,
        "min_usdc": 1.0,
        "label": "Weather high-prob wallet copy",
        "strategy_prefixes": ["weather_high_prob_wallet_copy", "weather_high_prob"],
    },
    "btc_directional_live_shadow": {
        "audit_csv": PROJECT_DIR / "btc_directional_trade_audit.csv",
        "max_usdc_default": 10.0,
        "min_usdc": 1.0,
        "label": "BTC directional live shadow",
        "strategy_prefixes": ["btc_directional_wallet_copy", "btc_directional_copy"],
    },
}


# ── data model ──────────────────────────────────────────────────────────────


@dataclass
class PendingTrade:
    row_id: str
    strategy: str
    wallet_name: str
    slug: str
    outcome: str
    stake: float
    token_id: str | None
    fill_price: float | None
    timestamp: str
    raw_row: dict[str, str]


@dataclass
class ExecutionRecord:
    ts: str
    mode: str
    strategy: str
    row_id: str
    slug: str
    outcome: str
    intended_stake: float
    ask_at_exec: float | None
    total_cost: float | None
    status: str  # DRY_RUN | EXECUTED | SKIP_NO_ASK | SKIP_STALE_MARKET | SKIP_SLIPPAGE | FAILED
    detail: str
    raw_response: dict[str, Any] = field(default_factory=dict)


# ── Gamma / CLOB helpers (read-only) ────────────────────────────────────────


def _gamma_get(path: str) -> Any:
    url = f"{GAMMA_BASE}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _clob_get(path: str) -> Any:
    url = f"{CLOB_BASE}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def fetch_market_by_slug(slug: str) -> dict[str, Any] | None:
    """Return the first Gamma market matching slug."""
    try:
        data = _gamma_get(f"/markets?slug={urllib.parse.quote(slug)}&limit=1")
        if isinstance(data, list) and data:
            return data[0]
        return None
    except Exception as exc:
        print(f"    [fetch_market_by_slug] Slug not found: {slug[:40]} ({exc})", flush=True)
        return None


def clob_book(token_id: str) -> dict[str, Any] | None:
    """Fetch CLOB order book for a token. Returns {'asks': [...], 'bids': [...]}."""
    try:
        return _clob_get(f"/book?token_id={token_id}")
    except Exception:
        return None


def best_ask(token_id: str) -> float | None:
    """Get the best ask price for a token from CLOB."""
    book = clob_book(token_id)
    if not book or "asks" not in book or not book["asks"]:
        return None
    try:
        return float(book["asks"][0]["price"])
    except (IndexError, KeyError, ValueError, TypeError):
        return None


def gamma_outcome_by_token(market: dict[str, Any], token_id: str) -> dict[str, Any] | None:
    """Find the outcome in a Gamma market matching the given token_id."""
    for outcome in market.get("outcomes", []):
        if outcome.get("token_id") == token_id:
            return outcome
    return None


# ── CSV helpers ─────────────────────────────────────────────────────────────


def load_audit_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def find_open_trades(rows: list[dict[str, str]], strategy_filter: str | None = None, strategy_prefixes: list[str] | None = None) -> list[PendingTrade]:
    """Collect all OPEN rows that haven't been processed by this executor."""
    pending: list[PendingTrade] = []
    for row in rows:
        status = (row.get("status") or "").strip().upper()
        if status != "OPEN":
            continue
        sid = (row.get("id") or "").strip()
        strat = (row.get("strategy") or "").strip()
        if strategy_filter and strategy_prefixes:
            match = any(strat.startswith(p) for p in strategy_prefixes)
            if not match:
                continue
        elif strategy_filter and strat != strategy_filter:
            continue
        token = (row.get("token_id") or "").strip()
        try:
            stake_val = float((row.get("stake") or "0").replace(",", ""))
        except ValueError:
            stake_val = 0.0
        pending.append(
            PendingTrade(
                row_id=sid,
                strategy=strat,
                wallet_name=(row.get("wallet_name") or "").strip(),
                slug=(row.get("slug") or "").strip(),
                outcome=(row.get("outcome") or "").strip(),
                stake=stake_val,
                token_id=token if token else None,
                fill_price=None,
                timestamp=(row.get("ts") or row.get("timestamp") or "").strip(),
                raw_row=row,
            )
        )
    return pending


def resolve_token_id(trade: PendingTrade) -> str | None:
    """Resolve token_id from slug + outcome. First tries existing token_id."""
    if trade.token_id:
        return trade.token_id
    # Fallback: fetch from Gamma
    market = fetch_market_by_slug(trade.slug)
    if not market:
        return None

    # Polymarket Gamma API: outcomes and clobTokenIds are often JSON strings
    # e.g. outcomes='"["Yes", "No"]"' and clobTokenIds='"["tok1", "tok2"]"'
    def _parse_json_field(val):
        if isinstance(val, str):
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return val
        return val

    outcomes_raw = _parse_json_field(market.get("outcomes", []))
    if not isinstance(outcomes_raw, list):
        outcomes_raw = []

    clob_ids_raw = _parse_json_field(market.get("clobTokenIds", market.get("clobtokenids", [])))
    if not isinstance(clob_ids_raw, list):
        clob_ids_raw = []

    token_ids_raw = _parse_json_field(market.get("token_ids", []))
    if not isinstance(token_ids_raw, list):
        token_ids_raw = []

    outcomes_out = _parse_json_field(market.get("outcomes_out", {}))
    if not isinstance(outcomes_out, dict):
        outcomes_out = {}

    # Prefer: outcomes_out dict {"Yes": "token_id_123", ...}
    target = trade.outcome.strip().lower()
    if outcomes_out:
        for key_raw, tid in outcomes_out.items():
            if key_raw.strip().lower() == target:
                return tid

    # Match outcome name to token ID by index
    for i, outcome in enumerate(outcomes_raw):
        if isinstance(outcome, dict):
            name = (outcome.get("outcome") or outcome.get("name") or "").strip().lower()
        else:
            name = str(outcome).strip().lower()

        if name == target:
            # Priority: clobTokenIds (most reliable) > token_ids > outcome dict
            if i < len(clob_ids_raw) and clob_ids_raw[i]:
                return str(clob_ids_raw[i])
            if i < len(token_ids_raw) and token_ids_raw[i]:
                return str(token_ids_raw[i])
            if isinstance(outcome, dict):
                tid = outcome.get("token_id") or outcome.get("id")
                if tid:
                    return str(tid)

    return None


def check_market_still_open(slug: str) -> tuple[bool, str]:
    """Check if the market is still open for trading. Returns (is_open, reason)."""
    market = fetch_market_by_slug(slug)
    if market is None:
        return False, "GAMMA_NOT_FOUND"
    closed = market.get("closed") or market.get("closed_time") or False
    if isinstance(closed, bool) and closed:
        return False, "MARKET_CLOSED"
    if isinstance(closed, str) and closed.lower() == "true":
        return False, "MARKET_CLOSED"
    end_date = market.get("end_date_iso")
    if end_date:
        try:
            if end_date < datetime.now(timezone.utc).isoformat():
                return False, "EXPIRED"
        except TypeError:
            pass
    return True, "OPEN"


# ── execution ───────────────────────────────────────────────────────────────


def make_client(args: argparse.Namespace) -> Any | None:
    """Create a py-clob-client-v2 ClobClient. Returns None in dry-run mode."""
    try:
        from py_clob_client_v2 import ApiCreds, ClobClient
    except ImportError as exc:
        raise RuntimeError("pip install py-clob-client-v2") from exc

    private_key = os.environ.get("POLY_PRIVATE_KEY") or os.environ.get("PK")
    if not private_key:
        print("[WARN] POLY_PRIVATE_KEY/PK not set — client will be None (dry-run enforced)", file=sys.stderr)
        return None

    funder = os.environ.get("POLY_PROXY_ADDRESS") or None
    sig_type_raw = os.environ.get("POLY_SIGNATURE_TYPE")
    sig_type = int(sig_type_raw) if sig_type_raw else None

    api_key = os.environ.get("POLY_API_KEY") or os.environ.get("CLOB_API_KEY")
    api_secret = os.environ.get("POLY_API_SECRET") or os.environ.get("CLOB_SECRET")
    api_passphrase = os.environ.get("POLY_API_PASSPHRASE") or os.environ.get("CLOB_PASS_PHRASE")

    if api_key and api_secret and api_passphrase:
        creds = ApiCreds(api_key=api_key, api_secret=api_secret, api_passphrase=api_passphrase)
    else:
        client = ClobClient(
            host=CLOB_BASE, chain_id=137, key=private_key,
            signature_type=sig_type, funder=funder,
        )
        creds = client.create_or_derive_api_key()

    return ClobClient(
        host=CLOB_BASE, chain_id=137, key=private_key,
        creds=creds, signature_type=sig_type, funder=funder,
        retry_on_error=True,
    )


def check_slippage(book_ask: float, intended_budget: float, tick_size: str = "0.01") -> tuple[bool, float]:
    """Check if the order is feasible. Returns (can_execute, estimated_cost)."""
    # FOK market order: we just check that the best ask isn't absurd
    # Polymarket shares cost up to 1 USDC each, anything over 0.98 is fine
    if book_ask > 0.99:
        print(f"  [!] Ask {book_ask:.4f} is near 1.0 - expected cost: {intended_budget:.2f} USDC")
    return True, intended_budget


def place_fok_buy(client: Any, token_id: str, usdc_amount: float, tick_size: str = "0.01") -> dict[str, Any]:
    """Place a FOK market buy order on Polymarket."""
    from py_clob_client_v2 import MarketOrderArgs, OrderType, PartialCreateOrderOptions, Side

    response = client.create_and_post_market_order(
        order_args=MarketOrderArgs(
            token_id=token_id,
            amount=usdc_amount,
            side=Side.BUY,
            order_type=OrderType.FOK,
        ),
        options=PartialCreateOrderOptions(tick_size=tick_size),
        order_type=OrderType.FOK,
    )
    if isinstance(response, dict):
        return response
    try:
        return json.loads(json.dumps(response, default=lambda v: getattr(v, "__dict__", str(v))))
    except TypeError:
        return {"raw": str(response)}


def response_ok(response: dict[str, Any]) -> bool:
    if response.get("success") is False:
        return False
    status = str(response.get("status") or response.get("state") or "").lower()
    for word in ["failed", "cancel", "reject", "error"]:
        if word in status:
            return False
    return True


# ── main loop ───────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Polymarket wallet-copy executor")
    parser.add_argument("--strategy", choices=list(STRATEGY_CONFIG.keys()), required=True,
                        help="Which strategy's OPEN trades to execute")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Log what WOULD execute, no real orders (default)")
    parser.add_argument("--execute", action="store_true",
                        help="Place real FOK orders (requires env gate)")
    parser.add_argument("--max-usdc", type=float, default=None,
                        help="Max USDC per trade (default: strategy default)")
    parser.add_argument("--min-usdc", type=float, default=None,
                        help="Min USDC per trade (default: strategy default)")
    parser.add_argument("--max-trades", type=int, default=0,
                        help="Stop after this many executions (0 = no limit)")
    parser.add_argument("--max-daily-usdc", type=float, default=50.0,
                        help="Hard daily cap total USDC placed (default: 50)")
    parser.add_argument("--tick-size", default="0.01",
                        help="Tick size for FOK order (default: 0.01)")
    parser.add_argument("--interval", type=float, default=15.0,
                        help="Poll interval in seconds (default: 15)")
    parser.add_argument("--once", action="store_true",
                        help="Single pass, then exit")
    parser.add_argument("--fok-only", action="store_true", default=True,
                        help="Only use FOK orders (default)")
    parser.add_argument("--log", type=Path, default=PROJECT_DIR / "wallet_copy_exec_log.csv",
                        help="Execution log CSV path")
    parser.add_argument("--json-log", type=Path, default=PROJECT_DIR / "wallet_copy_exec_log.jsonl",
                        help="Raw JSON execution log path")
    parser.add_argument("--seen", type=Path, default=PROJECT_DIR / "wallet_copy_executor_seen.json",
                        help="JSON file tracking processed row IDs (persists across restarts)")
    return parser


def execution_enabled(args: argparse.Namespace) -> bool:
    return args.execute and os.environ.get("POLY_WALLET_COPY_ENABLED") == ACK_ENVVAR


def recent_daily_cost(log_path: Path) -> float:
    """Sum up today's successfully executed USDC from the log."""
    if not log_path.exists():
        return 0.0
    today = datetime.now().strftime("%Y-%m-%d")
    total = 0.0
    with log_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = (row.get("ts") or "").strip()
            if ts.startswith(today):
                cost_str = (row.get("total_cost") or "0").strip()
                try:
                    total += float(cost_str)
                except ValueError:
                    pass
    return total


def append_execution_log(path: Path, record: ExecutionRecord) -> None:
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "ts", "mode", "strategy", "row_id", "slug", "outcome",
            "intended_stake", "ask_at_exec", "total_cost", "status", "detail",
        ])
        if not exists:
            writer.writeheader()
        writer.writerow({
            "ts": record.ts,
            "mode": record.mode,
            "strategy": record.strategy,
            "row_id": record.row_id,
            "slug": record.slug,
            "outcome": record.outcome,
            "intended_stake": f"{record.intended_stake:.4f}",
            "ask_at_exec": f"{record.ask_at_exec:.6f}" if record.ask_at_exec else "",
            "total_cost": f"{record.total_cost:.4f}" if record.total_cost else "",
            "status": record.status,
            "detail": record.detail[:500],
        })


def append_json_log(path: Path, record: ExecutionRecord) -> None:
    with path.open("a", encoding="utf-8") as f:
        data = record.__dict__ | {"raw_response": record.raw_response}
        f.write(json.dumps(data, ensure_ascii=False, default=str) + "\n")


def load_seen(path: Path) -> set[str]:
    """Load processed row IDs from JSON file."""
    if not path.exists():
        return set()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("processed_ids", []))
    except (json.JSONDecodeError, Exception) as exc:
        print(f"  [load_seen] error: {exc}", file=sys.stderr)
        return set()


def save_seen(path: Path, ids: set[str]) -> None:
    """Save processed row IDs to JSON file."""
    with path.open("w", encoding="utf-8") as f:
        json.dump({"processed_ids": list(ids)}, f)


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    live = execution_enabled(args)

    if args.execute and not live:
        print(
            "[WARN] --execute set but POLY_WALLET_COPY_ENABLED is not set to "
            f"'{ACK_ENVVAR}'. Running in dry-run mode.",
            file=sys.stderr,
        )
        live = False

    cfg = STRATEGY_CONFIG[args.strategy]
    max_usdc = args.max_usdc or cfg["max_usdc_default"]
    min_usdc = args.min_usdc or cfg["min_usdc"]

    client = make_client(args) if live else None

    trades_done = 0
    scan_id = 0
    # Track IDs already processed (persisted to file)
    processed_ids: set[str] = load_seen(args.seen)

    if args.once:
        print(f"[{'LIVE' if live else 'DRY'}] {cfg['label']} — single pass")
        run_once(args, cfg, client, live, max_usdc, min_usdc, processed_ids)
        return 0

    print(f"[{'LIVE' if live else 'DRY'}] {cfg['label']} — polling every {args.interval}s")

    while True:
        scan_id += 1
        started = time.time()
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            daily_cost = recent_daily_cost(args.log) if live else 0.0
            remaining_daily = max(0.0, args.max_daily_usdc - daily_cost)

            print(f"[{stamp}] scan={scan_id} seen={len(processed_ids)} "
                  f"daily_cost={daily_cost:.2f}/{args.max_daily_usdc}")

            rows = load_audit_csv(cfg["audit_csv"])
            pending = find_open_trades(rows, strategy_filter=args.strategy, strategy_prefixes=cfg.get("strategy_prefixes"))

            # Remove already-processed (dedup across scans)
            new_pending = [t for t in pending if t.row_id not in processed_ids]
            stale_pending = [t for t in pending if t.row_id in processed_ids]

            if not pending:
                print("  No OPEN trades in audit CSV.")
            elif not new_pending:
                print(f"  {len(stale_pending)} OPEN trade(s) already processed, nothing new.")
            else:
                print(f"  {len(new_pending)} new OPEN trade(s) (plus {len(stale_pending)} already seen).")

            for trade in new_pending:
                if args.max_trades and trades_done >= args.max_trades:
                    print("  Reached max-trades limit.")
                    break

                if live and remaining_daily < min_usdc:
                    print(f"  Daily cap reached (remaining={remaining_daily:.2f}). Stopping.")
                    break

                result = process_one(trade, client, live, max_usdc, min_usdc, args, cfg)
                append_execution_log(args.log, result)
                append_json_log(args.json_log, result)

                # Real-time per-trade output
                status_icon = {"DRY_RUN": "[~]", "EXECUTED": "[+]", "FAILED": "[!]",
                               "SKIP_NO_TOKEN": "[-]", "SKIP_NO_ASK": "[-]", "SKIP_BELOW_MIN": "[-]",
                               "SKIP_STALE_MARKET": "[-]", "SKIP_SLIPPAGE": "[-]"}.get(result.status, "[?]")
                print(
                    f"  {status_icon} {trade.slug[:55]:55s} | {trade.outcome:6s} | "
                    f"{result.intended_stake:.1f}U | {result.status}"
                )

                if result.status == "EXECUTED":
                    trades_done += 1
                    if live:
                        remaining_daily -= (result.total_cost or 0)

                processed_ids.add(trade.row_id)
                save_seen(args.seen, processed_ids)

                # Brief pause between orders
                time.sleep(1.0)

        except KeyboardInterrupt:
            print("\nStopped.")
            save_seen(args.seen, processed_ids)
            return 130
        except Exception as exc:
            print(f"  scan={scan_id} error: {exc}", file=sys.stderr)

        if args.max_trades and trades_done >= args.max_trades:
            print(f"Reached max_trades={args.max_trades}")
            save_seen(args.seen, processed_ids)
            return 0

        sleep_for = max(0.0, args.interval - (time.time() - started))
        time.sleep(sleep_for)


def run_once(args, cfg, client, live, max_usdc, min_usdc, processed_ids):
    """Single-pass execution."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = load_audit_csv(cfg["audit_csv"])
    pending = find_open_trades(rows, strategy_filter=args.strategy, strategy_prefixes=cfg.get("strategy_prefixes"))
    pending = [t for t in pending if t.row_id not in processed_ids]
    skipped = len(load_audit_csv(cfg["audit_csv"])) - len(pending)

    print(f"[{stamp}] {cfg['label']}: {len(pending)} new OPEN trade(s) (skipped {len(processed_ids)} already seen)")

    for trade in pending:
        stake = min(trade.stake, max_usdc)
        result = process_one(trade, client, live, max_usdc, min_usdc, args, cfg)
        append_execution_log(args.log, result)
        append_json_log(args.json_log, result)
        processed_ids.add(trade.row_id)
        status_icon = {"DRY_RUN": "[~]", "EXECUTED": "[+]", "FAILED": "[!]",
                       "SKIP_NO_TOKEN": "[-]", "SKIP_NO_ASK": "[-]", "SKIP_BELOW_MIN": "[-]",
                       "SKIP_STALE_MARKET": "[-]", "SKIP_SLIPPAGE": "[-]"}.get(result.status, "[?]")
        print(f"  {status_icon} {trade.slug[:55]:55s} | {trade.outcome:6s} | {stake:.1f}U | {result.status}: {result.detail[:80]}")
        time.sleep(0.3)

    save_seen(args.seen, processed_ids)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Done. {len(pending)} trades processed.")


def process_one(
    trade: PendingTrade,
    client: Any,
    live: bool,
    max_usdc: float,
    min_usdc: float,
    args: argparse.Namespace,
    cfg: dict[str, Any],
) -> ExecutionRecord:
    """Process a single pending trade. Returns an ExecutionRecord."""
    ts = datetime.now(timezone.utc).isoformat()

    # ── 1. Cap stake ──
    stake = min(trade.stake, max_usdc)
    if stake < min_usdc:
        return ExecutionRecord(
            ts=ts, mode="LIVE" if live else "DRY",
            strategy=args.strategy, row_id=trade.row_id,
            slug=trade.slug, outcome=trade.outcome,
            intended_stake=stake, ask_at_exec=None,
            total_cost=None, status="SKIP_BELOW_MIN",
            detail=f"stake {stake:.2f} < min {min_usdc:.2f}",
        )

    # ── 2. Resolve token ID ──
    token_id = resolve_token_id(trade)
    if not token_id:
        return ExecutionRecord(
            ts=ts, mode="LIVE" if live else "DRY",
            strategy=args.strategy, row_id=trade.row_id,
            slug=trade.slug, outcome=trade.outcome,
            intended_stake=stake, ask_at_exec=None,
            total_cost=None, status="SKIP_NO_TOKEN",
            detail="Could not resolve token_id from slug + outcome",
        )

    # ── 3. Check market still open ──
    is_open, reason = check_market_still_open(trade.slug)
    if not is_open:
        return ExecutionRecord(
            ts=ts, mode="LIVE" if live else "DRY",
            strategy=args.strategy, row_id=trade.row_id,
            slug=trade.slug, outcome=trade.outcome,
            intended_stake=stake, ask_at_exec=None,
            total_cost=None, status="SKIP_STALE_MARKET",
            detail=f"Market not open: {reason}",
        )

    # ── 4. Check CLOB ask price ──
    ask = best_ask(token_id)
    if ask is None:
        return ExecutionRecord(
            ts=ts, mode="LIVE" if live else "DRY",
            strategy=args.strategy, row_id=trade.row_id,
            slug=trade.slug, outcome=trade.outcome,
            intended_stake=stake, ask_at_exec=None,
            total_cost=None, status="SKIP_NO_ASK",
            detail="No ask price from CLOB",
        )
    if ask > 1.0:
        return ExecutionRecord(
            ts=ts, mode="LIVE" if live else "DRY",
            strategy=args.strategy, row_id=trade.row_id,
            slug=trade.slug, outcome=trade.outcome,
            intended_stake=stake, ask_at_exec=ask,
            total_cost=None, status="SKIP_SLIPPAGE",
            detail=f"Ask {ask:.4f} > 1.0 USDC, unacceptable",
        )

    can_exec, estimated_cost = check_slippage(ask, stake)

    # ── 5. Execute or dry-run ──
    if live and client:
        try:
            response = place_fok_buy(client, token_id, stake, tick_size=args.tick_size)
            ok = response_ok(response)
            if ok:
                return ExecutionRecord(
                    ts=ts, mode="LIVE",
                    strategy=args.strategy, row_id=trade.row_id,
                    slug=trade.slug, outcome=trade.outcome,
                    intended_stake=stake, ask_at_exec=ask,
                    total_cost=stake, status="EXECUTED",
                    detail=f"FOK buy {stake} USDC of {token_id[:12]}... @ ~{ask:.4f}",
                    raw_response=response,
                )
            else:
                return ExecutionRecord(
                    ts=ts, mode="LIVE",
                    strategy=args.strategy, row_id=trade.row_id,
                    slug=trade.slug, outcome=trade.outcome,
                    intended_stake=stake, ask_at_exec=ask,
                    total_cost=None, status="FAILED",
                    detail=f"Order failed: {json.dumps(response)[:300]}",
                    raw_response=response,
                )
        except Exception as exc:
            return ExecutionRecord(
                ts=ts, mode="LIVE",
                strategy=args.strategy, row_id=trade.row_id,
                slug=trade.slug, outcome=trade.outcome,
                intended_stake=stake, ask_at_exec=ask,
                total_cost=None, status="FAILED",
                detail=f"Exception: {exc}",
            )
    else:
        # Dry-run mode
        return ExecutionRecord(
            ts=ts, mode="DRY",
            strategy=args.strategy, row_id=trade.row_id,
            slug=trade.slug, outcome=trade.outcome,
            intended_stake=stake, ask_at_exec=ask,
            total_cost=estimated_cost,
            status="DRY_RUN",
            detail=f"Would buy {stake} USDC of {token_id[:12]}... @ ask {ask:.4f}",
        )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
