#!/usr/bin/env python3
"""Report whether simulation trades use strict live-like execution fields."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent

AUDITS = {
    "creamcream_copy": ROOT / "creamcream_trade_audit.csv",
    "smart_wallet_copy": ROOT / "smart_wallet_trade_audit.csv",
    "btc_directional_copy": ROOT / "btc_directional_trade_audit.csv",
    "eth_directional_copy": ROOT / "eth_directional_trade_audit.csv",
    "sol_directional_copy": ROOT / "sol_directional_trade_audit.csv",
    "bnb_directional_copy": ROOT / "bnb_directional_trade_audit.csv",
    "btc_directional_candidate_copy": ROOT / "btc_directional_candidate_trade_audit.csv",
    "smart_direction_retest": ROOT / "smart_direction_retest_trade_audit.csv",
    "weather_direction_retest": ROOT / "weather_direction_retest_trade_audit.csv",
    "weather_high_prob_wallet_copy": ROOT / "weather_high_prob_trade_audit.csv",
    "btc_directional_live_shadow": ROOT / "btc_directional_live_shadow_trade_audit.csv",
    "weather_high_prob_live_shadow": ROOT / "weather_high_prob_live_shadow_trade_audit.csv",
    "btc_no_dominant_candidate_copy": ROOT / "btc_no_dominant_trade_audit.csv",
    "eth_high_quality_directional_copy": ROOT / "eth_high_quality_directional_trade_audit.csv",
    "weather_wallet_copy": ROOT / "weather_wallet_trade_audit.csv",
    "ai_signal_copy": ROOT / "ai_signal_trade_audit.csv",
}

FIELDS = [
    "strategy",
    "rows",
    "strict_rows",
    "strict_pct",
    "full_fill_rows",
    "fee_rows",
    "missing_token_rows",
    "missing_cost_rows",
    "legacy_rows",
    "status",
]


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def is_strict(row: dict[str, str]) -> bool:
    return (
        row.get("execution_source") == "REALTIME_ORDERBOOK"
        and row.get("token_id") not in {"", None}
        and row.get("fill_status") == "FULL"
        and row.get("would_live_fill") == "YES"
        and fnum(row.get("spent_usdc")) > 0
        and fnum(row.get("total_cost_usdc")) > 0
    )


def summarize(strategy: str, path: Path) -> dict[str, Any]:
    rows = list(read_csv(path))
    strict_rows = [row for row in rows if is_strict(row)]
    full_fill = [row for row in rows if row.get("fill_status") == "FULL" or row.get("would_live_fill") == "YES"]
    fee_rows = [row for row in rows if fnum(row.get("fee_rate")) > 0 and fnum(row.get("fee_usdc")) >= 0]
    missing_token = [row for row in rows if row.get("token_id") in {"", None}]
    missing_cost = [row for row in rows if fnum(row.get("spent_usdc")) <= 0 or fnum(row.get("total_cost_usdc")) <= 0]
    legacy = [row for row in rows if row.get("execution_source") != "REALTIME_ORDERBOOK"]
    pct = len(strict_rows) / len(rows) * 100 if rows else 0.0
    if not rows:
        status = "NO_ROWS"
    elif pct >= 99:
        status = "STRICT"
    elif strict_rows:
        status = "PARTIAL_STRICT_NEW_ROWS_ONLY"
    else:
        status = "LEGACY_OR_PENDING_STRICT_UPGRADE"
    return {
        "strategy": strategy,
        "rows": len(rows),
        "strict_rows": len(strict_rows),
        "strict_pct": pct,
        "full_fill_rows": len(full_fill),
        "fee_rows": len(fee_rows),
        "missing_token_rows": len(missing_token),
        "missing_cost_rows": len(missing_cost),
        "legacy_rows": len(legacy),
        "status": status,
    }


def write_outputs(rows: list[dict[str, Any]]) -> str:
    with (ROOT / "strict_simulation_report.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["strict_pct"] = f"{fnum(out.get('strict_pct')):.2f}"
            writer.writerow({field: out.get(field, "") for field in FIELDS})
    lines = [
        "# Strict Simulation Report",
        "",
        "Simulation-only. STRICT means the row has realtime order-book execution, token id, FULL fill, fee fields, and total cost.",
        "",
        "| strategy | rows | strict | strict % | full fill | fee rows | legacy | status |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['strategy']} | {row['rows']} | {row['strict_rows']} | {fnum(row['strict_pct']):.2f}% | "
            f"{row['full_fill_rows']} | {row['fee_rows']} | {row['legacy_rows']} | {row['status']} |"
        )
    text = "\n".join(lines)
    (ROOT / "strict_simulation_report.md").write_text(text + "\n", encoding="utf-8")
    return text


def main() -> int:
    rows = [summarize(strategy, path) for strategy, path in AUDITS.items()]
    print(write_outputs(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
