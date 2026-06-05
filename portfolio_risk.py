#!/usr/bin/env python3
"""Shared paper-portfolio exposure checks."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
AUDIT_LOGS = [
    ROOT / "btc_directional_trade_audit.csv",
    ROOT / "btc_directional_candidate_trade_audit.csv",
    ROOT / "btc_no_dominant_trade_audit.csv",
    ROOT / "eth_high_quality_directional_trade_audit.csv",
    ROOT / "weather_direction_retest_trade_audit.csv",
    ROOT / "weather_high_prob_trade_audit.csv",
    ROOT / "weather_wallet_trade_audit.csv",
    ROOT / "ai_signal_trade_audit.csv",
    ROOT / "smart_wallet_trade_audit.csv",
    ROOT / "smart_direction_retest_trade_audit.csv",
    ROOT / "creamcream_trade_audit.csv",
]


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def latest_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    latest: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        for idx, row in enumerate(csv.DictReader(file)):
            trade_id = row.get("id") or row.get("trade_id") or f"{path.name}:{idx}"
            latest[trade_id] = row
    return latest


def portfolio_open_exposure(paths: list[Path] | None = None) -> tuple[int, float]:
    count = 0
    stake = 0.0
    for path in paths or AUDIT_LOGS:
        for row in latest_rows(path).values():
            if row.get("status") not in {"OPEN", "MARK"}:
                continue
            count += 1
            stake += fnum(row.get("stake"))
    return count, stake
