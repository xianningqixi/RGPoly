#!/usr/bin/env python3
"""Report pending simulation exposure by strategy and market.

This is read-only. It helps decide where stale pending rows are blocking
final-only ROI validation.
"""

from __future__ import annotations

import argparse
import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from realized_pnl_report import AUDIT_FILES, CHANGE_POINTS, STRATEGY_KEYS, is_realized, row_time_value
from trade_audit import outcome_price

import ai_signal_simulator
import btc_directional_wallet_copy_sim
import creamcream_copy_sim
import smart_wallet_copy_sim
import weather_wallet_copy_sim


ROOT = Path.cwd()
FIELDS = [
    "strategy",
    "event_slug",
    "slug",
    "title",
    "pending_rows",
    "pending_stake",
    "oldest_time",
    "oldest_age_hours",
    "latest_time",
    "outcomes",
    "current_prices",
    "near_final_rows",
    "market_closed",
    "date_hint",
]

LOADERS = {
    "creamcream_copy": creamcream_copy_sim.market_by_slug,
    "smart_wallet_copy": smart_wallet_copy_sim.market_by_slug,
    "btc_directional_copy": btc_directional_wallet_copy_sim.market_by_slug,
    "btc_directional_candidate_copy": btc_directional_wallet_copy_sim.market_by_slug,
    "smart_direction_retest": smart_wallet_copy_sim.market_by_slug,
    "weather_direction_retest": weather_wallet_copy_sim.market_by_slug,
    "weather_wallet_copy": weather_wallet_copy_sim.market_by_slug,
    "ai_signal_copy": ai_signal_simulator.market_loader,
}


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def read_latest(path: Path) -> list[dict[str, str]]:
    full = ROOT / path
    if not full.exists():
        return []
    latest: dict[str, dict[str, str]] = {}
    with full.open("r", encoding="utf-8-sig", newline="") as file:
        for idx, row in enumerate(csv.DictReader(file)):
            latest[row.get("id") or str(idx)] = row
    return list(latest.values())


def read_latest_cutoffs() -> dict[str, datetime]:
    full = ROOT / CHANGE_POINTS
    if not full.exists():
        return {}
    cutoffs: dict[str, datetime] = {}
    with full.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            strategy = row.get("strategy") or ""
            cutoff = parse_dt(row.get("cutoff_ts"))
            if not strategy or cutoff is None:
                continue
            if strategy not in cutoffs or cutoff >= cutoffs[strategy]:
                cutoffs[strategy] = cutoff
    return cutoffs


def date_hint(text: str) -> str:
    patterns = [
        r"(may-\d{1,2}-2026)",
        r"(on-may-\d{1,2})",
        r"(may-\d{1,2})",
        r"(\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01]))",
    ]
    hay = text.lower()
    for pattern in patterns:
        match = re.search(pattern, hay)
        if match:
            return match.group(1)
    return ""


def build_rows() -> list[dict[str, str]]:
    now = datetime.now(timezone.utc)
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    cutoffs = read_latest_cutoffs()
    for label, path in AUDIT_FILES.items():
        strategy = STRATEGY_KEYS[label]
        cutoff = cutoffs.get(strategy, datetime(1970, 1, 1, tzinfo=timezone.utc))
        for row in read_latest(path):
            row_time = parse_dt(row_time_value(row))
            if row_time is None or row_time < cutoff:
                continue
            if is_realized(row):
                continue
            key = (strategy, row.get("event_slug") or "", row.get("slug") or "")
            grouped.setdefault(key, []).append(row)

    rows: list[dict[str, str]] = []
    for (strategy, event_slug, slug), items in grouped.items():
        times = [ts for ts in (parse_dt(row_time_value(row)) for row in items) if ts]
        oldest = min(times) if times else None
        latest = max(times) if times else None
        age_hours = (now - oldest.astimezone(timezone.utc)).total_seconds() / 3600 if oldest else 0.0
        title = next((row.get("title") or "" for row in items if row.get("title")), "")
        outcomes = sorted({row.get("outcome") or "" for row in items if row.get("outcome")})
        current_prices: list[float] = []
        market_closed = ""
        loader = LOADERS.get(strategy)
        market = None
        if loader:
            try:
                market = loader(slug)
            except Exception:
                market = None
        if market:
            market_closed = str(bool(market.get("closed") or market.get("archived"))).upper()
            for row in items:
                price = outcome_price(market, row.get("outcome") or "")
                if price is not None:
                    current_prices.append(price)
        near_final = sum(1 for price in current_prices if price <= 0.005 or price >= 0.995)
        rows.append(
            {
                "strategy": strategy,
                "event_slug": event_slug,
                "slug": slug,
                "title": title,
                "pending_rows": str(len(items)),
                "pending_stake": f"{sum(fnum(row.get('stake')) for row in items):.4f}",
                "oldest_time": oldest.isoformat() if oldest else "",
                "oldest_age_hours": f"{age_hours:.2f}",
                "latest_time": latest.isoformat() if latest else "",
                "outcomes": ";".join(outcomes),
                "current_prices": ";".join(f"{price:.4f}" for price in current_prices[:8]),
                "near_final_rows": str(near_final),
                "market_closed": market_closed,
                "date_hint": date_hint(f"{event_slug} {slug} {title}"),
            }
        )
    rows.sort(key=lambda row: (fnum(row["pending_stake"]), fnum(row["oldest_age_hours"])), reverse=True)
    return rows


def write_csv(rows: list[dict[str, str]], path: Path = ROOT / "pending_exposure_report.csv") -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def render(rows: list[dict[str, str]], limit: int) -> str:
    lines = [
        "# Pending Exposure Report",
        "",
        "Pending rows are not counted as true ROI. Large or stale groups should be backfilled or inspected first.",
        "",
        "| strategy | pending | stake | near-final | closed | oldest | date | prices | outcomes | market |",
        "|---|---:|---:|---:|---|---:|---|---|---|---|",
    ]
    for row in rows[:limit]:
        market = row["title"] or row["slug"] or row["event_slug"]
        lines.append(
            f"| {row['strategy']} | {row['pending_rows']} | {row['pending_stake']}U | "
            f"{row['near_final_rows']} | {row['market_closed']} | {row['oldest_age_hours']}h | "
            f"{row['date_hint']} | {row['current_prices']} | {row['outcomes']} | {market[:90]} |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--limit", type=int, default=30)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = build_rows()
    write_csv(rows)
    text = render(rows, args.limit)
    (ROOT / "pending_exposure_report.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
