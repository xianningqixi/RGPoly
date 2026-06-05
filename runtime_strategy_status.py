#!/usr/bin/env python3
"""Report runtime state for each simulation strategy.

This is read-only. It makes paused/stopped strategies explicit in status output
and dashboard data so historical losses are not confused with active exposure.
"""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent

STRATEGIES = [
    {
        "strategy": "basket_arbitrage",
        "script": "polymarket_auto_arb.py",
        "audit_file": "dry_run_arb_log.csv",
        "start_file": "start_auto_dry_run_background.ps1",
        "intended_state": "ACTIVE",
        "note": "basket dry-run scanner",
    },
    {
        "strategy": "btc_signal",
        "script": "btc_signal_bot.py",
        "audit_file": "btc_signal_trades.csv",
        "start_file": "start_btc_signal_background.ps1",
        "intended_state": "PAUSED",
        "note": "paused after finalized BTC signal ROI turned negative",
    },
    {
        "strategy": "creamcream_copy",
        "script": "creamcream_copy_sim.py",
        "audit_file": "creamcream_trade_audit.csv",
        "start_file": "start_creamcream_copy_background.ps1",
        "intended_state": "PAUSED",
        "note": "paused after negative realized ROI and high historical slippage",
    },
    {
        "strategy": "creamcream_activity_watcher",
        "script": "watch_creamcream_activity.py",
        "audit_file": "creamcream_activity.csv",
        "start_file": "start_creamcream_watcher_background.ps1",
        "intended_state": "ACTIVE",
        "note": "source wallet activity monitor",
    },
    {
        "strategy": "weather_wallet_copy",
        "script": "weather_wallet_copy_sim.py",
        "audit_file": "weather_wallet_trade_audit.csv",
        "start_file": "start_weather_wallet_copy_background.ps1",
        "intended_state": "ACTIVE",
        "note": "strict allowlist only",
    },
    {
        "strategy": "smart_wallet_copy",
        "script": "smart_wallet_copy_sim.py",
        "audit_file": "smart_wallet_trade_audit.csv",
        "start_file": "start_smart_wallet_copy_background.ps1",
        "intended_state": "PAUSED",
        "note": "paused after finalized audit showed large negative realized ROI",
    },
    {
        "strategy": "btc_directional_copy",
        "script": "btc_directional_wallet_copy_sim.py",
        "audit_file": "btc_directional_trade_audit.csv",
        "start_file": "start_btc_directional_wallet_copy_background.ps1",
        "intended_state": "ACTIVE",
        "note": "downweighted after drawdown breach",
    },
    {
        "strategy": "eth_directional_copy",
        "script": "eth_directional_wallet_copy_sim.py",
        "audit_file": "eth_directional_trade_audit.csv",
        "start_file": "start_eth_directional_wallet_copy_background.ps1",
        "intended_state": "ACTIVE",
        "note": "ETH directional wallet observation, simulation only",
    },
    {
        "strategy": "sol_directional_copy",
        "script": "sol_directional_wallet_copy_sim.py",
        "audit_file": "sol_directional_trade_audit.csv",
        "start_file": "start_sol_directional_wallet_copy_background.ps1",
        "intended_state": "ACTIVE",
        "note": "SOL directional wallet observation, simulation only",
    },
    {
        "strategy": "bnb_directional_copy",
        "script": "bnb_directional_wallet_copy_sim.py",
        "audit_file": "bnb_directional_trade_audit.csv",
        "start_file": "start_bnb_directional_wallet_copy_background.ps1",
        "intended_state": "ACTIVE",
        "note": "BNB directional wallet observation, simulation only",
    },
    {
        "strategy": "btc_directional_candidate_copy",
        "script": "btc_directional_candidate_copy_sim.py",
        "audit_file": "btc_directional_candidate_trade_audit.csv",
        "start_file": "start_btc_directional_candidate_copy_background.ps1",
        "intended_state": "ACTIVE",
        "note": "new candidate BTC directional wallets; strict 0.5U observation only",
    },
    {
        "strategy": "btc_candidate_discovery_scheduler",
        "script": "btc_candidate_discovery_scheduler.py",
        "audit_file": "btc_directional_candidate_pool.csv",
        "start_file": "start_btc_candidate_discovery_scheduler.ps1",
        "intended_state": "ACTIVE",
        "note": "periodically discovers and rotates BTC directional candidate wallets",
    },
    {
        "strategy": "smart_direction_retest",
        "script": "smart_direction_retest_sim.py",
        "audit_file": "smart_direction_retest_trade_audit.csv",
        "start_file": "start_smart_direction_retest_background.ps1",
        "intended_state": "ACTIVE",
        "note": "isolated tiny retest for profitable crypto short-window sub-buckets only",
    },
    {
        "strategy": "weather_direction_retest",
        "script": "weather_direction_retest_sim.py",
        "audit_file": "weather_direction_retest_trade_audit.csv",
        "start_file": "start_weather_direction_retest_background.ps1",
        "intended_state": "ACTIVE",
        "note": "isolated tiny retest for historically positive weather wallet+direction buckets",
    },
    {
        "strategy": "weather_high_prob_wallet_copy",
        "script": "weather_high_prob_wallet_copy_sim.py",
        "audit_file": "weather_high_prob_trade_audit.csv",
        "start_file": "start_weather_high_prob_wallet_copy_background.ps1",
        "intended_state": "ACTIVE",
        "note": "high-probability Poligarch/Railbird weather buckets only; simulation",
    },
    {
        "strategy": "btc_directional_live_shadow",
        "script": "btc_directional_live_shadow_sim.py",
        "audit_file": "btc_directional_live_shadow_trade_audit.csv",
        "start_file": "start_btc_directional_live_shadow_background.ps1",
        "intended_state": "ACTIVE",
        "note": "pre-live 30U shadow validator; simulation only, no private key or live orders",
    },
    {
        "strategy": "weather_high_prob_live_shadow",
        "script": "weather_high_prob_live_shadow_sim.py",
        "audit_file": "weather_high_prob_live_shadow_trade_audit.csv",
        "start_file": "start_weather_high_prob_live_shadow_background.ps1",
        "intended_state": "ACTIVE",
        "note": "pre-live 30U weather shadow validator; simulation only, no private key or live orders",
    },
    {
        "strategy": "btc_no_dominant_candidate_copy",
        "script": "btc_no_dominant_candidate_copy_sim.py",
        "audit_file": "btc_no_dominant_trade_audit.csv",
        "start_file": "start_btc_no_dominant_candidate_copy_background.ps1",
        "intended_state": "ACTIVE",
        "note": "BTC No-dominant candidate wallets only; simulation",
    },
    {
        "strategy": "btc_yes_candidate_observation_copy",
        "script": "btc_yes_candidate_observation_copy_sim.py",
        "audit_file": "btc_yes_candidate_observation_trade_audit.csv",
        "start_file": "start_btc_yes_candidate_observation_copy_background.ps1",
        "intended_state": "ACTIVE",
        "note": "BTC Yes-only observation for current candidate wallets; simulation only, not routed to execution_outbox",
    },
    {
        "strategy": "btc_high_win_candidate_observation_copy",
        "script": "btc_high_win_candidate_observation_copy_sim.py",
        "audit_file": "btc_high_win_candidate_observation_trade_audit.csv",
        "start_file": "start_btc_high_win_candidate_observation_copy_background.ps1",
        "intended_state": "ACTIVE",
        "note": "New high-win BTC candidate wallet batch; simulation only, not routed to execution_outbox",
    },
    {
        "strategy": "eth_high_quality_directional_copy",
        "script": "eth_high_quality_directional_copy_sim.py",
        "audit_file": "eth_high_quality_directional_trade_audit.csv",
        "start_file": "start_eth_high_quality_directional_copy_background.ps1",
        "intended_state": "ACTIVE",
        "note": "ETH high-quality directional wallet pool v2; simulation",
    },
    {
        "strategy": "ai_signal_copy",
        "script": "ai_signal_simulator.py",
        "audit_file": "ai_signal_trade_audit.csv",
        "start_file": "start_ai_signal_simulator_background.ps1",
        "intended_state": "ACTIVE",
        "note": "BTC 15m only observation; ETH and 5m variants remain disabled after negative finalized ROI",
    },
    {
        "strategy": "oracle_source_monitor",
        "script": "oracle_source_monitor.py",
        "audit_file": "oracle_source_map.csv",
        "start_file": "start_oracle_source_monitor_background.ps1",
        "intended_state": "ACTIVE",
        "note": "resolution-source mapper",
    },
    {
        "strategy": "bond_style_scanner",
        "script": "bond_style_market_scanner.py",
        "audit_file": "bond_style_candidates.csv",
        "start_file": "start_bond_style_scanner_background.ps1",
        "intended_state": "ACTIVE",
        "note": "candidate scanner only",
    },
    {
        "strategy": "dashboard_auto_refresh",
        "script": "dashboard_auto_refresh.py",
        "audit_file": "dashboard.html",
        "start_file": "start_dashboard_auto_refresh.ps1",
        "intended_state": "ACTIVE",
        "note": "refreshes dashboard every 10 minutes",
    },
    {
        "strategy": "live_order_preflight",
        "script": "live_order_preflight.py",
        "audit_file": "live_order_intents.csv",
        "start_file": "start_live_order_preflight_background.ps1",
        "intended_state": "ACTIVE",
        "note": "locked live-order preflight only; no private key and no order placement",
    },
    {
        "strategy": "execution_intent_router",
        "script": "execution_intent_router.py",
        "audit_file": "execution_outbox.csv",
        "start_file": "start_execution_intent_router_background.ps1",
        "intended_state": "ACTIVE",
        "note": "routes preflight passes to manual/external execution outbox; no order placement",
    },
]

