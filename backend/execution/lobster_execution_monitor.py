#!/usr/bin/env python3
"""Monitor external executor ("lobster"/OpenClaw) order receipts.

Read-only. This script never places orders. It correlates external execution
receipts with the local simulation audit files so live/external execution can
be monitored against final-only simulated PnL.
"""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path.cwd()
RECEIPTS = ROOT / "external_execution_receipts.csv"
OUTBOX_JSONL = ROOT / "execution_outbox.jsonl"
REPORT_MD = ROOT / "lobster_execution_monitor.md"
REPORT_CSV = ROOT / "lobster_execution_monitor.csv"

ALLOWED_STRATEGIES = {"btc_no_dominant_candidate_copy"}
AUDIT_FILES = {
    "btc_no_dominant_candidate_copy": ROOT / "btc_no_dominant_trade_audit.csv",
    "btc_directional_copy": ROOT / "btc_directional_trade_audit.csv",
    "btc_directional_live_shadow": ROOT / "btc_directional_live_shadow_trade_audit.csv",
    "eth_directional_copy": ROOT / "eth_directional_trade_audit.csv",
    "eth_high_quality_directional_copy": ROOT / "eth_high_quality_directional_trade_audit.csv",
    "weather_high_prob_wallet_copy": ROOT / "weather_high_prob_trade_audit.csv",
    "weather_high_prob_live_shadow": ROOT / "weather_high_prob_live_shadow_trade_audit.csv",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def fnum(value: str | None) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def parse_dt(value: str | None) -> datetime:
    try:
        dt = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def source_id_from_intent(intent_id: str) -> str:
    prefix = "locked_live_preflight:"
    if intent_id.startswith(prefix):
        rest = intent_id[len(prefix):]
        parts = rest.split(":", 1)
        return parts[1] if len(parts) == 2 else ""
    return ""


def normalize_receipt(receipt: dict[str, str]) -> dict[str, str]:
    """Support both the original 11-column receipt format and newer executor rows.

    New OpenClaw rows were appended under the old header, so fields after
    ticket_id are shifted and the extra values land under DictReader's None key.
    """
    status = (receipt.get("execution_status") or "").upper()
    if status in {"EXECUTED", "MARKET_CLOSED", "EXCEPTION", "REDEEMED", "SETTLED", "CLAIMED"}:
        return receipt

    extras = receipt.get(None) or []  # type: ignore[arg-type]
    if not isinstance(extras, list):
        extras = []
    action = receipt.get("actual_order_id") or ""
    outcome = receipt.get("actual_fill_price") or ""
    shifted_status = extras[1] if len(extras) > 1 else ""
    if action not in {"BUY", "SELL"} or shifted_status.upper() not in {"EXECUTED", "MARKET_CLOSED", "EXCEPTION"}:
        return receipt

    source_strategy = receipt.get("intent_id") or ""
    source_id = receipt.get("source_strategy") or ""
    tx_hash = extras[2] if len(extras) > 2 else ""
    error = extras[3] if len(extras) > 3 else ""
    notes = f"Tx: {tx_hash}" if tx_hash else error
    normalized = dict(receipt)
    normalized.update(
        {
            "intent_id": f"locked_live_preflight:{source_strategy}:{source_id}",
            "source_strategy": source_strategy,
            "execution_status": shifted_status.upper(),
            "actual_order_id": tx_hash,
            "actual_fill_price": receipt.get("notes", ""),
            "actual_shares": extras[0] if extras else "",
            "actual_spent_usdc": receipt.get("actual_spent_usdc", ""),
            "actual_fee_usdc": "",
            "notes": notes,
            "_source_id": source_id,
            "_wallet_name": receipt.get("execution_status", ""),
            "_action": action,
            "_outcome": outcome,
            "_sim_fill_price": receipt.get("actual_fee_usdc", ""),
            "_source_to_ask_gap": extras[4] if len(extras) > 4 else "",
        }
    )
    return normalized


def load_tickets() -> dict[str, dict[str, str]]:
    tickets: dict[str, dict[str, str]] = {}
    if not OUTBOX_JSONL.exists():
        return tickets
    with OUTBOX_JSONL.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                ticket = obj.get("ticket", {})
                ticket_id = ticket.get("ticket_id") or ""
                if ticket_id:
                    tickets[ticket_id] = ticket
            except Exception:
                continue
    return tickets


def load_latest_audit_rows() -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for path in AUDIT_FILES.values():
        for row in read_csv(path):
            row_id = row.get("id") or row.get("source_id") or ""
            if not row_id:
                continue
            existing = rows.get(row_id)
            if existing is None or parse_dt(row.get("audit_ts") or row.get("detected_time")) >= parse_dt(
                existing.get("audit_ts") or existing.get("detected_time")
            ):
                rows[row_id] = row
    return rows


def final_result(row: dict[str, str] | None) -> str:
    if not row:
        return "NO_AUDIT_MATCH"
    result = row.get("final_result") or ""
    if result in {"WIN", "LOSS"}:
        return result
    if row.get("status") == "RESOLVED" and row.get("result") in {"WIN", "LOSS"}:
        return row.get("result") or "PENDING"
    return "PENDING"


def redemption_confirmed(receipt: dict[str, str]) -> bool:
    status = (receipt.get("execution_status") or "").upper()
    notes = (receipt.get("notes") or "").upper()
    return status in {"REDEEMED", "SETTLED", "CLAIMED"} or any(
        marker in notes for marker in ("REDEEM", "SETTLED", "CLAIMED", "PAYOUT")
    )


def final_pnl(row: dict[str, str] | None) -> float:
    if not row:
        return 0.0
    if row.get("fee_adjusted_final_pnl") not in {"", None}:
        return fnum(row.get("fee_adjusted_final_pnl"))
    if row.get("slippage_final_pnl") not in {"", None}:
        return fnum(row.get("slippage_final_pnl"))
    if row.get("status") == "RESOLVED" and row.get("pnl") not in {"", None}:
        return fnum(row.get("pnl"))
    return 0.0


def build_rows() -> list[dict[str, str]]:
    receipts = [normalize_receipt(row) for row in read_csv(RECEIPTS)]
    tickets = load_tickets()
    audits = load_latest_audit_rows()
    out: list[dict[str, str]] = []
    for receipt in receipts:
        ticket = tickets.get(receipt.get("ticket_id", ""), {})
        strategy = receipt.get("source_strategy") or ticket.get("source_strategy") or ""
        source_id = receipt.get("_source_id") or source_id_from_intent(receipt.get("intent_id") or ticket.get("intent_id") or "")
        audit = audits.get(source_id)
        status = receipt.get("execution_status") or ""
        result = final_result(audit)
        redeem_confirmed = redemption_confirmed(receipt)
        pnl = final_pnl(audit) if status == "EXECUTED" and result in {"WIN", "LOSS"} and redeem_confirmed else 0.0
        out.append(
            {
                "receipt_ts": receipt.get("receipt_ts", ""),
                "ticket_id": receipt.get("ticket_id", ""),
                "strategy": strategy,
                "authorization": "AUTHORIZED_COPY" if strategy in ALLOWED_STRATEGIES else "UNAUTHORIZED_OR_PAUSED",
                "execution_status": status,
                "wallet_name": receipt.get("_wallet_name") or ticket.get("wallet_name") or (audit or {}).get("wallet_name", ""),
                "action": receipt.get("_action") or ticket.get("action") or "",
                "outcome": receipt.get("_outcome") or ticket.get("outcome") or (audit or {}).get("outcome", ""),
                "stake_usdc": receipt.get("actual_spent_usdc") or ticket.get("intended_stake_usdc") or "",
                "sim_fill_price": receipt.get("_sim_fill_price") or ticket.get("sim_fill_price") or (audit or {}).get("sim_fill_price", ""),
                "actual_order_id": receipt.get("actual_order_id", ""),
                "tx": receipt.get("notes", ""),
                "title": ticket.get("title") or (audit or {}).get("title", ""),
                "source_id": source_id,
                "audit_final_result": result,
                "redeem_status": "CONFIRMED" if redeem_confirmed else "NOT_CONFIRMED",
                "final_result": result if redeem_confirmed else "NOT_REDEEMED",
                "final_pnl": f"{pnl:.4f}",
            }
        )
    out.sort(key=lambda row: parse_dt(row["receipt_ts"]))
    return out


def write_csv_report(rows: list[dict[str, str]]) -> None:
    fields = [
        "receipt_ts",
        "ticket_id",
        "strategy",
        "authorization",
        "execution_status",
        "wallet_name",
        "action",
        "outcome",
        "stake_usdc",
        "sim_fill_price",
        "actual_order_id",
        "tx",
        "title",
        "source_id",
        "audit_final_result",
        "redeem_status",
        "final_result",
        "final_pnl",
    ]
    with REPORT_CSV.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def render(rows: list[dict[str, str]]) -> str:
    now = datetime.now(timezone.utc)
    executed = [row for row in rows if row["execution_status"] == "EXECUTED"]
    authorized = [row for row in executed if row["authorization"] == "AUTHORIZED_COPY"]
    unauthorized = [row for row in executed if row["authorization"] != "AUTHORIZED_COPY"]
    audit_final = [row for row in authorized if row["audit_final_result"] in {"WIN", "LOSS"}]
    realized = [row for row in authorized if row["redeem_status"] == "CONFIRMED" and row["audit_final_result"] in {"WIN", "LOSS"}]
    pending = [row for row in authorized if row["final_result"] == "PENDING"]
    pnl = sum(fnum(row["final_pnl"]) for row in realized)
    stake = sum(fnum(row["stake_usdc"]) for row in realized)
    roi = pnl / stake * 100 if stake else 0.0
    last_24h = [row for row in rows if parse_dt(row["receipt_ts"]) >= now - timedelta(hours=24)]
    by_status = Counter(row["execution_status"] for row in rows)
    by_strategy = Counter(f"{row['strategy']} | {row['execution_status']}" for row in rows)
    strategy_pnl: dict[str, float] = defaultdict(float)
    for row in realized:
        strategy_pnl[row["strategy"]] += fnum(row["final_pnl"])

    lines = [
        "# Lobster/OpenClaw Execution Monitor",
        "",
        "Read-only monitor. It does not place orders.",
        "",
        f"- generated_utc: {now.isoformat()}",
        f"- allowed copy strategies: {', '.join(sorted(ALLOWED_STRATEGIES))}",
        f"- total receipts: {len(rows)}",
        f"- executed receipts: {len(executed)}",
        f"- authorized executed copy trades: {len(authorized)}",
        f"- unauthorized/paused executed trades: {len(unauthorized)}",
        f"- authorized realized trades: {len(realized)}",
        f"- authorized audit-final but not redeem-confirmed trades: {len(audit_final) - len(realized)}",
        f"- authorized pending/unconfirmed trades: {len(authorized) - len(realized)}",
        f"- authorized redeem-confirmed PnL: {pnl:.4f}U",
        f"- authorized redeem-confirmed ROI: {roi:.2f}%",
        f"- receipts in last 24h: {len(last_24h)}",
        "",
        "## Status Breakdown",
    ]
    for key, count in by_status.most_common():
        lines.append(f"- {count}: {key}")
    lines.extend(["", "## Strategy Breakdown"])
    for key, count in by_strategy.most_common():
        lines.append(f"- {count}: {key}")
    lines.extend(["", "## Authorized Redeem-Confirmed Strategy PnL"])
    if strategy_pnl:
        for strategy, value in sorted(strategy_pnl.items()):
            lines.append(f"- {strategy}: {value:.4f}U")
    else:
        lines.append("- no authorized finalized external trades yet")
    lines.extend(["", "## Unauthorized Or Paused Executed Trades"])
    if unauthorized:
        lines.extend(["| time | strategy | status | stake | title |", "|---|---|---:|---:|---|"])
        for row in unauthorized[-20:]:
            lines.append(
                f"| {row['receipt_ts']} | {row['strategy']} | {row['execution_status']} | "
                f"{row['stake_usdc']} | {row['title']} |"
            )
    else:
        lines.append("- none")
    lines.extend(["", "## Latest Executed Trades"])
    if executed:
        lines.extend(["| time | auth | strategy | wallet | outcome | stake | audit final | redeem | pnl | title |", "|---|---|---|---|---|---:|---|---|---:|---|"])
        for row in executed[-20:]:
            lines.append(
                f"| {row['receipt_ts']} | {row['authorization']} | {row['strategy']} | {row['wallet_name']} | "
                f"{row['outcome']} | {row['stake_usdc']} | {row['audit_final_result']} | {row['redeem_status']} | {row['final_pnl']} | {row['title']} |"
            )
    else:
        lines.append("- no executed receipts")
    return "\n".join(lines) + "\n"


def main() -> int:
    rows = build_rows()
    write_csv_report(rows)
    text = render(rows)
    REPORT_MD.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
