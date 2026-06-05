#!/usr/bin/env python3
"""Backtest simulated Polymarket entries from local audit logs.

This is intentionally read-only. It replays rows that were already captured in
`*_trade_audit.csv` files and reports only finalized `slippage_final_pnl`.
Pending rows are counted for diagnostics but never included in realized ROI.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent

AUDIT_FILES = {
    "weather_direction_retest": ROOT / "weather_direction_retest_trade_audit.csv",
    "weather_wallet_copy": ROOT / "weather_wallet_trade_audit.csv",
    "btc_directional_copy": ROOT / "btc_directional_trade_audit.csv",
    "eth_directional_copy": ROOT / "eth_directional_trade_audit.csv",
    "sol_directional_copy": ROOT / "sol_directional_trade_audit.csv",
    "bnb_directional_copy": ROOT / "bnb_directional_trade_audit.csv",
    "btc_directional_candidate_copy": ROOT / "btc_directional_candidate_trade_audit.csv",
    "weather_high_prob_wallet_copy": ROOT / "weather_high_prob_trade_audit.csv",
    "btc_directional_live_shadow": ROOT / "btc_directional_live_shadow_trade_audit.csv",
    "weather_high_prob_live_shadow": ROOT / "weather_high_prob_live_shadow_trade_audit.csv",
    "btc_no_dominant_candidate_copy": ROOT / "btc_no_dominant_trade_audit.csv",
    "eth_high_quality_directional_copy": ROOT / "eth_high_quality_directional_trade_audit.csv",
    "ai_signal_copy": ROOT / "ai_signal_trade_audit.csv",
    "smart_wallet_copy": ROOT / "smart_wallet_trade_audit.csv",
    "smart_direction_retest": ROOT / "smart_direction_retest_trade_audit.csv",
    "creamcream_copy": ROOT / "creamcream_trade_audit.csv",
}


def fnum(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def parse_dt(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    text = value.strip()
    if not text:
        return datetime.min.replace(tzinfo=timezone.utc)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def latest_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep the latest audit update for each trade id."""
    by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        key = row.get("id") or "|".join(
            [
                row.get("strategy", ""),
                row.get("wallet_name", ""),
                row.get("slug", ""),
                row.get("outcome", ""),
                row.get("signal_time", ""),
            ]
        )
        if not key:
            continue
        prev = by_id.get(key)
        if prev is None or parse_dt(row.get("audit_ts")) >= parse_dt(prev.get("audit_ts")):
            by_id[key] = row
    return list(by_id.values())


def row_time(row: dict[str, str]) -> datetime:
    return max(parse_dt(row.get("signal_time")), parse_dt(row.get("detected_time")), parse_dt(row.get("audit_ts")))


def price_bucket(price: float) -> str:
    if price < 0.1:
        return "0.0-0.1"
    if price >= 1.0:
        return "1.0+"
    start = int(price * 10) / 10
    return f"{start:.1f}-{start + 0.1:.1f}"


def source_age_sec(row: dict[str, str]) -> float:
    signal = parse_dt(row.get("signal_time"))
    detected = parse_dt(row.get("detected_time"))
    if signal == datetime.min.replace(tzinfo=timezone.utc) or detected == datetime.min.replace(tzinfo=timezone.utc):
        return 0.0
    return max(0.0, (detected - signal).total_seconds())


def source_to_ask_gap(row: dict[str, str]) -> float:
    ask = fnum(row.get("best_ask"), fnum(row.get("sim_fill_price")))
    source = fnum(row.get("source_price"))
    if ask <= 0 or source <= 0:
        return 0.0
    return max(0.0, ask - source)


def is_final(row: dict[str, str]) -> bool:
    status = (row.get("status") or "").upper()
    final = (row.get("final_result") or "").upper()
    return status == "FINAL" or final in {"WIN", "LOSS", "PUSH"}


def final_pnl(row: dict[str, str], stake_usdc: float) -> float:
    original_stake = fnum(row.get("stake"))
    pnl = fnum(row.get("slippage_final_pnl"), fnum(row.get("final_pnl")))
    if original_stake <= 0:
        return pnl
    return pnl * stake_usdc / original_stake


@dataclass
class BacktestResult:
    name: str
    total_rows: int
    selected_rows: int
    final_rows: int
    pending_rows: int
    wins: int
    losses: int
    stake: float
    pnl: float
    roi: float
    max_drawdown: float
    avg_slippage_bps: float
    avg_source_age_sec: float
    avg_source_to_ask_gap: float


def include_row(row: dict[str, str], args: argparse.Namespace) -> bool:
    if args.wallet and (row.get("wallet_name") or "") not in args.wallet:
        return False
    if args.outcome and (row.get("outcome") or "") not in args.outcome:
        return False
    fill = fnum(row.get("sim_fill_price"), fnum(row.get("best_ask")))
    source = fnum(row.get("source_price"))
    if fill < args.min_entry_price or fill > args.max_entry_price:
        return False
    if source < args.min_source_price or source > args.max_source_price:
        return False
    if args.price_bucket and price_bucket(source) not in args.price_bucket:
        return False
    if fnum(row.get("slippage_bps")) > args.max_slippage_bps:
        return False
    if source_to_ask_gap(row) > args.max_source_to_ask_gap:
        return False
    if fnum(row.get("ask_depth_usdc")) < args.min_ask_depth_usdc:
        return False
    if source_age_sec(row) > args.max_source_age_sec:
        return False
    if args.require_live_fill and (row.get("would_live_fill") or "").upper() not in {"YES", "TRUE", "1"}:
        return False
    estimated_q = row.get("estimated_q")
    if estimated_q not in (None, ""):
        if fnum(estimated_q) - fill < args.min_direction_edge:
            return False
    return True