FIELDS = [
    "strategy",
    "script",
    "intended_state",
    "runtime_state",
    "pid",
    "audit_file",
    "audit_rows",
    "status",
    "note",
]


def read_overrides(path: Path = ROOT / "runtime_strategy_overrides.csv") -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            return {row.get("strategy", ""): row for row in csv.DictReader(file) if row.get("strategy")}
    except Exception:
        return {}


def process_map() -> dict[str, dict[str, str]]:
    command = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -like 'python*' } | "
        "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=12,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {}
        raw: Any = json.loads(result.stdout)
        if isinstance(raw, dict):
            raw = [raw]
    except Exception:
        return {}

    out: dict[str, dict[str, str]] = {}
    for row in raw:
        cmd = str(row.get("CommandLine") or "")
        for item in STRATEGIES:
            script = item["script"]
            if script in cmd:
                out[script] = {
                    "pid": str(row.get("ProcessId") or ""),
                    "command": cmd,
                }
    return out


def count_csv_rows(name: str) -> int:
    path = ROOT / name
    if not path.exists():
        return 0
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            return max(0, sum(1 for _ in csv.DictReader(file)))
    except Exception:
        return 0


def build_rows() -> list[dict[str, str]]:
    running = process_map()
    overrides = read_overrides()
    rows: list[dict[str, str]] = []
    for item in STRATEGIES:
        script = item["script"]
        proc = running.get(script)
        override = overrides.get(item["strategy"], {})
        intended = override.get("intended_state") or item["intended_state"]
        note = override.get("note") or item["note"]
        runtime = "RUNNING" if proc else "STOPPED"
        if intended == "PAUSED" and runtime == "STOPPED":
            status = "OK_PAUSED"
        elif intended == "PAUSED" and runtime == "RUNNING":
            status = "ATTENTION_PAUSED_BUT_RUNNING"
        elif intended == "ACTIVE" and runtime == "RUNNING":
            status = "OK_RUNNING"
        else:
            status = "ATTENTION_ACTIVE_BUT_STOPPED"
        rows.append(
            {
                "strategy": item["strategy"],
                "script": script,
                "intended_state": intended,
                "runtime_state": runtime,
                "pid": proc["pid"] if proc else "",
                "audit_file": item["audit_file"],
                "audit_rows": str(count_csv_rows(item["audit_file"])),
                "status": status,
                "note": note,
            }
        )
    return rows


def write_csv(rows: list[dict[str, str]], path: Path = ROOT / "runtime_strategy_status.csv") -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    rows = build_rows()
    write_csv(rows)
    for row in rows:
        print(
            f"{row['strategy']}: {row['status']} "
            f"({row['runtime_state']}, intended={row['intended_state']}, pid={row['pid'] or '-'})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
