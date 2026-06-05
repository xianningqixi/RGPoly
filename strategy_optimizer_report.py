#!/usr/bin/env python3
"""Generate conservative parameter recommendations from wallet quality data.

This report is advisory only. It does not edit startup scripts or running bots.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any


FIELDS = [
    "strategy",
    "wallet",
    "classification",
    "recommended_action",
    "stake_usdc",
    "max_source_age_sec",
    "max_slippage_bps",
    "max_source_to_ask_gap",
    "max_market_stake_usdc",
    "max_wallet_market_entries",
    "max_entry_price",
    "reason",
]


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def read_quality(path: Path = Path("wallet_quality_report.csv")) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def read_current_config(path: Path = Path("current_config_report.csv")) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return {row.get("strategy_key", ""): row for row in csv.DictReader(file)}


def base_params(strategy: str) -> dict[str, Any]:
    if strategy == "weather_wallet_copy":
        return {
            "stake_usdc": 2.0,
            "max_source_age_sec": 15,
            "max_slippage_bps": 150,
            "max_source_to_ask_gap": 0.010,
            "max_market_stake_usdc": 2.0,
            "max_wallet_market_entries": 1,
            "max_entry_price": 0.75,
        }
    if strategy == "creamcream_copy":
        return {
            "stake_usdc": 1.0,
            "max_source_age_sec": 15,
            "max_slippage_bps": 200,
            "max_source_to_ask_gap": 0.015,
            "max_market_stake_usdc": 5.0,
            "max_wallet_market_entries": 1,
            "max_entry_price": 0.75,
        }
    if strategy == "smart_wallet_copy":
        return {
            "stake_usdc": 1.0,
            "max_source_age_sec": 6,
            "max_slippage_bps": 150,
            "max_source_to_ask_gap": 0.010,
            "max_market_stake_usdc": 3.0,
            "max_wallet_market_entries": 1,
            "max_entry_price": 0.70,
        }
    if strategy == "btc_directional_copy":
        return {
            "stake_usdc": 2.0,
            "max_source_age_sec": 30,
            "max_slippage_bps": 250,
            "max_source_to_ask_gap": 0.02,
            "max_market_stake_usdc": 8.0,
            "max_wallet_market_entries": 1,
            "max_entry_price": 0.985,
        }
    if strategy == "btc_signal":
        return {
            "stake_usdc": 1.0,
            "max_source_age_sec": 10,
            "max_slippage_bps": 150,
            "max_source_to_ask_gap": 0.010,
            "max_market_stake_usdc": 2.0,
            "max_wallet_market_entries": 1,
            "max_entry_price": 0.58,
        }
    if strategy == "ai_signal_copy":
        return {
            "stake_usdc": 1.0,
            "max_source_age_sec": 10,
            "max_slippage_bps": 200,
            "max_source_to_ask_gap": 0.015,
            "max_market_stake_usdc": 5.0,
            "max_wallet_market_entries": 1,
            "max_entry_price": 0.70,
        }
    return {
        "stake_usdc": 1.0,
        "max_source_age_sec": 15,
        "max_slippage_bps": 200,
        "max_source_to_ask_gap": 0.015,
        "max_market_stake_usdc": 5.0,
        "max_wallet_market_entries": 1,
        "max_entry_price": 0.75,
    }


def recommendation(row: dict[str, str], current_config: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    strategy = row.get("strategy") or "unknown"
    params = base_params(strategy)
    classification = row.get("classification") or "OBSERVE"
    action = row.get("recommended_action") or "keep_observing"
    roi = fnum(row.get("realized_roi_pct"))
    realized = int(fnum(row.get("realized_trades")))
    max_losses = int(fnum(row.get("max_consecutive_losses")))
    current = (current_config or {}).get(strategy, {})
    current_final = int(fnum(current.get("final_since_cutoff")))

    if classification == "MAIN_POOL":
        if current_final < 30:
            params["stake_usdc"] = min(float(params["stake_usdc"]), 1.0)
            params["max_slippage_bps"] = min(float(params["max_slippage_bps"]), 150)
            params["max_source_to_ask_gap"] = min(float(params["max_source_to_ask_gap"]), 0.01)
            params["max_market_stake_usdc"] = min(float(params["max_market_stake_usdc"]), 2.0)
            action = "main_pool_historical_but_wait_current_config_evidence"
        else:
            params["stake_usdc"] = 2.0 if roi < 8 else 5.0
            params["max_slippage_bps"] = 250
            params["max_source_to_ask_gap"] = 0.02
            action = "eligible_but_keep_current_or_small_increase"
    elif classification == "OBSERVE":
        params["stake_usdc"] = 1.0
        action = "observation_only"
    elif classification == "DOWNWEIGHT":
        params["stake_usdc"] = 1.0
        params["max_slippage_bps"] = 150
        params["max_source_to_ask_gap"] = 0.01
        params["max_market_stake_usdc"] = 2.0
        action = "downweight_tighten_filters"
    elif classification == "PAUSE_SUGGESTED":
        params["stake_usdc"] = 0.0
        params["max_market_stake_usdc"] = 0.0
        action = "pause_new_entries"

    if max_losses >= 3:
        params["stake_usdc"] = min(float(params["stake_usdc"]), 1.0)
        params["max_market_stake_usdc"] = min(float(params["max_market_stake_usdc"]), 2.0)
    if realized < 30 and classification != "PAUSE_SUGGESTED":
        params["stake_usdc"] = min(float(params["stake_usdc"]), 1.0)

    return {
        "strategy": strategy,
        "wallet": row.get("wallet") or "unknown",
        "classification": classification,
        "recommended_action": action,
        **params,
        "reason": row.get("reason") or "",
    }


def build_recommendations(quality_rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    rows = quality_rows if quality_rows is not None else read_quality()
    current_config = read_current_config()
    return [recommendation(row, current_config) for row in rows]


def write_csv(rows: list[dict[str, Any]], path: Path = Path("strategy_optimizer_report.csv")) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDS})


def render(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Strategy Optimizer Report",
        "",
        "Advisory only. This report does not edit running scripts.",
        "",
        "| strategy | wallet | class | action | stake | age | slip | gap | market cap | entries | max price | reason |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['strategy']} | {row['wallet']} | {row['classification']} | {row['recommended_action']} | "
            f"{fnum(row['stake_usdc']):.2f} | {fnum(row['max_source_age_sec']):.0f} | "
            f"{fnum(row['max_slippage_bps']):.0f} | {fnum(row['max_source_to_ask_gap']):.3f} | "
            f"{fnum(row['max_market_stake_usdc']):.2f} | {int(fnum(row['max_wallet_market_entries']))} | "
            f"{fnum(row['max_entry_price']):.3f} | {row['reason']} |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one advisory optimization pass and exit")
    return parser


def main() -> int:
    build_parser().parse_args()
    rows = build_recommendations()
    write_csv(rows)
    text = render(rows)
    Path("strategy_optimizer_report.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
