#!/usr/bin/env python3
"""Route preflight-passed intents to a manual/external execution outbox.

This script does not place orders and does not read credentials. It converts
`live_order_intents.csv` rows with PREVIEW_ONLY_WOULD_PLACE into stable files
that a human or a separate executor can consume.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path.cwd()

OUTBOX_FIELDS = [
    "exported_at",
    "ticket_id",
    "intent_id",
    "status",
    "source_strategy",
    "source_id",
    "wallet_name",
    "action",
    "order_type",
    "token_id",
    "tick_size",
    "neg_risk",
    "order_price_min",
    "order_price_max",
    "outcome",
    "intended_stake_usdc",
    "sim_fill_price",
    "best_bid",
    "best_ask",
    "source_to_ask_gap",
    "ask_depth_usdc",
    "fee_usdc",
    "total_cost_usdc",
    "slippage_bps",
    "btc_spot",
    "btc_momentum_bps",
    "url",
    "title",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def parse_dt(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write_csv(rows: list[dict[str, Any]], path: Path, fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    if isinstance(data, list):
        return {str(item) for item in data}
    if isinstance(data, dict):
        return {str(key) for key, value in data.items() if value}
    return set()


def save_seen(path: Path, seen: set[str]) -> None:
    path.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")


def latest_by_intent(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        intent_id = row.get("intent_id") or ""
        if not intent_id:
            continue
        previous = out.get(intent_id)
        if previous is None:
            out[intent_id] = row
            continue
        current_ts = parse_dt(row.get("ts")) or datetime.min.replace(tzinfo=timezone.utc)
        previous_ts = parse_dt(previous.get("ts")) or datetime.min.replace(tzinfo=timezone.utc)
        if current_ts >= previous_ts:
            out[intent_id] = row
    return out


def ticket_id(row: dict[str, str]) -> str:
    raw = row.get("intent_id") or f"{row.get('source_strategy','')}:{row.get('source_id','')}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return "ticket_" + digest


def build_ticket(row: dict[str, str]) -> dict[str, Any]:
    return {
        "exported_at": now_utc(),
        "ticket_id": ticket_id(row),
        "intent_id": row.get("intent_id", ""),
        "status": "READY_FOR_MANUAL_OR_EXTERNAL_EXECUTION",
        "source_strategy": row.get("source_strategy", ""),
        "source_id": row.get("source_id", ""),
        "wallet_name": row.get("wallet_name", ""),
        "action": "BUY",
        "order_type": "FOK_MARKET_BUY_PREVIEW",
        "token_id": row.get("token_id", ""),
        "tick_size": row.get("tick_size", ""),
        "neg_risk": row.get("neg_risk", ""),
        "order_price_min": row.get("order_price_min", ""),
        "order_price_max": row.get("order_price_max", ""),
        "outcome": row.get("outcome", ""),
        "intended_stake_usdc": f"{fnum(row.get('intended_stake_usdc')):.4f}",
        "sim_fill_price": f"{fnum(row.get('sim_fill_price')):.6f}",
        "best_bid": row.get("best_bid", ""),
        "best_ask": row.get("best_ask", ""),
        "source_to_ask_gap": row.get("source_to_ask_gap", ""),
        "ask_depth_usdc": f"{fnum(row.get('ask_depth_usdc')):.4f}",
        "fee_usdc": f"{fnum(row.get('fee_usdc')):.6f}",
        "total_cost_usdc": f"{fnum(row.get('total_cost_usdc')):.6f}",
        "slippage_bps": f"{fnum(row.get('slippage_bps')):.2f}",
        "btc_spot": row.get("btc_spot", ""),
        "btc_momentum_bps": row.get("btc_momentum_bps", ""),
        "url": row.get("url", ""),
        "title": row.get("title", ""),
    }


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("a", encoding="utf-8") as file:
        for row in rows:
            payload = {
                "schema_version": "polymarket.execution_intent.v1",
                "safety": {
                    "does_not_place_order": True,
                    "credential_required_by_this_script": False,
                },
                "ticket": row,
            }
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def render_manual_tickets(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Manual Execution Tickets",
        "",
        "These tickets are generated from PREVIEW_ONLY_WOULD_PLACE rows. This file does not place orders.",
        "",
    ]
    if not rows:
        lines.append("No fresh tickets.")
        return "\n".join(lines)
    for index, row in enumerate(rows, start=1):
        lines.extend(
            [
                f"## Ticket {index}: {row['source_strategy']}",
                "",
                f"- ticket_id: `{row['ticket_id']}`",
                f"- wallet: `{row['wallet_name']}`",
                f"- action: `BUY {row['outcome']}`",
                f"- stake: `{row['intended_stake_usdc']} USDC`",
                f"- simulated fill: `{row['sim_fill_price']}`",
                f"- best ask: `{row['best_ask']}`",
                f"- depth: `{row['ask_depth_usdc']} USDC`",
                f"- fee: `{row['fee_usdc']} USDC`",
                f"- total cost: `{row['total_cost_usdc']} USDC`",
                f"- slippage: `{row['slippage_bps']} bps`",
                f"- token_id: `{row['token_id']}`",
                f"- tick_size: `{row['tick_size']}`",
                f"- neg_risk: `{row['neg_risk']}`",
                f"- valid price range: `{row['order_price_min']} - {row['order_price_max']}`",
                f"- market: {row['title']}",
                f"- url: {row['url']}",
                "",
            ]
        )
    return "\n".join(lines)


def route_once(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows = list(latest_by_intent(read_csv(args.input)).values())
    allowed_strategies = {item.strip() for item in (args.allowed_strategy or []) if item.strip()}
    seen = set() if args.rebuild else load_seen(args.seen)
    now = datetime.now(timezone.utc)
    fresh: list[dict[str, Any]] = []
    for row in rows:
        intent_id = row.get("intent_id") or ""
        if not intent_id:
            continue
        if allowed_strategies and row.get("source_strategy", "") not in allowed_strategies:
            continue
        if row.get("status") != "PREVIEW_ONLY_WOULD_PLACE":
            continue
        if row.get("token_id") in {"", None}:
            continue
        stake = fnum(row.get("intended_stake_usdc"))
        if args.min_stake_usdc is not None and stake < args.min_stake_usdc:
            continue
        if args.max_stake_usdc is not None and stake > args.max_stake_usdc:
            continue
        ts = parse_dt(row.get("ts"))
        if ts and (now - ts.astimezone(timezone.utc)).total_seconds() > args.max_intent_age_sec:
            continue
        if intent_id in seen:
            continue
        fresh.append(build_ticket(row))
        seen.add(intent_id)

    append_jsonl(args.outbox_jsonl, fresh)
    existing = read_csv(args.outbox_csv) if args.outbox_csv.exists() and not args.rebuild else []
    merged = existing + fresh
    write_csv(merged, args.outbox_csv, OUTBOX_FIELDS)
    args.manual_md.write_text(render_manual_tickets(fresh) + "\n", encoding="utf-8")
    save_seen(args.seen, seen)
    return fresh


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Route preflight-passed intents to execution outbox files")
    parser.add_argument("--input", type=Path, default=ROOT / "live_order_intents.csv")
    parser.add_argument("--outbox-jsonl", type=Path, default=ROOT / "execution_outbox.jsonl")
    parser.add_argument("--outbox-csv", type=Path, default=ROOT / "execution_outbox.csv")
    parser.add_argument("--manual-md", type=Path, default=ROOT / "manual_order_tickets.md")
    parser.add_argument("--seen", type=Path, default=ROOT / "execution_outbox_seen.json")
    parser.add_argument("--max-intent-age-sec", type=float, default=300.0)
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--allowed-strategy", action="append", default=[])
    parser.add_argument("--min-stake-usdc", type=float)
    parser.add_argument("--max-stake-usdc", type=float)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--rebuild", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    while True:
        try:
            rows = route_once(args)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] routed execution tickets: {len(rows)}", flush=True)
        except Exception as exc:
            print(f"execution_intent_router error: {exc}", flush=True)
        if args.once:
            return 0
        time.sleep(max(1.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