def max_drawdown(pnls: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def run_backtest(name: str, rows: list[dict[str, str]], args: argparse.Namespace) -> BacktestResult:
    filtered = [row for row in latest_rows(rows) if row_time(row) >= args.since_dt and include_row(row, args)]
    filtered.sort(key=row_time)
    final_rows = [row for row in filtered if is_final(row)]
    pending_rows = [row for row in filtered if not is_final(row)]
    pnls = [final_pnl(row, args.stake_usdc) for row in final_rows]
    stake = len(final_rows) * args.stake_usdc
    pnl = sum(pnls)
    wins = sum(1 for value in pnls if value > 0)
    losses = sum(1 for value in pnls if value < 0)
    return BacktestResult(
        name=name,
        total_rows=len(latest_rows(rows)),
        selected_rows=len(filtered),
        final_rows=len(final_rows),
        pending_rows=len(pending_rows),
        wins=wins,
        losses=losses,
        stake=stake,
        pnl=pnl,
        roi=pnl / stake * 100 if stake else 0.0,
        max_drawdown=max_drawdown(pnls),
        avg_slippage_bps=sum(fnum(row.get("slippage_bps")) for row in final_rows) / len(final_rows) if final_rows else 0.0,
        avg_source_age_sec=sum(source_age_sec(row) for row in final_rows) / len(final_rows) if final_rows else 0.0,
        avg_source_to_ask_gap=sum(source_to_ask_gap(row) for row in final_rows) / len(final_rows) if final_rows else 0.0,
    )


def write_csv(results: list[BacktestResult], path: Path) -> None:
    fields = list(BacktestResult.__dataclass_fields__.keys())
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for result in results:
            row = result.__dict__.copy()
            for key in ["stake", "pnl", "roi", "max_drawdown", "avg_slippage_bps", "avg_source_age_sec", "avg_source_to_ask_gap"]:
                row[key] = f"{row[key]:.6f}"
            writer.writerow(row)


def render(results: list[BacktestResult], args: argparse.Namespace) -> str:
    lines = [
        "# Audit Backtest Report",
        "",
        "Read-only historical replay. Realized ROI uses finalized slippage_final_pnl only.",
        "",
        f"- stake_usdc: {args.stake_usdc:.2f}",
        f"- since: {args.since}",
        f"- max_slippage_bps: {args.max_slippage_bps:.0f}",
        f"- max_source_to_ask_gap: {args.max_source_to_ask_gap:.4f}",
        f"- max_source_age_sec: {args.max_source_age_sec:.0f}",
        f"- min_ask_depth_usdc: {args.min_ask_depth_usdc:.2f}",
        "",
        "| strategy | selected | final | pending | W/L | stake | pnl | roi | max DD | avg slip | avg age | avg gap |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in results:
        lines.append(
            f"| {result.name} | {result.selected_rows} | {result.final_rows} | {result.pending_rows} | "
            f"{result.wins}/{result.losses} | {result.stake:.2f} | {result.pnl:.4f} | {result.roi:.2f}% | "
            f"{result.max_drawdown:.4f} | {result.avg_slippage_bps:.1f} | {result.avg_source_age_sec:.1f}s | "
            f"{result.avg_source_to_ask_gap:.4f} |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backtest local audit logs with final-only PnL")
    parser.add_argument("--strategy", action="append", choices=sorted(AUDIT_FILES), help="Strategy to test; defaults to all")
    parser.add_argument("--stake-usdc", type=float, default=10.0)
    parser.add_argument("--since", default="1970-01-01T00:00:00+00:00")
    parser.add_argument("--wallet", action="append", default=[])
    parser.add_argument("--outcome", action="append", default=[])
    parser.add_argument("--price-bucket", action="append", default=[])
    parser.add_argument("--min-source-price", type=float, default=0.0)
    parser.add_argument("--max-source-price", type=float, default=1.0)
    parser.add_argument("--min-entry-price", type=float, default=0.0)
    parser.add_argument("--max-entry-price", type=float, default=1.0)
    parser.add_argument("--max-slippage-bps", type=float, default=10_000.0)
    parser.add_argument("--max-source-to-ask-gap", type=float, default=1.0)
    parser.add_argument("--max-source-age-sec", type=float, default=1_000_000.0)
    parser.add_argument("--min-ask-depth-usdc", type=float, default=0.0)
    parser.add_argument("--min-direction-edge", type=float, default=-1.0)
    parser.add_argument("--require-live-fill", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--csv", type=Path, default=ROOT / "audit_backtest_report.csv")
    parser.add_argument("--md", type=Path, default=ROOT / "audit_backtest_report.md")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.since_dt = parse_dt(args.since)
    strategies = args.strategy or sorted(AUDIT_FILES)
    results = [run_backtest(name, read_rows(AUDIT_FILES[name]), args) for name in strategies]
    write_csv(results, args.csv)
    text = render(results, args)
    args.md.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
