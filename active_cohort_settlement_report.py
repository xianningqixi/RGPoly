#!/usr/bin/env python3
"""Settlement timing diagnostics for the current active cohort.

This report is read-only. It helps distinguish normal pending positions from
positions that appear closed/resolved but have not been finalized in the local
audit log yet.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import audit_backtest
from btc_directional_wallet_copy_sim import market_by_slug, market_end_time
from realized_pnl_report import row_time_value


ROOT = Path(__file__).resolve().parent
CURRENT_CONFIG = ROOT / "current_config_report.csv"
OUT_CSV = ROOT / "active_cohort_settlement_report.csv"
OUT_MD = ROOT / "active_cohort_settlement_report.md"

FIELDS = [
    "strategy",
    "slug",
    "outcome",
    "status",
    "title",
    "stake",
    "detected_time",
    "market_end_time",
    "hours_to_end",
    "market_closed",
    "market_active",
    "current_price",
    "diagnostic",
]


def fnum(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def active_configs() -> list[dict[str, str]]:
    return [row for row in read_csv(CURRENT_CONFIG) if row.get("intended_state") != "PAUSED"]


def active_rows() -> list[tuple[str, dict[str, str]]]:
    out: list[tuple[str, dict[str, str]]] = []
    for config in active_configs():
        strategy = config.get("strategy_key") or ""
        path = audit_backtest.AUDIT_FILES.get(strategy)
        if not path:
            continue
        cutoff = audit_backtest.parse_dt(config.get("cutoff_ts"))
        for row in audit_backtest.latest_rows(audit_backtest.read_rows(path)):
            if audit_backtest.parse_dt(row_time_value(row)) < cutoff:
                continue
            if audit_backtest.is_final(row):
                continue
            out.append((strategy, row))
    out.sort(key=lambda item: audit_backtest.parse_dt(row_time_value(item[1])))
    return out


def bool_text(value: Any) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    text = str(value or "").strip().lower()
    if text in {"true", "1", "yes"}:
        return "TRUE"
    if text in {"false", "0", "no"}:
        return "FALSE"
    return ""


def diagnostic(hours_to_end: float | None, closed: str, status: str) -> str:
    if status in {"FINAL"}:
        return "FINAL"
    if closed == "TRUE":
        return "CHECK_FINAL_BACKFILL"
    if hours_to_end is None:
        return "UNKNOWN_END_TIME"
    if hours_to_end <= -1:
        return "PAST_END_WAITING_RESOLUTION"
    if hours_to_end <= 3:
        return "NEAR_END"
    return "WAITING"


def build_rows() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    for strategy, row in active_rows():
        slug = row.get("slug") or ""
        market = None
        try:
            market = market_by_slug(slug)
        except Exception:
            market = None
        end = market_end_time(market) if market else None
        if end and end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        hours_to_end = (end.astimezone(timezone.utc) - now).total_seconds() / 3600 if end else None
        closed = bool_text((market or {}).get("closed"))
        active = bool_text((market or {}).get("active"))
        status = row.get("status") or ""
        rows.append(
            {
                "strategy": strategy,
                "slug": slug,
                "outcome": row.get("outcome") or "",
                "status": status,
                "title": row.get("title") or "",
                "stake": fnum(row.get("stake")),
                "detected_time": row.get("detected_time") or "",
                "market_end_time": end.isoformat() if end else "",
                "hours_to_end": hours_to_end if hours_to_end is not None else "",
                "market_closed": closed,
                "market_active": active,
                "current_price": fnum(row.get("final_price"), fnum(row.get("price_1h"), fnum(row.get("price_10m"), fnum(row.get("price_2m"))))),
                "diagnostic": diagnostic(hours_to_end, closed, status),
            }
        )
    return rows


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["stake"] = f"{fnum(out.get('stake')):.6f}"
            if out.get("hours_to_end") != "":
                out["hours_to_end"] = f"{fnum(out.get('hours_to_end')):.6f}"
            out["current_price"] = f"{fnum(out.get('current_price')):.6f}"
            writer.writerow({field: out.get(field, "") for field in FIELDS})


def render(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Active Cohort Settlement Report",
        "",
        "Read-only timing diagnostics for non-final active-cohort rows.",
        "",
        "| strategy | diagnostic | outcome | stake | hours to end | closed | active | current | market |",
        "|---|---|---|---:|---:|---|---|---:|---|",
    ]
    for row in rows:
        hours = row["hours_to_end"]
        hours_text = "" if hours == "" else f"{fnum(hours):.2f}"
        lines.append(
            f"| {row['strategy']} | {row['diagnostic']} | {row['outcome']} | {fnum(row['stake']):.2f}U | "
            f"{hours_text} | {row['market_closed']} | {row['market_active']} | {fnum(row['current_price']):.4f} | "
            f"{row['title']} |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--csv", type=Path, default=OUT_CSV)
    parser.add_argument("--md", type=Path, default=OUT_MD)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = build_rows()
    write_csv(rows, args.csv)
    text = render(rows)
    args.md.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
