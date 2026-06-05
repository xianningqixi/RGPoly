#!/usr/bin/env python3
"""Pre-live validation gate report.

This is read-only. It evaluates whether the selected main strategies have enough
strict-shadow and locked preflight evidence to be considered ready for manual
live review. It never places orders and never reads credentials.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent

STRATEGIES = [
    {
        "strategy": "btc_directional_copy",
        "name": "BTC directional copy",
        "main_audit": "btc_directional_trade_audit.csv",
        "shadow_strategy": "btc_directional_live_shadow",
        "shadow_name": "BTC directional live shadow",
        "shadow_audit": "btc_directional_live_shadow_trade_audit.csv",
        "shadow_execution_audit": "btc_directional_live_shadow_execution_audit.csv",
        "strict_label": "btc_directional_live_shadow_fee_aware_exact_mirror_v3_2026_06_02",
    },
    {
        "strategy": "btc_no_dominant_candidate_copy",
        "name": "BTC No-dominant candidate copy",
        "main_audit": "btc_no_dominant_trade_audit.csv",
        "shadow_strategy": "btc_no_dominant_candidate_copy",
        "shadow_name": "BTC No-dominant strict live-like simulation",
        "shadow_audit": "btc_no_dominant_trade_audit.csv",
        "shadow_execution_audit": "",
        "strict_label": "strict_live_like_execution_all_sims_2026_06_02",
    },
    {
        "strategy": "weather_high_prob_wallet_copy",
        "name": "Weather high-prob wallet copy",
        "main_audit": "weather_high_prob_trade_audit.csv",
        "shadow_strategy": "weather_high_prob_live_shadow",
        "shadow_name": "Weather high-prob live shadow",
        "shadow_audit": "weather_high_prob_live_shadow_trade_audit.csv",
        "shadow_execution_audit": "weather_high_prob_live_shadow_execution_audit.csv",
        "strict_label": "weather_high_prob_live_shadow_fee_aware_exact_mirror_v3_2026_06_02",
    },
]

FIELDS = [
    "strategy",
    "main_state",
    "main_final",
    "main_pending",
    "main_wins",
    "main_losses",
    "main_pnl",
    "main_roi",
    "shadow_state",
    "strict_shadow_cutoff",
    "strict_shadow_final",
    "strict_shadow_pending",
    "strict_shadow_wins",
    "strict_shadow_losses",
    "strict_shadow_pnl",
    "strict_shadow_roi",
    "strict_shadow_max_drawdown",
    "preflight_rows",
    "preflight_pass",
    "preflight_pass_rate",
    "preflight_blocked",
    "gate_profile",
    "gate_status",
    "failed_rules",
]

STRICT_RULES = {
    "main_min_final": 50,
    "main_min_roi": 3.0,
    "strict_shadow_min_final": 50,
    "strict_shadow_min_roi": 3.0,
    "preflight_min_rows": 20,
    "preflight_min_pass_rate": 95.0,
    "max_shadow_drawdown_to_pnl": 0.5,
}

SMALL_STAKE_RULES = {
    "main_min_final": 10,
    "main_min_roi": 0.0,
    "strict_shadow_min_final": 5,
    "strict_shadow_min_roi": 0.0,
    "preflight_min_rows": 5,
    "preflight_min_pass": 1,
    "max_shadow_drawdown_to_pnl": 2.0,
}


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def parse_dt(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def read_csv(name: str | Path) -> list[dict[str, str]]:
    path = Path(name)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def latest_rows(name: str) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for row in read_csv(name):
        key = row.get("id") or row.get("intent_id") or ""
        if key:
            rows[key] = row
    return rows


def row_time(row: dict[str, str]) -> datetime:
    for key in ("detected_time", "audit_ts", "ts", "signal_time"):
        value = row.get(key)
        if value:
            return parse_dt(value)
    return datetime.min.replace(tzinfo=timezone.utc)


def final_pnl(row: dict[str, str]) -> float:
    value = row.get("fee_adjusted_final_pnl")
    if value not in (None, ""):
        return fnum(value)
    value = row.get("slippage_final_pnl")
    if value not in (None, ""):
        return fnum(value)
    return fnum(row.get("final_pnl"))


def stake_value(row: dict[str, str]) -> float:
    value = row.get("intended_stake_usdc")
    if value not in (None, ""):
        return fnum(value)
    return fnum(row.get("stake"))


def is_final(row: dict[str, str]) -> bool:
    return row.get("final_result") in {"WIN", "LOSS"} or row.get("status") == "FINAL"


def latest_override_state(strategy: str) -> str:
    state = "ACTIVE"
    latest = datetime.min.replace(tzinfo=timezone.utc)
    for row in read_csv("runtime_strategy_overrides.csv"):
        if row.get("strategy") != strategy:
            continue
        ts = parse_dt(row.get("updated_at"))
        if ts >= latest:
            latest = ts
            state = row.get("intended_state") or state
    return state


def strict_cutoff(label: str) -> datetime:
    for row in read_csv("strategy_change_points.csv"):
        if row.get("label") == label:
            return parse_dt(row.get("cutoff_ts"))
    return datetime.max.replace(tzinfo=timezone.utc)


def summarize_audit(name: str, cutoff: datetime | None = None, realtime_only: bool = False) -> dict[str, Any]:
    rows = list(latest_rows(name).values())
    if cutoff:
        rows = [row for row in rows if row_time(row) >= cutoff]
    if realtime_only:
        rows = [row for row in rows if row.get("execution_source") == "REALTIME_ORDERBOOK"]
    finals = [row for row in rows if is_final(row)]
    pending = [row for row in rows if not is_final(row)]
    stake = sum(stake_value(row) for row in finals)
    pnl = sum(final_pnl(row) for row in finals)
    wins = sum(1 for row in finals if final_pnl(row) > 0)
    losses = sum(1 for row in finals if final_pnl(row) < 0)
    curve = []
    equity = 0.0
    for row in sorted(finals, key=row_time):
        equity += final_pnl(row)
        curve.append(equity)
    peak = 0.0
    max_dd = 0.0
    for equity in curve:
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {
        "final": len(finals),
        "pending": len(pending),
        "wins": wins,
        "losses": losses,
        "stake": stake,
        "pnl": pnl,
        "roi": pnl / stake * 100 if stake else 0.0,
        "max_drawdown": max_dd,
    }


def summarize_preflight(*strategies: str) -> dict[str, Any]:
    strategy_set = {item for item in strategies if item}
    rows = [row for row in read_csv("live_order_intents.csv") if row.get("source_strategy") in strategy_set]
    total = len(rows)
    passed = sum(1 for row in rows if row.get("status") == "PREVIEW_ONLY_WOULD_PLACE")
    return {
        "rows": total,
        "passed": passed,
        "blocked": total - passed,
        "pass_rate": passed / total * 100 if total else 0.0,
    }


def failed_strict_rules(main: dict[str, Any], shadow: dict[str, Any], preflight: dict[str, Any], main_state: str, shadow_state: str) -> list[str]:
    failed: list[str] = []
    if main_state == "PAUSED":
        failed.append("main_paused")
    if shadow_state == "PAUSED":
        failed.append("shadow_paused")
    if shadow["final"] < STRICT_RULES["strict_shadow_min_final"]:
        failed.append("strict_shadow_final_lt_50")
    if shadow["roi"] <= STRICT_RULES["strict_shadow_min_roi"]:
        failed.append("strict_shadow_roi_lte_3pct")
    if shadow["pnl"] <= 0:
        failed.append("strict_shadow_pnl_not_positive")
    if shadow["pnl"] > 0 and shadow["max_drawdown"] > shadow["pnl"] * STRICT_RULES["max_shadow_drawdown_to_pnl"]:
        failed.append("strict_shadow_drawdown_gt_50pct_pnl")
    if preflight["rows"] < STRICT_RULES["preflight_min_rows"]:
        failed.append("preflight_rows_lt_20")
    if preflight["pass_rate"] < STRICT_RULES["preflight_min_pass_rate"]:
        failed.append("preflight_pass_rate_lt_95pct")
    if main["final"] < STRICT_RULES["main_min_final"]:
        failed.append("main_final_lt_50")
    if main["roi"] <= STRICT_RULES["main_min_roi"]:
        failed.append("main_roi_lte_3pct")
    return failed


def failed_small_stake_rules(main: dict[str, Any], shadow: dict[str, Any], preflight: dict[str, Any], main_state: str, shadow_state: str) -> list[str]:
    failed: list[str] = []
    if main_state == "PAUSED":
        failed.append("main_paused")
    if main["final"] < SMALL_STAKE_RULES["main_min_final"]:
        failed.append("main_final_lt_10")
    if main["pnl"] <= 0:
        failed.append("main_pnl_not_positive")
    if main["roi"] <= SMALL_STAKE_RULES["main_min_roi"]:
        failed.append("main_roi_lte_0pct")

    shadow_ok = (
        shadow_state != "PAUSED"
        and shadow["final"] >= SMALL_STAKE_RULES["strict_shadow_min_final"]
        and shadow["pnl"] > 0
        and shadow["roi"] > SMALL_STAKE_RULES["strict_shadow_min_roi"]
        and (
            shadow["max_drawdown"] <= shadow["pnl"] * SMALL_STAKE_RULES["max_shadow_drawdown_to_pnl"]
            if shadow["pnl"] > 0
            else False
        )
    )
    preflight_ok = (
        preflight["rows"] >= SMALL_STAKE_RULES["preflight_min_rows"]
        and preflight["passed"] >= SMALL_STAKE_RULES["preflight_min_pass"]
    )
    if not (shadow_ok or preflight_ok):
        failed.append("needs_positive_shadow_or_fresh_preflight_pass")
    return failed


def gate(main: dict[str, Any], shadow: dict[str, Any], preflight: dict[str, Any], main_state: str, shadow_state: str) -> tuple[str, str, list[str]]:
    strict_failed = failed_strict_rules(main, shadow, preflight, main_state, shadow_state)
    if not strict_failed:
        return "STRICT", "READY_FOR_MANUAL_REVIEW", []
    small_failed = failed_small_stake_rules(main, shadow, preflight, main_state, shadow_state)
    if not small_failed:
        return "SMALL_STAKE", "READY_FOR_SMALL_STAKE_REVIEW", strict_failed
    return "SMALL_STAKE", "NOT_READY", small_failed


def build_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in STRATEGIES:
        main = summarize_audit(item["main_audit"])
        cutoff = strict_cutoff(item["strict_label"])
        execution_audit = item.get("shadow_execution_audit")
        if execution_audit and read_csv(execution_audit):
            shadow = summarize_audit(execution_audit, cutoff=cutoff, realtime_only=True)
        else:
            shadow = summarize_audit(item["shadow_audit"], cutoff=cutoff)
        preflight = summarize_preflight(item["strategy"], item["shadow_strategy"])
        main_state = latest_override_state(item["strategy"])
        shadow_state = latest_override_state(item["shadow_strategy"])
        profile, status, failed = gate(main, shadow, preflight, main_state, shadow_state)
        rows.append(
            {
                "strategy": item["strategy"],
                "main_state": main_state,
                "main_final": main["final"],
                "main_pending": main["pending"],
                "main_wins": main["wins"],
                "main_losses": main["losses"],
                "main_pnl": main["pnl"],
                "main_roi": main["roi"],
                "shadow_state": shadow_state,
                "strict_shadow_cutoff": cutoff.isoformat(),
                "strict_shadow_final": shadow["final"],
                "strict_shadow_pending": shadow["pending"],
                "strict_shadow_wins": shadow["wins"],
                "strict_shadow_losses": shadow["losses"],
                "strict_shadow_pnl": shadow["pnl"],
                "strict_shadow_roi": shadow["roi"],
                "strict_shadow_max_drawdown": shadow["max_drawdown"],
                "preflight_rows": preflight["rows"],
                "preflight_pass": preflight["passed"],
                "preflight_pass_rate": preflight["pass_rate"],
                "preflight_blocked": preflight["blocked"],
                "gate_profile": profile,
                "gate_status": status,
                "failed_rules": ";".join(failed),
            }
        )
    return rows


def write_csv(rows: list[dict[str, Any]]) -> None:
    with (ROOT / "pre_live_validation_report.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            for key in ("main_pnl", "main_roi", "strict_shadow_pnl", "strict_shadow_roi", "strict_shadow_max_drawdown", "preflight_pass_rate"):
                out[key] = f"{fnum(out.get(key)):.6f}"
            writer.writerow({field: out.get(field, "") for field in FIELDS})


def render_md(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Pre-live Validation Report",
        "",
        "Read-only validation. This report does not place orders and does not use credentials.",
        "Strict gate is unchanged. Small-stake gate is looser for review only and does not change copy-entry filters.",
        "",
        "| strategy | profile | gate | main state | main final | main pnl | main ROI | shadow state | strict shadow final | strict shadow pnl | strict shadow ROI | preflight pass | failed rules |",
        "|---|---|---|---|---:|---:|---:|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['strategy']} | {row['gate_profile']} | {row['gate_status']} | {row['main_state']} | {row['main_final']} | "
            f"{fnum(row['main_pnl']):.4f}U | {fnum(row['main_roi']):.2f}% | {row['shadow_state']} | "
            f"{row['strict_shadow_final']} | {fnum(row['strict_shadow_pnl']):.4f}U | "
            f"{fnum(row['strict_shadow_roi']):.2f}% | {fnum(row['preflight_pass_rate']):.2f}% | "
            f"{row['failed_rules']} |"
        )
    return "\n".join(lines)


def main() -> int:
    argparse.ArgumentParser().parse_args()
    rows = build_rows()
    write_csv(rows)
    text = render_md(rows)
    (ROOT / "pre_live_validation_report.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
