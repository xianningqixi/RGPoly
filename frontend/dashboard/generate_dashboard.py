#!/usr/bin/env python3
"""Generate a self-contained visual dashboard for the Polymarket simulation.

The dashboard is read-only. It embeds current CSV/report data into dashboard.html
so the user can open it directly without a web server.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore


ROOT = Path.cwd()
LOCAL_TZ = ZoneInfo("Asia/Shanghai") if ZoneInfo else timezone(timedelta(hours=8))


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def inum(value: Any) -> int:
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def read_csv(name: str) -> list[dict[str, str]]:
    path = ROOT / name
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def local_time_text(value: datetime | None = None) -> str:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")


def max_drawdown(points: list[dict[str, str]]) -> float:
    peak = 0.0
    worst = 0.0
    for row in points:
        equity = fnum(row.get("total_equity"))
        peak = max(peak, equity)
        worst = max(worst, peak - equity)
    return worst


def tail_text(name: str, lines: int = 8) -> str:
    path = ROOT / name
    if not path.exists():
        return ""
    try:
        data = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return ""
    return "\n".join(data[-lines:])


def bot_processes() -> list[dict[str, str]]:
    scripts = [
        "polymarket_auto_arb.py",
        "btc_signal_bot.py",
        "ai_signal_simulator.py",
        "watch_creamcream_activity.py",
        "creamcream_copy_sim.py",
        "oracle_source_monitor.py",
        "weather_wallet_copy_sim.py",
        "smart_wallet_copy_sim.py",
        "smart_direction_retest_sim.py",
        "btc_directional_wallet_copy_sim.py",
        "btc_directional_candidate_copy_sim.py",
        "btc_candidate_discovery_scheduler.py",
        "bond_style_market_scanner.py",
        "dashboard_auto_refresh.py",
        "live_order_preflight.py",
    ]
    command = (
        "Get-CimInstance Win32_Process -Filter \"name = 'python.exe'\" | "
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
            return []
        raw = json.loads(result.stdout)
        if isinstance(raw, dict):
            raw = [raw]
        processes = []
        for row in raw:
            cmd = str(row.get("CommandLine") or "")
            matched = next((script for script in scripts if script in cmd), "")
            if matched:
                processes.append({"pid": str(row.get("ProcessId") or ""), "script": matched, "command": cmd})
        return processes
    except Exception:
        return []


def refresh_reports() -> None:
    commands = [
        ["python", str(ROOT / "audit_backfill_scheduler.py"), "--once", "--batch-limit", "20"],
        ["python", str(ROOT / "wallet_discovery.py"), "--once"],
        ["python", str(ROOT / "btc_directional_wallet_discovery.py"), "--once"],
        ["python", str(ROOT / "btc_directional_candidate_rotation_report.py"), "--once"],
        ["python", str(ROOT / "apply_btc_candidate_rotation.py"), "--once"],
        ["python", str(ROOT / "btc_candidate_shadow_observer.py"), "--once", "--candidate-limit", "8", "--max-new-rows", "80"],
        ["python", str(ROOT / "btc_candidate_shadow_report.py"), "--once"],
        ["python", str(ROOT / "btc_candidate_pool_health.py"), "--once"],
        ["python", str(ROOT / "candidate_sampling_health.py"), "--once"],
        ["python", str(ROOT / "wallet_quality_engine.py"), "--once"],
        ["python", str(ROOT / "observation_promotion_queue.py"), "--once"],
        ["python", str(ROOT / "strategy_optimizer_report.py"), "--once"],
        ["python", str(ROOT / "runtime_strategy_status.py")],
        ["python", str(ROOT / "runtime_parameter_health.py"), "--once"],
        ["python", str(ROOT / "dashboard_refresh_health.py"), "--once"],
        ["python", str(ROOT / "data_quality_report.py"), "--once"],
        ["python", str(ROOT / "pending_exposure_report.py"), "--once"],
        ["python", str(ROOT / "exposure_consistency_report.py"), "--once"],
        ["python", str(ROOT / "current_config_report.py"), "--once"],
        ["python", str(ROOT / "active_cohort_health_report.py"), "--once"],
        ["python", str(ROOT / "active_cohort_settlement_report.py"), "--once"],
        ["python", str(ROOT / "active_cohort_guard.py"), "--apply", "--once"],
        ["python", str(ROOT / "risk_guard.py"), "--apply"],
        ["python", str(ROOT / "runtime_strategy_status.py")],
        ["python", str(ROOT / "current_config_report.py"), "--once"],
        ["python", str(ROOT / "pre_live_validation_report.py")],
        ["python", str(ROOT / "strict_simulation_report.py")],
        ["python", str(ROOT / "signal_reject_report.py"), "--once"],
        ["python", str(ROOT / "active_signal_funnel.py"), "--once"],
        ["python", str(ROOT / "btc_directional_bucket_report.py"), "--once"],
        ["python", str(ROOT / "btc_directional_filter_optimizer.py"), "--once", "--stake-usdc", "10", "--bankroll-usdc", "1000", "--top", "25"],
        ["python", str(ROOT / "market_direction_report.py"), "--once"],
        ["python", str(ROOT / "direction_retest_candidates.py"), "--once"],
        ["python", str(ROOT / "realized_pnl_report.py")],
        ["python", str(ROOT / "weather_direction_parameter_sweep.py"), "--once"],
        ["python", str(ROOT / "pending_scenario_report.py"), "--once"],
        ["python", str(ROOT / "recovery_backtest_matrix.py"), "--once", "--stake-usdc", "10", "--bankroll-usdc", "1000"],
        [
            "python",
            str(ROOT / "portfolio_backtest.py"),
            "--strategy",
            "weather_direction_retest",
            "--stake-usdc",
            "10",
            "--bankroll-usdc",
            "1000",
            "--max-open-positions",
            "2",
            "--max-strategy-open-positions",
            "2",
            "--since",
            "2026-05-25T13:58:41Z",
            "--wallet",
            "Poligarch",
            "--wallet",
            "Railbird",
            "--outcome",
            "Yes",
            "--outcome",
            "No",
            "--price-bucket",
            "0.8-0.9",
            "--price-bucket",
            "0.9-1.0",
            "--min-entry-price",
            "0.80",
            "--max-entry-price",
            "0.995",
            "--min-source-price",
            "0.80",
            "--max-source-price",
            "0.995",
            "--max-slippage-bps",
            "350",
            "--max-source-to-ask-gap",
            "0.035",
            "--max-source-age-sec",
            "90",
            "--min-ask-depth-usdc",
            "20",
            "--min-direction-edge",
            "0.005",
            "--csv",
            str(ROOT / "portfolio_backtest_current_10u_report.csv"),
            "--md",
            str(ROOT / "portfolio_backtest_current_10u_report.md"),
        ],
        ["python", str(ROOT / "stability_verdict_report.py"), "--once"],
        ["python", str(ROOT / "capital_allocation_report.py"), "--once"],
        ["python", str(ROOT / "daily_report.py")],
    ]
    for command in commands:
        subprocess.run(command, cwd=str(ROOT), check=False)


def compact_rows(rows: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    return rows[:limit]


def build_data() -> dict[str, Any]:
    realized = read_csv("realized_pnl_report.csv")
    active_realized = read_csv("realized_active_pnl_report.csv")
    cohorts = read_csv("realized_cohort_report.csv")
    equity = read_csv("realized_equity_curve.csv")
    current_equity = read_csv("realized_current_config_equity_curve.csv")
    quality = read_csv("wallet_quality_report.csv")
    observation_queue = read_csv("observation_promotion_queue.csv")
    optimizer = read_csv("strategy_optimizer_report.csv")
    runtime_status = read_csv("runtime_strategy_status.csv")
    runtime_parameter_health = read_csv("runtime_parameter_health.csv")
    dashboard_refresh_health = read_csv("dashboard_refresh_health.csv")
    data_quality = read_csv("data_quality_report.csv")
    pending_exposure = read_csv("pending_exposure_report.csv")
    exposure_consistency = read_csv("exposure_consistency_report.csv")
    active_cohort_health = read_csv("active_cohort_health_report.csv")
    active_cohort_settlement = read_csv("active_cohort_settlement_report.csv")
    active_cohort_guard = read_csv("active_cohort_guard_status.csv")
    backfill_summary = read_csv("audit_backfill_summary.csv")
    risk_guard_status = read_csv("risk_guard_status.csv")
    risk_guard_actions = read_csv("risk_guard_actions.csv")
    current_config = read_csv("current_config_report.csv")
    pre_live_validation = read_csv("pre_live_validation_report.csv")
    strict_simulation = read_csv("strict_simulation_report.csv")
    reject_report = read_csv("signal_reject_report.csv")
    active_funnel = read_csv("active_signal_funnel.csv")
    btc_bucket_report = read_csv("btc_directional_bucket_report.csv")
    btc_filter_optimizer = read_csv("btc_directional_filter_optimizer.csv")
    btc_candidate_rotation = read_csv("btc_directional_candidate_rotation_report.csv")
    btc_candidate_pool_health = read_csv("btc_candidate_pool_health.csv")
    btc_candidate_shadow = read_csv("btc_candidate_shadow_report.csv")
    candidate_sampling_health = read_csv("candidate_sampling_health.csv")
    market_direction = read_csv("market_direction_report.csv")
    direction_retest = read_csv("direction_retest_candidates.csv")
    capital_allocation = read_csv("capital_allocation_report.csv")
    weather_direction_sweep = read_csv("weather_direction_parameter_sweep.csv")
    pending_scenario = read_csv("pending_scenario_report.csv")
    recovery_backtest = read_csv("recovery_backtest_matrix.csv")
    portfolio_backtest = read_csv("portfolio_backtest_current_10u_report.csv")
    stability_verdict = read_csv("stability_verdict_report.csv")
    candidates = read_csv("candidate_wallets.csv")
    lead_lag_candidates = read_csv("crypto_lead_lag_candidates.csv")
    ai_decisions = read_csv("ai_signal_decisions.csv")
    ai_audit = read_csv("ai_signal_trade_audit.csv")
    ai_runtime_health = read_csv("ai_signal_health.csv")

    total_stake = sum(fnum(row.get("stake")) for row in realized)
    total_pnl = sum(fnum(row.get("pnl")) for row in realized)
    total_realized = sum(inum(row.get("realized")) for row in realized)
    total_pending = sum(inum(row.get("pending")) for row in realized)
    total_roi = (total_pnl / total_stake * 100) if total_stake else 0.0
    active_stake = sum(fnum(row.get("stake")) for row in active_realized)
    active_pnl = sum(fnum(row.get("pnl")) for row in active_realized)
    active_realized_count = sum(inum(row.get("realized")) for row in active_realized)
    active_roi = (active_pnl / active_stake * 100) if active_stake else 0.0
    current_active = [row for row in current_config if row.get("intended_state") != "PAUSED"]
    current_active_stake = sum(fnum(row.get("stake")) for row in current_active)
    current_active_pnl = sum(fnum(row.get("pnl")) for row in current_active)
    current_active_final = sum(inum(row.get("final_since_cutoff")) for row in current_active)
    current_active_pending = sum(inum(row.get("pending_since_cutoff")) for row in current_active)
    current_active_roi = (current_active_pnl / current_active_stake * 100) if current_active_stake else 0.0

    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    new_24h = 0
    for row in equity:
        ts = parse_dt(row.get("ts", ""))
        if ts and ts >= day_ago:
            new_24h += 1

    classes: dict[str, int] = {}
    for row in quality:
        key = row.get("classification") or "UNKNOWN"
        classes[key] = classes.get(key, 0) + 1

    latest_ts = None
    if equity:
        latest_ts = parse_dt(equity[-1].get("ts", ""))

    runtime_attention = sum(1 for row in runtime_status if str(row.get("status") or "").startswith("ATTENTION"))
    runtime_parameter_attention = sum(1 for row in runtime_parameter_health if row.get("status") != "OK")
    dashboard_refresh_attention = sum(1 for row in dashboard_refresh_health if row.get("status") != "OK")
    paused_ok = sum(1 for row in runtime_status if row.get("status") == "OK_PAUSED")
    stale_pending = sum(1 for row in data_quality if row.get("data_quality") == "STALE_PENDING")
    low_coverage = sum(1 for row in data_quality if row.get("data_quality") in {"LOW_FINAL_SAMPLE", "LOW_FINAL_COVERAGE"})
    candidate_health_counts: dict[str, int] = {}
    for row in btc_candidate_pool_health:
        key = row.get("health") or "UNKNOWN"
        candidate_health_counts[key] = candidate_health_counts.get(key, 0) + 1

    ai_take = [row for row in ai_decisions if row.get("decision") == "TAKE"]
    ai_skip = [row for row in ai_decisions if row.get("decision") == "SKIP"]
    ai_final = [
        row
        for row in ai_audit
        if row.get("final_result") in {"WIN", "LOSS"} and row.get("slippage_final_pnl") not in {"", None}
    ]
    ai_pnl = sum(fnum(row.get("slippage_final_pnl")) for row in ai_final)
    ai_stake = sum(fnum(row.get("stake")) for row in ai_final)
    ai_wins = sum(1 for row in ai_final if fnum(row.get("slippage_final_pnl")) > 0)
    ai_losses = sum(1 for row in ai_final if fnum(row.get("slippage_final_pnl")) < 0)
    positive_2m = [
        row for row in ai_audit if row.get("slippage_pnl_2m") not in {"", None} and fnum(row.get("slippage_pnl_2m")) > 0
    ]
    marked_2m = [row for row in ai_audit if row.get("slippage_pnl_2m") not in {"", None}]
    ai_health = {
        "take": len(ai_take),
        "skip": len(ai_skip),
        "final": len(ai_final),
        "wins": ai_wins,
        "losses": ai_losses,
        "pnl": ai_pnl,
        "roi": ai_pnl / ai_stake * 100 if ai_stake else 0.0,
        "stake": ai_stake,
        "avg_confidence": sum(fnum(row.get("confidence")) for row in ai_take) / len(ai_take) if ai_take else 0.0,
        "approved_losses": ai_losses,
        "missed_edge": sum(1 for row in ai_skip if fnum(row.get("expected_edge_bps")) > 50),
        "avg_slippage_bps": sum(fnum(row.get("slippage_bps")) for row in ai_audit) / len(ai_audit) if ai_audit else 0.0,
        "avg_source_to_ask_gap": sum(fnum(row.get("source_to_ask_gap")) for row in lead_lag_candidates) / len(lead_lag_candidates) if lead_lag_candidates else 0.0,
        "positive_2m_rate": len(positive_2m) / len(marked_2m) * 100 if marked_2m else 0.0,
    }
    ai_runtime = ai_runtime_health[-1] if ai_runtime_health else {}

    return {
        "generated_at": local_time_text(),
        "latest_trade_at": local_time_text(latest_ts) if latest_ts else "暂无 final 交易",
        "summary": {
            "total_stake": total_stake,
            "total_pnl": total_pnl,
            "total_roi": total_roi,
            "active_stake": active_stake,
            "active_pnl": active_pnl,
            "active_roi": active_roi,
            "active_realized": active_realized_count,
            "current_active_stake": current_active_stake,
            "current_active_pnl": current_active_pnl,
            "current_active_roi": current_active_roi,
            "current_active_final": current_active_final,
            "current_active_pending": current_active_pending,
            "current_active_drawdown": max_drawdown(
                [
                    {"total_equity": row.get("active_current_equity", "")}
                    for row in current_equity
                    if row.get("intended_state") != "PAUSED"
                ]
            ),
            "total_realized": total_realized,
            "total_pending": total_pending,
            "new_24h": new_24h,
            "max_drawdown": max_drawdown(equity),
            "running_processes": len(bot_processes()),
            "runtime_attention": runtime_attention + runtime_parameter_attention + dashboard_refresh_attention,
            "paused_ok": paused_ok,
            "stale_pending": stale_pending,
            "low_coverage": low_coverage,
            "candidate_new_observation": candidate_health_counts.get("NEW_OBSERVATION", 0),
            "candidate_waiting_final_in_pool": candidate_health_counts.get("WAITING_FINAL_IN_POOL", 0),
            "candidate_waiting_final": candidate_health_counts.get("WAITING_FINAL_OFF_POOL", 0),
            "candidate_promotion_ready": candidate_health_counts.get("PROMOTION_READY", 0),
            "candidate_failed_gate": candidate_health_counts.get("FAILED_FINAL_GATE", 0),
        },
        "realized": realized,
        "active_realized": active_realized,
        "cohorts": cohorts,
        "equity": equity,
        "current_equity": current_equity,
        "quality": quality,
        "observation_queue": compact_rows(observation_queue, 30),
        "optimizer": optimizer,
        "runtime_status": runtime_status,
        "runtime_parameter_health": runtime_parameter_health,
        "dashboard_refresh_health": dashboard_refresh_health,
        "data_quality": data_quality,
        "pending_exposure": compact_rows(pending_exposure, 40),
        "exposure_consistency": exposure_consistency,
        "active_cohort_health": active_cohort_health,
        "active_cohort_settlement": active_cohort_settlement,
        "active_cohort_guard": active_cohort_guard,
        "backfill_summary": compact_rows(list(reversed(backfill_summary)), 30),
        "risk_guard_status": risk_guard_status,
        "risk_guard_actions": compact_rows(list(reversed(risk_guard_actions)), 30),
        "current_config": current_config,
        "pre_live_validation": pre_live_validation,
        "strict_simulation": strict_simulation,
        "reject_report": reject_report,
        "active_funnel": active_funnel,
        "btc_bucket_report": btc_bucket_report,
        "btc_filter_optimizer": compact_rows(btc_filter_optimizer, 25),
        "btc_candidate_rotation": compact_rows(btc_candidate_rotation, 80),
        "btc_candidate_pool_health": compact_rows(btc_candidate_pool_health, 80),
        "btc_candidate_shadow": compact_rows(btc_candidate_shadow, 30),
        "candidate_sampling_health": compact_rows(candidate_sampling_health, 80),
        "market_direction": compact_rows(market_direction, 80),
        "direction_retest": compact_rows(direction_retest, 80),
        "capital_allocation": capital_allocation,
        "weather_direction_sweep": weather_direction_sweep,
        "pending_scenario": pending_scenario,
        "recovery_backtest": recovery_backtest,
        "portfolio_backtest": portfolio_backtest,
        "stability_verdict": stability_verdict,
        "candidates": compact_rows(candidates, 80),
        "lead_lag_candidates": compact_rows(lead_lag_candidates, 80),
        "ai_decisions": compact_rows(list(reversed(ai_decisions)), 80),
        "ai_health": ai_health,
        "ai_runtime_health": ai_runtime,
        "classes": classes,
        "processes": bot_processes(),
        "logs": {
            "weather_errors": tail_text("weather_wallet_copy_error.log"),
            "smart_errors": tail_text("smart_wallet_copy_error.log"),
            "btc_errors": tail_text("btc_directional_copy_error.log"),
            "bond_errors": tail_text("bond_style_error.log"),
            "ai_errors": tail_text("ai_signal_error.log"),
        },
    }


def render_html(data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    escaped_payload = html.escape(payload, quote=False)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Polymarket 模拟盘可视化</title>
  <style>
    :root {{
      --bg: #f7f8fa;
      --panel: #ffffff;
      --ink: #1d2733;
      --muted: #687386;
      --line: #d9dee8;
      --good: #16845b;
      --bad: #b42318;
      --warn: #a15c07;
      --blue: #235caa;
      --cyan: #007c89;
      --shadow: 0 1px 2px rgba(23, 34, 49, .08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
      font-size: 14px;
      letter-spacing: 0;
    }}
    header {{
      background: #ffffff;
      border-bottom: 1px solid var(--line);
      padding: 18px 24px 14px;
      position: sticky;
      top: 0;
      z-index: 4;
    }}
    .title-row {{
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 18px;
      flex-wrap: wrap;
    }}
    h1 {{ margin: 0; font-size: 24px; line-height: 1.25; }}
    .sub {{ color: var(--muted); margin-top: 6px; }}
    .badge {{
      display: inline-flex;
      align-items: center;
      height: 26px;
      padding: 0 9px;
      border: 1px solid var(--line);
      background: #f9fafb;
      border-radius: 6px;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }}
    main {{ padding: 18px 24px 32px; max-width: 1500px; margin: 0 auto; }}
    .grid {{ display: grid; gap: 14px; }}
    .cards {{ grid-template-columns: repeat(6, minmax(150px, 1fr)); }}
    .two {{ grid-template-columns: minmax(0, 1.25fr) minmax(360px, .75fr); }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }}
    .panel-head {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }}
    .panel-title {{ font-weight: 700; font-size: 15px; }}
    .panel-body {{ padding: 14px; }}
    .metric {{ padding: 13px 14px; min-height: 96px; }}
    .metric-label {{ color: var(--muted); font-size: 12px; }}
    .metric-value {{ font-size: 23px; font-weight: 750; margin-top: 9px; white-space: nowrap; }}
    .metric-foot {{ margin-top: 8px; color: var(--muted); font-size: 12px; }}
    .pos {{ color: var(--good); }}
    .neg {{ color: var(--bad); }}
    .warn {{ color: var(--warn); }}
    canvas {{ width: 100%; height: 330px; display: block; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{
      padding: 9px 10px;
      border-bottom: 1px solid #edf0f5;
      text-align: left;
      vertical-align: middle;
      font-size: 13px;
    }}
    th {{
      color: var(--muted);
      font-weight: 650;
      background: #fbfcfe;
      position: sticky;
      top: 0;
      z-index: 1;
    }}
    td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .table-wrap {{ max-height: 420px; overflow: auto; }}
    .tag {{
      display: inline-flex;
      align-items: center;
      border-radius: 6px;
      padding: 3px 7px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid var(--line);
      white-space: nowrap;
    }}
    .tag-main {{ color: var(--good); background: #eaf7f1; border-color: #b8e2d0; }}
    .tag-observe {{ color: var(--blue); background: #edf4ff; border-color: #bfd4f3; }}
    .tag-down {{ color: var(--warn); background: #fff5e7; border-color: #efd3a8; }}
    .tag-pause {{ color: var(--bad); background: #fff0f0; border-color: #f0c2c0; }}
    .bar {{
      height: 8px;
      background: #e9edf4;
      border-radius: 999px;
      overflow: hidden;
      min-width: 90px;
    }}
    .bar > span {{ display: block; height: 100%; background: var(--cyan); }}
    .actions {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }}
    button {{
      border: 1px solid var(--line);
      background: #ffffff;
      color: var(--ink);
      border-radius: 6px;
      padding: 7px 10px;
      cursor: pointer;
      font: inherit;
    }}
    button.active {{ background: #1d2733; color: white; border-color: #1d2733; }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      color: #303846;
      background: #fbfcfe;
      border: 1px solid #edf0f5;
      padding: 10px;
      border-radius: 6px;
      min-height: 44px;
      max-height: 190px;
      overflow: auto;
    }}
    .note {{ color: var(--muted); font-size: 12px; line-height: 1.6; }}
    .stack {{ display: grid; gap: 14px; }}
    @media (max-width: 1100px) {{
      .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .two {{ grid-template-columns: 1fr; }}
      header, main {{ padding-left: 14px; padding-right: 14px; }}
    }}
    @media (max-width: 640px) {{
      .cards {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 20px; }}
      .metric-value {{ font-size: 20px; }}
      th, td {{ padding: 8px 7px; }}
    }}
  </style>
</head>
<body>
  <script id="dashboard-data" type="application/json">{escaped_payload}</script>
  <header>
    <div class="title-row">
      <div>
        <h1>Polymarket 模拟盘可视化</h1>
        <div class="sub">真实收益只统计 final 后的 slippage_final_pnl；浮盈和未结算不进入 ROI。页面每 60 秒自动重载一次。</div>
      </div>
      <div class="actions">
        <span class="badge" id="generated"></span>
        <span class="badge">模拟盘，不是实盘建议</span>
      </div>
    </div>
  </header>
  <main class="grid">
    <section class="grid cards" id="metrics"></section>

    <section class="grid two">
      <div class="panel">
        <div class="panel-head"><div class="panel-title">AI 决策表现</div><span class="badge">TAKE / SKIP</span></div>
        <div class="table-wrap"><table id="aiDecisionTable"></table></div>
      </div>
      <div class="panel">
        <div class="panel-head"><div class="panel-title">延迟套利健康度</div><span class="badge">lead-lag</span></div>
        <div class="table-wrap"><table id="leadLagTable"></table></div>
      </div>
    </section>

    <section class="grid two">
      <div class="panel">
        <div class="panel-head">
          <div class="panel-title">落袋收益曲线</div>
          <div class="actions" id="chartButtons"></div>
        </div>
        <div class="panel-body"><canvas id="equityChart"></canvas></div>
      </div>
      <div class="panel">
        <div class="panel-head"><div class="panel-title">策略真实收益</div><span class="badge">final only</span></div>
        <div class="table-wrap"><table id="strategyTable"></table></div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">调参后真实收益验证</div><span class="badge">post-change cohorts</span></div>
      <div class="table-wrap"><table id="cohortTable"></table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">当前配置表现</div><span class="badge">latest change only</span></div>
      <div class="table-wrap"><table id="currentConfigTable"></table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">BTC 方向分桶证据</div><span class="badge">final only</span></div>
      <div class="table-wrap"><table id="btcBucketTable"></table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">BTC Candidate Rotation</div><span class="badge">report only</span></div>
      <div class="table-wrap"><table id="btcCandidateRotationTable"></table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">BTC Candidate Pool Health</div><span class="badge">observation gate</span></div>
      <div class="table-wrap"><table id="btcCandidatePoolHealthTable"></table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">BTC Candidate Shadow</div><span class="badge">0U shadow</span></div>
      <div class="table-wrap"><table id="btcCandidateShadowTable"></table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">Candidate Sampling Health</div><span class="badge">No-only sample flow</span></div>
      <div class="table-wrap"><table id="candidateSamplingHealthTable"></table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">Market Direction Score</div><span class="badge">final-only direction filter</span></div>
      <div class="table-wrap"><table id="marketDirectionTable"></table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">Direction Retest Candidates</div><span class="badge">wallet + bucket</span></div>
      <div class="table-wrap"><table id="directionRetestTable"></table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">Capital Allocation</div><span class="badge">advisory simulation caps</span></div>
      <div class="table-wrap"><table id="capitalAllocationTable"></table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">Recovery Backtest Matrix</div><span class="badge">allows losses / final PnL only</span></div>
      <div class="table-wrap"><table id="recoveryBacktestTable"></table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">Active Cohort Health</div><span class="badge">mark diagnostic / final-only ROI</span></div>
      <div class="table-wrap"><table id="activeCohortHealthTable"></table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">Active Cohort Guard</div><span class="badge">auto pause protection</span></div>
      <div class="table-wrap"><table id="activeCohortGuardTable"></table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">Active Cohort Settlement</div><span class="badge">end time / closed check</span></div>
      <div class="table-wrap"><table id="activeCohortSettlementTable"></table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">BTC Filter Optimizer</div><span class="badge">parameter search</span></div>
      <div class="table-wrap"><table id="btcFilterOptimizerTable"></table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">Portfolio Backtest</div><span class="badge">1000U / 10U replay</span></div>
      <div class="table-wrap"><table id="portfolioBacktestTable"></table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">Weather Parameter Sweep</div><span class="badge">read-only tuning</span></div>
      <div class="table-wrap"><table id="weatherDirectionSweepTable"></table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">Pending Scenario</div><span class="badge">risk diagnostic</span></div>
      <div class="table-wrap"><table id="pendingScenarioTable"></table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">Stability Verdict</div><span class="badge">stable-positive gate</span></div>
      <div class="table-wrap"><table id="stabilityVerdictTable"></table></div>
    </section>

    <section class="grid two">
      <div class="panel">
        <div class="panel-head"><div class="panel-title">钱包质量排名</div><span class="badge">观察 / 降权 / 暂停建议</span></div>
        <div class="table-wrap"><table id="qualityTable"></table></div>
      </div>
      <div class="panel">
        <div class="panel-head"><div class="panel-title">参数优化建议</div><span class="badge">只建议，不自动应用</span></div>
        <div class="table-wrap"><table id="optimizerTable"></table></div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">观察晋级队列</div><span class="badge">not main ROI</span></div>
      <div class="table-wrap"><table id="observationQueueTable"></table></div>
    </section>

    <section class="grid two">
      <div class="panel">
        <div class="panel-head"><div class="panel-title">策略运行状态</div><span class="badge">暂停状态可见</span></div>
        <div class="table-wrap"><table id="runtimeTable"></table></div>
      </div>
      <div class="panel">
        <div class="panel-head"><div class="panel-title">运行参数健康</div><span class="badge">guarded params</span></div>
        <div class="table-wrap"><table id="runtimeParamTable"></table></div>
      </div>
    </section>

    <section class="grid two">
      <div class="panel">
        <div class="panel-head"><div class="panel-title">Dashboard刷新健康</div><span class="badge">auto refresh</span></div>
        <div class="table-wrap"><table id="dashboardRefreshHealthTable"></table></div>
      </div>
      <div class="panel">
        <div class="panel-head"><div class="panel-title">数据质量 / 结算覆盖</div><span class="badge">final coverage</span></div>
        <div class="table-wrap"><table id="dataQualityTable"></table></div>
      </div>
    </section>

    <section class="grid two">
      <div class="panel">
        <div class="panel-head"><div class="panel-title">审计回填记录</div><span class="badge">pending -> final</span></div>
        <div class="table-wrap"><table id="backfillTable"></table></div>
      </div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">未结算暴露分布</div><span class="badge">pending exposure</span></div>
      <div class="table-wrap"><table id="pendingExposureTable"></table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">暴露一致性检查</div><span class="badge">sim vs audit</span></div>
      <div class="table-wrap"><table id="exposureConsistencyTable"></table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">自动风控守门</div><span class="badge">simulation only</span></div>
      <div class="table-wrap"><table id="riskGuardTable"></table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">拒单原因 / 错失机会漏斗</div><span class="badge">last 24h</span></div>
      <div class="table-wrap"><table id="rejectTable"></table></div>
    </section>

    <section class="panel">
      <div class="panel-head"><div class="panel-title">活跃信号漏斗</div><span class="badge">recent source activity</span></div>
      <div class="table-wrap"><table id="activeFunnelTable"></table></div>
    </section>

    <section class="grid two">
      <div class="panel">
        <div class="panel-head"><div class="panel-title">候选钱包 / 市场池</div><span class="badge">观察池</span></div>
        <div class="table-wrap"><table id="candidateTable"></table></div>
      </div>
      <div class="stack">
        <div class="panel">
          <div class="panel-head"><div class="panel-title">后台进程</div><span class="badge" id="procCount"></span></div>
          <div class="table-wrap"><table id="processTable"></table></div>
        </div>
        <div class="panel">
          <div class="panel-head"><div class="panel-title">最近错误日志</div><span class="badge">tail</span></div>
          <div class="panel-body grid">
            <pre id="logBox"></pre>
            <div class="note">页面是静态快照。要刷新数据，运行 view_dashboard.ps1。</div>
          </div>
        </div>
      </div>
    </section>
  </main>
  <script>
    const data = JSON.parse(document.getElementById("dashboard-data").textContent);
    const fmt = new Intl.NumberFormat("zh-CN", {{ maximumFractionDigits: 4 }});
    const money = v => `${{fmt.format(Number(v || 0))}}U`;
    const pct = v => `${{fmt.format(Number(v || 0))}}%`;
    const clsPnL = v => Number(v || 0) >= 0 ? "pos" : "neg";
    const esc = value => String(value ?? "").replace(/[&<>"']/g, m => ({{"&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#39;"}}[m]));

    document.getElementById("generated").textContent = `生成时间 ${{data.generated_at}}`;

    function metric(label, value, foot, cls="") {{
      return `<div class="panel metric"><div class="metric-label">${{label}}</div><div class="metric-value ${{cls}}">${{value}}</div><div class="metric-foot">${{foot}}</div></div>`;
    }}

    const s = data.summary;
    const ai = data.ai_health;
    const aiRun = data.ai_runtime_health || {{}};
    document.getElementById("metrics").innerHTML = [
      metric("总落袋 PnL", money(s.total_pnl), "只含 final 后 slippage_final_pnl", clsPnL(s.total_pnl)),
      metric("总真实 ROI", pct(s.total_roi), `已结算本金 ${{money(s.total_stake)}}`, clsPnL(s.total_roi)),
      metric("当前配置 PnL", money(s.current_active_pnl), `仅当前活跃配置 | final ${{fmt.format(s.current_active_final)}}`, clsPnL(s.current_active_pnl)),
      metric("当前配置 ROI", pct(s.current_active_roi), `pending ${{fmt.format(s.current_active_pending)}} | 本金 ${{money(s.current_active_stake)}}`, clsPnL(s.current_active_roi)),
      metric("当前配置回撤", money(s.current_active_drawdown), "只看当前活跃配置 final 曲线", s.current_active_drawdown > 0 ? "warn" : ""),
      metric("活跃配置 PnL", money(s.active_pnl), `排除暂停和旧配置 | final ${{fmt.format(s.active_realized)}}`, clsPnL(s.active_pnl)),
      metric("活跃配置 ROI", pct(s.active_roi), `仅最新变更点后`, clsPnL(s.active_roi)),
      metric("已结算交易", fmt.format(s.total_realized), `近 24h 新增 final：${{fmt.format(s.new_24h)}}`),
      metric("未结算交易", fmt.format(s.total_pending), "不计入真实收益"),
      metric("最大回撤", money(s.max_drawdown), "按总落袋曲线计算", s.max_drawdown > Math.abs(s.total_pnl) * .5 ? "warn" : ""),
      metric("AI 落袋 ROI", pct(ai.roi), `TAKE ${{fmt.format(ai.take)}} / SKIP ${{fmt.format(ai.skip)}}`, clsPnL(ai.roi)),
      metric("AI 落袋 PnL", money(ai.pnl), `final ${{fmt.format(ai.final)}} | W/L ${{fmt.format(ai.wins)}}/${{fmt.format(ai.losses)}}`, clsPnL(ai.pnl)),
      metric("AI 扫描健康", `${{fmt.format(Number(aiRun.next_sleep_sec || 0))}}s`, `候选 ${{fmt.format(Number(aiRun.candidates || 0))}} | 错误 ${{fmt.format(Number(aiRun.errors || 0))}} | 连续空扫 ${{fmt.format(Number(aiRun.failure_streak || 0))}}`, Number(aiRun.errors || 0) ? "warn" : ""),
      metric("后台脚本", fmt.format(s.running_processes), `异常 ${{fmt.format(s.runtime_attention)}} | 暂停 ${{fmt.format(s.paused_ok)}}`, s.runtime_attention ? "warn" : ""),
      metric("数据质量", `${{fmt.format(s.stale_pending)}} stale`, `低样本/低覆盖：${{fmt.format(s.low_coverage)}}`, s.stale_pending ? "warn" : ""),
      metric("BTC 候选池", fmt.format(s.candidate_new_observation), `池内等 final：${{fmt.format(s.candidate_waiting_final_in_pool)}} | 离池等 final：${{fmt.format(s.candidate_waiting_final)}} | 可晋级：${{fmt.format(s.candidate_promotion_ready)}}`, s.candidate_failed_gate ? "warn" : "")
    ].join("");

    function renderTable(id, headers, rows, mapper) {{
      const thead = `<thead><tr>${{headers.map(h => `<th class="${{h.num ? "num" : ""}}">${{h.label}}</th>`).join("")}}</tr></thead>`;
      const body = rows.length
        ? rows.map(row => `<tr>${{mapper(row)}}</tr>`).join("")
        : `<tr><td colspan="${{headers.length}}" class="note">暂无数据</td></tr>`;
      document.getElementById(id).innerHTML = thead + `<tbody>${{body}}</tbody>`;
    }}

    const maxAbsPnl = Math.max(1, ...data.realized.map(r => Math.abs(Number(r.pnl || 0))));
    renderTable("aiDecisionTable",
      [{{label:"时间"}},{{label:"资产"}},{{label:"方向"}},{{label:"决策"}},{{label:"信心",num:true}},{{label:"edge",num:true}},{{label:"原因"}}],
      data.ai_decisions,
      r => `<td>${{esc((r.decision_ts || '').slice(5, 19))}}</td><td>${{esc(r.asset)}}</td><td>${{esc(r.direction)}}</td>
            <td><span class="tag ${{r.decision === "TAKE" ? "tag-main" : "tag-down"}}">${{esc(r.decision)}}</span></td>
            <td class="num">${{fmt.format(Number(r.confidence || 0))}}</td>
            <td class="num">${{fmt.format(Number(r.expected_edge_bps || 0))}}bps</td>
            <td>${{esc(r.risk_flags || r.reason || "")}}</td>`);

    renderTable("leadLagTable",
      [{{label:"资产"}},{{label:"窗口"}},{{label:"方向"}},{{label:"ask",num:true}},{{label:"q",num:true}},{{label:"gap",num:true}},{{label:"edge",num:true}}],
      data.lead_lag_candidates,
      r => `<td>${{esc(r.asset)}}</td><td>${{esc(r.duration)}}</td><td>${{esc(r.direction)}}</td>
            <td class="num">${{fmt.format(Number(r.best_ask || 0))}}</td>
            <td class="num">${{fmt.format(Number(r.estimated_q || 0))}}</td>
            <td class="num">${{fmt.format(Number(r.source_to_ask_gap || 0))}}</td>
            <td class="num">${{fmt.format(Number(r.expected_edge_bps || 0))}}bps</td>`);

    renderTable("strategyTable",
      [{{label:"策略"}},{{label:"已结算",num:true}},{{label:"W/L",num:true}},{{label:"PnL",num:true}},{{label:"ROI",num:true}},{{label:"规模"}}],
      data.realized,
      r => {{
        const pnl = Number(r.pnl || 0);
        return `
          <td>${{esc(r.strategy)}}</td>
          <td class="num">${{esc(r.realized)}}</td>
          <td class="num">${{esc(r.wins)}}/${{esc(r.losses)}}</td>
          <td class="num ${{clsPnL(pnl)}}">${{money(pnl)}}</td>
          <td class="num ${{clsPnL(r.roi)}}">${{pct(r.roi)}}</td>
          <td><div class="bar"><span style="width:${{Math.max(2, Math.abs(pnl) / maxAbsPnl * 100)}}%; background:${{pnl >= 0 ? "var(--good)" : "var(--bad)"}}"></span></div></td>`;
      }});

    renderTable("cohortTable",
      [{{label:"调参批次"}},{{label:"策略"}},{{label:"开始时间"}},{{label:"已结算",num:true}},{{label:"W/L",num:true}},{{label:"PnL",num:true}},{{label:"ROI",num:true}},{{label:"本金",num:true}}],
      data.cohorts || [],
      r => `<td>${{esc(r.cohort)}}</td><td>${{esc(r.strategy)}}</td><td>${{esc(r.cutoff_ts)}}</td>
            <td class="num">${{esc(r.realized)}}</td><td class="num">${{esc(r.wins)}}/${{esc(r.losses)}}</td>
            <td class="num ${{clsPnL(r.pnl)}}">${{money(r.pnl)}}</td>
            <td class="num ${{clsPnL(r.roi)}}">${{pct(r.roi)}}</td>
            <td class="num">${{money(r.stake)}}</td>`);

    renderTable("currentConfigTable",
      [{{label:"策略"}},{{label:"状态"}},{{label:"开始"}},{{label:"total",num:true}},{{label:"final",num:true}},{{label:"pending",num:true}},{{label:"W/L",num:true}},{{label:"PnL",num:true}},{{label:"ROI",num:true}},{{label:"判断"}}],
      data.current_config || [],
      r => `<td>${{esc(r.strategy)}}</td><td>${{esc(r.intended_state)}}</td><td>${{esc((r.cutoff_ts || '').slice(5, 16))}}</td>
            <td class="num">${{esc(r.total_since_cutoff)}}</td><td class="num">${{esc(r.final_since_cutoff)}}</td>
            <td class="num">${{esc(r.pending_since_cutoff)}}</td><td class="num">${{esc(r.wins)}}/${{esc(r.losses)}}</td>
            <td class="num ${{clsPnL(r.pnl)}}">${{money(r.pnl)}}</td><td class="num ${{clsPnL(r.roi)}}">${{pct(r.roi)}}</td>
            <td>${{esc(r.status)}}</td>`);

    renderTable("btcBucketTable",
      [{{label:"类型"}},{{label:"分桶"}},{{label:"final",num:true}},{{label:"W/L",num:true}},{{label:"本金",num:true}},{{label:"PnL",num:true}},{{label:"ROI",num:true}},{{label:"动作"}}],
      data.btc_bucket_report || [],
      r => `<td>${{esc(r.bucket_type)}}</td><td>${{esc(r.bucket)}}</td>
            <td class="num">${{esc(r.final)}}</td><td class="num">${{esc(r.wins)}}/${{esc(r.losses)}}</td>
            <td class="num">${{money(r.stake)}}</td>
            <td class="num ${{clsPnL(r.pnl)}}">${{money(r.pnl)}}</td>
            <td class="num ${{clsPnL(r.roi)}}">${{pct(r.roi)}}</td>
            <td>${{esc(r.action)}}</td>`);

    renderTable("btcCandidateRotationTable",
      [{{label:"action"}},{{label:"alias"}},{{label:"rank",num:true}},{{label:"rec"}},{{label:"final/pending",num:true}},{{label:"ROI",num:true}},{{label:"2m+",num:true}},{{label:"10m+",num:true}},{{label:"slip",num:true}},{{label:"reason"}}],
      data.btc_candidate_rotation || [],
      r => `<td><span class="tag ${{tagClass(r.action)}}">${{esc(r.action)}}</span></td><td>${{esc(r.alias)}}</td>
            <td class="num">${{esc(r.candidate_rank)}}</td><td>${{esc(r.discovery_recommendation)}}</td>
            <td class="num">${{esc(r.sim_final)}}/${{esc(r.sim_pending)}}</td>
            <td class="num ${{clsPnL(r.sim_final_roi)}}">${{pct(r.sim_final_roi)}}</td>
            <td class="num">${{pct(r.positive_2m_rate)}}</td><td class="num">${{pct(r.positive_10m_rate)}}</td>
            <td class="num">${{fmt.format(Number(r.avg_slippage_bps || 0))}}bps</td><td>${{esc(r.reason)}}</td>`);

    renderTable("btcCandidatePoolHealthTable",
      [{{label:"health"}},{{label:"in pool"}},{{label:"alias"}},{{label:"rank",num:true}},{{label:"rec"}},{{label:"last seen",num:true}},{{label:"action"}},{{label:"total/final/pending",num:true}},{{label:"ROI",num:true}},{{label:"2m+",num:true}},{{label:"10m+",num:true}},{{label:"reason"}}],
      data.btc_candidate_pool_health || [],
      r => `<td><span class="tag ${{tagClass(r.health)}}">${{esc(r.health)}}</span></td><td>${{esc(r.in_pool)}}</td>
            <td>${{esc(r.alias)}}</td><td class="num">${{esc(r.candidate_rank)}}</td><td>${{esc(r.discovery_recommendation)}}</td>
            <td class="num">${{fmt.format(Number(r.last_seen_age_sec || 0) / 3600)}}h</td>
            <td><span class="tag ${{tagClass(r.rotation_action)}}">${{esc(r.rotation_action)}}</span></td>
            <td class="num">${{esc(r.sim_total)}}/${{esc(r.sim_final)}}/${{esc(r.sim_pending)}}</td>
            <td class="num ${{clsPnL(r.sim_final_roi)}}">${{pct(r.sim_final_roi)}}</td>
            <td class="num">${{pct(r.positive_2m_rate)}}</td><td class="num">${{pct(r.positive_10m_rate)}}</td>
            <td>${{esc(r.reason)}}</td>`);

    renderTable("btcCandidateShadowTable",
      [{{label:"scope"}},{{label:"wallet"}},{{label:"total",num:true}},{{label:"TAKE",num:true}},{{label:"reject",num:true}},{{label:"top reason"}},{{label:"TAKE rate",num:true}},{{label:"slip",num:true}},{{label:"action"}}],
      data.btc_candidate_shadow || [],
      r => `<td>${{esc(r.scope)}}</td><td>${{esc(r.wallet)}}</td><td class="num">${{esc(r.total)}}</td>
            <td class="num">${{esc(r.take)}}</td><td class="num">${{esc(r.reject)}}</td><td>${{esc(r.top_reason)}}</td>
            <td class="num">${{pct(r.take_rate)}}</td><td class="num">${{fmt.format(Number(r.avg_slippage_bps || 0))}}bps</td>
            <td><span class="tag ${{tagClass(r.action)}}">${{esc(r.action)}}</span></td>`);

    renderTable("candidateSamplingHealthTable",
      [{{label:"health"}},{{label:"alias"}},{{label:"rank",num:true}},{{label:"last seen",num:true}},{{label:"open/final/pending",num:true}},{{label:"reject",num:true}},{{label:"yes reject",num:true}},{{label:"old",num:true}},{{label:"fresh No block",num:true}},{{label:"action"}},{{label:"reason"}}],
      data.candidate_sampling_health || [],
      r => `<td><span class="tag ${{tagClass(r.health)}}">${{esc(r.health)}}</span></td><td>${{esc(r.alias)}}</td>
            <td class="num">${{esc(r.candidate_rank)}}</td>
            <td class="num">${{fmt.format(Number(r.last_seen_age_hours || 0))}}h</td>
            <td class="num">${{esc(r.opens_since_cutoff)}}/${{esc(r.final_since_cutoff)}}/${{esc(r.pending_since_cutoff)}}</td>
            <td class="num">${{esc(r.rejects_since_cutoff)}}</td><td class="num">${{esc(r.yes_rejects_since_cutoff)}}</td>
            <td class="num">${{esc(r.old_rejects_since_cutoff)}}</td><td class="num">${{esc(r.fresh_no_rejects_since_cutoff)}}</td>
            <td>${{esc(r.recommended_action)}}</td><td>${{esc(r.reason)}}</td>`);

    renderTable("marketDirectionTable",
      [{{label:"action"}},{{label:"direction"}},{{label:"strategy"}},{{label:"final/pending",num:true}},{{label:"W/L",num:true}},{{label:"PnL",num:true}},{{label:"ROI",num:true}},{{label:"reason"}}],
      data.market_direction || [],
      r => `<td><span class="tag ${{tagClass(r.action)}}">${{esc(r.action)}}</span></td><td>${{esc(r.direction)}}</td>
            <td>${{esc(r.strategy)}}</td><td class="num">${{esc(r.final)}}/${{esc(r.pending)}}</td>
            <td class="num">${{esc(r.wins)}}/${{esc(r.losses)}}</td>
            <td class="num ${{clsPnL(r.pnl)}}">${{money(r.pnl)}}</td>
            <td class="num ${{clsPnL(r.roi)}}">${{pct(r.roi)}}</td><td>${{esc(r.reason)}}</td>`);

    renderTable("directionRetestTable",
      [{{label:"action"}},{{label:"strategy"}},{{label:"wallet"}},{{label:"direction"}},{{label:"final",num:true}},{{label:"W/L",num:true}},{{label:"PnL",num:true}},{{label:"ROI",num:true}},{{label:"stake",num:true}},{{label:"filters"}},{{label:"reason"}}],
      data.direction_retest || [],
      r => `<td><span class="tag ${{tagClass(r.action)}}">${{esc(r.action)}}</span></td><td>${{esc(r.strategy)}}</td><td>${{esc(r.wallet)}}</td>
            <td>${{esc(`${{r.market_type}}:${{r.outcome}}:${{r.price_bucket}}`)}}</td><td class="num">${{esc(r.final)}}</td>
            <td class="num">${{esc(r.wins)}}/${{esc(r.losses)}}</td><td class="num ${{clsPnL(r.pnl)}}">${{money(r.pnl)}}</td>
            <td class="num ${{clsPnL(r.roi)}}">${{pct(r.roi)}}</td><td class="num">${{money(r.suggested_stake_usdc)}}</td>
            <td>${{esc(r.suggested_filters)}}</td><td>${{esc(r.reason)}}</td>`);

    renderTable("capitalAllocationTable",
      [{{label:"tier"}},{{label:"strategy"}},{{label:"stake",num:true}},{{label:"open cap",num:true}},{{label:"final/pending",num:true}},{{label:"PnL",num:true}},{{label:"ROI",num:true}},{{label:"action"}},{{label:"reason"}}],
      data.capital_allocation || [],
      r => `<td><span class="tag ${{tagClass(r.tier)}}">${{esc(r.tier)}}</span></td><td>${{esc(r.strategy)}}</td>
            <td class="num">${{money(r.max_new_trade_stake_usdc)}}</td><td class="num">${{money(r.max_open_stake_usdc)}}</td>
            <td class="num">${{esc(r.realized)}}/${{esc(r.pending)}}</td>
            <td class="num ${{clsPnL(r.pnl)}}">${{money(r.pnl)}}</td><td class="num ${{clsPnL(r.roi)}}">${{pct(r.roi)}}</td>
            <td>${{esc(r.action)}}</td><td>${{esc(r.reason)}}</td>`);

    renderTable("recoveryBacktestTable",
      [{{label:"case"}},{{label:"verdict"}},{{label:"selected",num:true}},{{label:"final/pending",num:true}},{{label:"W/L",num:true}},{{label:"stake",num:true}},{{label:"PnL",num:true}},{{label:"ROI",num:true}},{{label:"max DD",num:true}},{{label:"max open",num:true}},{{label:"notes"}}],
      data.recovery_backtest || [],
      r => `<td>${{esc(r.case)}}</td><td><span class="tag ${{tagClass(r.verdict)}}">${{esc(r.verdict)}}</span></td>
            <td class="num">${{esc(r.selected)}}</td><td class="num">${{esc(r.final)}}/${{esc(r.pending)}}</td>
            <td class="num">${{esc(r.wins)}}/${{esc(r.losses)}}</td><td class="num">${{money(r.stake)}}</td>
            <td class="num ${{clsPnL(r.pnl)}}">${{money(r.pnl)}}</td><td class="num ${{clsPnL(r.roi)}}">${{pct(r.roi)}}</td>
            <td class="num">${{money(r.max_drawdown)}}</td><td class="num">${{money(r.max_open_stake)}}</td><td>${{esc(r.notes)}}</td>`);

    renderTable("activeCohortHealthTable",
      [{{label:"strategy"}},{{label:"action"}},{{label:"total",num:true}},{{label:"final/pending",num:true}},{{label:"W/L",num:true}},{{label:"realized PnL",num:true}},{{label:"realized ROI",num:true}},{{label:"pending stake",num:true}},{{label:"mark PnL",num:true}},{{label:"all win",num:true}},{{label:"all loss",num:true}},{{label:"reason"}}],
      data.active_cohort_health || [],
      r => `<td>${{esc(r.strategy)}}</td><td><span class="tag ${{tagClass(r.action)}}">${{esc(r.action)}}</span></td>
            <td class="num">${{esc(r.total)}}</td><td class="num">${{esc(r.final)}}/${{esc(r.pending)}}</td>
            <td class="num">${{esc(r.wins)}}/${{esc(r.losses)}}</td>
            <td class="num ${{clsPnL(r.realized_pnl)}}">${{money(r.realized_pnl)}}</td><td class="num ${{clsPnL(r.realized_roi)}}">${{pct(r.realized_roi)}}</td>
            <td class="num">${{money(r.pending_stake)}}</td><td class="num ${{clsPnL(r.mark_pnl)}}">${{money(r.mark_pnl)}}</td>
            <td class="num ${{clsPnL(r.all_win_total_pnl)}}">${{money(r.all_win_total_pnl)}}</td>
            <td class="num ${{clsPnL(r.all_loss_total_pnl)}}">${{money(r.all_loss_total_pnl)}}</td><td>${{esc(r.reason)}}</td>`);

    renderTable("activeCohortGuardTable",
      [{{label:"strategy"}},{{label:"decision"}},{{label:"health"}},{{label:"final/pending",num:true}},{{label:"realized PnL",num:true}},{{label:"realized ROI",num:true}},{{label:"mark PnL",num:true}},{{label:"reason"}}],
      data.active_cohort_guard || [],
      r => `<td>${{esc(r.strategy)}}</td><td><span class="tag ${{tagClass(r.guard_decision)}}">${{esc(r.guard_decision)}}</span></td>
            <td>${{esc(r.health_action)}}</td><td class="num">${{esc(r.final)}}/${{esc(r.pending)}}</td>
            <td class="num ${{clsPnL(r.realized_pnl)}}">${{money(r.realized_pnl)}}</td>
            <td class="num ${{clsPnL(r.realized_roi)}}">${{pct(r.realized_roi)}}</td>
            <td class="num ${{clsPnL(r.mark_pnl)}}">${{money(r.mark_pnl)}}</td><td>${{esc(r.reason)}}</td>`);

    renderTable("activeCohortSettlementTable",
      [{{label:"diagnostic"}},{{label:"outcome"}},{{label:"stake",num:true}},{{label:"hours",num:true}},{{label:"closed"}},{{label:"active"}},{{label:"current",num:true}},{{label:"market"}}],
      data.active_cohort_settlement || [],
      r => `<td><span class="tag ${{tagClass(r.diagnostic)}}">${{esc(r.diagnostic)}}</span></td><td>${{esc(r.outcome)}}</td>
            <td class="num">${{money(r.stake)}}</td><td class="num">${{esc(Number(r.hours_to_end || 0).toFixed(2))}}</td>
            <td>${{esc(r.market_closed)}}</td><td>${{esc(r.market_active)}}</td>
            <td class="num">${{esc(Number(r.current_price || 0).toFixed(4))}}</td><td>${{esc(r.title)}}</td>`);

    renderTable("btcFilterOptimizerTable",
      [{{label:"verdict"}},{{label:"final",num:true}},{{label:"W/L",num:true}},{{label:"PnL",num:true}},{{label:"ROI",num:true}},{{label:"DD/PnL",num:true}},{{label:"market"}},{{label:"outcome"}},{{label:"price"}},{{label:"slip",num:true}},{{label:"gap",num:true}},{{label:"age",num:true}},{{label:"open",num:true}},{{label:"notes"}}],
      data.btc_filter_optimizer || [],
      r => `<td><span class="tag ${{tagClass(r.verdict)}}">${{esc(r.verdict)}}</span></td><td class="num">${{esc(r.final)}}</td>
            <td class="num">${{esc(r.wins)}}/${{esc(r.losses)}}</td><td class="num ${{clsPnL(r.pnl)}}">${{money(r.pnl)}}</td>
            <td class="num ${{clsPnL(r.roi)}}">${{pct(r.roi)}}</td><td class="num">${{esc(Number(r.drawdown_to_pnl || 0).toFixed(2))}}</td>
            <td>${{esc(r.market_types)}}</td><td>${{esc(r.outcomes)}}</td><td>${{esc(r.source_price_range)}}</td>
            <td class="num">${{esc(r.max_slippage_bps)}}</td><td class="num">${{esc(r.max_source_to_ask_gap)}}</td>
            <td class="num">${{esc(r.max_source_age_sec)}}s</td><td class="num">${{esc(r.max_open_positions)}}</td><td>${{esc(r.notes)}}</td>`);

    renderTable("portfolioBacktestTable",
      [{{label:"strategy"}},{{label:"accepted",num:true}},{{label:"cap reject",num:true}},{{label:"strategy reject",num:true}},{{label:"final/pending",num:true}},{{label:"W/L",num:true}},{{label:"stake",num:true}},{{label:"PnL",num:true}},{{label:"ROI",num:true}}],
      data.portfolio_backtest || [],
      r => `<td>${{esc(r.strategy)}}</td><td class="num">${{esc(r.accepted)}}</td>
            <td class="num">${{esc(r.rejected_capital)}}</td><td class="num">${{esc(r.rejected_strategy_cap)}}</td>
            <td class="num">${{esc(r.final)}}/${{esc(r.pending)}}</td><td class="num">${{esc(r.wins)}}/${{esc(r.losses)}}</td>
            <td class="num">${{money(r.stake)}}</td><td class="num ${{clsPnL(r.pnl)}}">${{money(r.pnl)}}</td>
            <td class="num ${{clsPnL(r.roi)}}">${{pct(r.roi)}}</td>`);

    renderTable("weatherDirectionSweepTable",
      [{{label:"case"}},{{label:"verdict"}},{{label:"selected",num:true}},{{label:"final/pending",num:true}},{{label:"W/L",num:true}},{{label:"PnL",num:true}},{{label:"ROI",num:true}},{{label:"max DD",num:true}},{{label:"max open",num:true}},{{label:"reject",num:true}},{{label:"notes"}}],
      data.weather_direction_sweep || [],
      r => `<td>${{esc(r.name)}}</td><td><span class="tag ${{tagClass(r.verdict)}}">${{esc(r.verdict)}}</span></td>
            <td class="num">${{esc(r.selected)}}</td><td class="num">${{esc(r.final)}}/${{esc(r.pending)}}</td>
            <td class="num">${{esc(r.wins)}}/${{esc(r.losses)}}</td>
            <td class="num ${{clsPnL(r.pnl)}}">${{money(r.pnl)}}</td><td class="num ${{clsPnL(r.roi)}}">${{pct(r.roi)}}</td>
            <td class="num">${{money(r.max_drawdown)}}</td><td class="num">${{money(r.max_open_stake)}}</td>
            <td class="num">${{Number(r.cap_rejects || 0) + Number(r.strategy_cap_rejects || 0)}}</td><td>${{esc(r.notes)}}</td>`);

    renderTable("pendingScenarioTable",
      [{{label:"strategy"}},{{label:"verdict"}},{{label:"final/pending",num:true}},{{label:"realized",num:true}},{{label:"buffer gap",num:true}},{{label:"new entries"}},{{label:"pending stake",num:true}},{{label:"all win",num:true}},{{label:"all loss",num:true}},{{label:"losses to negative",num:true}},{{label:"notes"}}],
      data.pending_scenario || [],
      r => `<td>${{esc(r.strategy)}}</td><td><span class="tag ${{tagClass(r.verdict)}}">${{esc(r.verdict)}}</span></td>
            <td class="num">${{esc(r.final)}}/${{esc(r.pending)}}</td>
            <td class="num ${{clsPnL(r.realized_pnl)}}">${{money(r.realized_pnl)}}</td>
            <td class="num">${{money(r.profit_buffer_gap)}}</td><td>${{esc(r.new_entries_allowed)}}</td>
            <td class="num">${{money(r.pending_stake)}}</td>
            <td class="num ${{clsPnL(r.all_win_total_pnl)}}">${{money(r.all_win_total_pnl)}}</td>
            <td class="num ${{clsPnL(r.all_loss_total_pnl)}}">${{money(r.all_loss_total_pnl)}}</td>
            <td class="num">${{esc(r.losses_to_turn_negative || "-")}}</td><td>${{esc(r.notes)}}</td>`);

    renderTable("stabilityVerdictTable",
      [{{label:"verdict"}},{{label:"final/pending",num:true}},{{label:"W/L",num:true}},{{label:"PnL",num:true}},{{label:"ROI",num:true}},{{label:"max DD",num:true}},{{label:"DD/PnL",num:true}},{{label:"backtest"}},{{label:"backtest ROI",num:true}},{{label:"BT DD/PnL",num:true}},{{label:"reason"}}],
      data.stability_verdict || [],
      r => `<td><span class="tag ${{tagClass(r.verdict)}}">${{esc(r.verdict)}}</span></td>
            <td class="num">${{esc(r.final_trades)}}/${{esc(r.pending_trades)}}</td><td class="num">${{esc(r.wins)}}/${{esc(r.losses)}}</td>
            <td class="num ${{clsPnL(r.pnl)}}">${{money(r.pnl)}}</td><td class="num ${{clsPnL(r.roi)}}">${{pct(r.roi)}}</td>
            <td class="num">${{money(r.max_drawdown)}}</td><td class="num">${{fmt.format(Number(r.drawdown_to_pnl || 0))}}</td>
            <td>${{esc(r.backtest_case)}}</td><td class="num ${{clsPnL(r.backtest_roi)}}">${{pct(r.backtest_roi)}}</td>
            <td class="num">${{fmt.format(Number(r.backtest_drawdown_to_pnl || 0))}}</td><td>${{esc(r.reason)}}</td>`);

    function tagClass(c) {{
      if (c === "MAIN_POOL") return "tag-main";
      if (c === "OBSERVE") return "tag-observe";
      if (c === "NEAR_PROMOTION_WATCH") return "tag-main";
      if (c === "OBSERVE_MORE" || c === "SHADOW_OBSERVE") return "tag-observe";
      if (c === "PROMOTE_TO_1U_OBSERVE") return "tag-main";
      if (c === "KEEP_SHADOW") return "tag-observe";
      if (c === "NO_ACTION") return "tag-pause";
      if (c === "CORE_OBSERVATION") return "tag-main";
      if (c === "ACTIVE_10U_RETEST") return "tag-main";
      if (c === "STABLE_POSITIVE") return "tag-main";
      if (c === "NOT_STABLE_YET") return "tag-observe";
      if (c === "CANDIDATE") return "tag-main";
      if (c === "WEAK_SAMPLE") return "tag-observe";
      if (c === "REJECT") return "tag-pause";
      if (c === "NO_PENDING") return "tag-main";
      if (c === "PENDING_BUFFERED") return "tag-main";
      if (c === "PENDING_CAN_ERASE_PROFIT") return "tag-down";
      if (c === "NO_ACTIVE_STRATEGY") return "tag-pause";
      if (c === "SIM_STALE_OPEN") return "tag-down";
      if (c === "OK") return "tag-main";
      if (c === "CANDIDATE_OBSERVATION" || c === "TINY_RETEST" || c === "SMALL_OBSERVATION" || c === "WAITING_FINAL") return "tag-observe";
      if (c === "PAUSED_ZERO" || c === "ZERO") return "tag-pause";
      if (c === "PROMOTE_CANDIDATE") return "tag-main";
      if (c === "PRIMARY_CANDIDATE" || c === "OBSERVE_TO_PROMOTE") return "tag-main";
      if (c === "OBSERVE_PENDING" || c === "NO_FINAL_SAMPLE" || c === "RETEST_TINY") return "tag-observe";
      if (c === "KEEP_OBSERVING" || c === "ADD_TO_OBSERVATION") return "tag-observe";
      if (c === "NEW_OBSERVATION" || c === "WAITING_FINAL_OFF_POOL") return "tag-observe";
      if (c === "PROMOTION_READY") return "tag-main";
      if (c === "FAILED_FINAL_GATE") return "tag-pause";
      if (c === "SAMPLING") return "tag-main";
      if (c === "WAITING_FRESH_NO") return "tag-observe";
      if (c === "YES_HEAVY_LIVE_FLOW" || c === "FRESH_NO_BLOCKED") return "tag-down";
      if (c === "STALE_SLOT") return "tag-pause";
      if (c === "DOWNWEIGHT_OBSERVATION") return "tag-down";
      if (c === "REMOVE_OR_SKIP" || c === "STOP" || c === "BLOCK" || c === "STOP_OR_TINY_OBSERVE") return "tag-pause";
      if (c === "DOWNWEIGHT") return "tag-down";
      if (c === "PAUSE_SUGGESTED") return "tag-pause";
      return "";
    }}

    renderTable("qualityTable",
      [{{label:"分层"}},{{label:"策略"}},{{label:"钱包"}},{{label:"已结算",num:true}},{{label:"PnL",num:true}},{{label:"ROI",num:true}},{{label:"回撤",num:true}},{{label:"动作"}}],
      data.quality,
      r => `<td><span class="tag ${{tagClass(r.classification)}}">${{esc(r.classification)}}</span></td>
            <td>${{esc(r.strategy)}}</td><td>${{esc(r.wallet)}}</td>
            <td class="num">${{esc(r.realized_trades)}}</td>
            <td class="num ${{clsPnL(r.realized_pnl)}}">${{money(r.realized_pnl)}}</td>
            <td class="num ${{clsPnL(r.realized_roi_pct)}}">${{pct(r.realized_roi_pct)}}</td>
            <td class="num">${{money(r.max_drawdown)}}</td>
            <td>${{esc(r.recommended_action)}}</td>`);

    renderTable("observationQueueTable",
      [{{label:"rank",num:true}},{{label:"action"}},{{label:"source"}},{{label:"strategy"}},{{label:"wallet"}},{{label:"stake",num:true}},{{label:"cap",num:true}},{{label:"final/pending",num:true}},{{label:"ROI",num:true}},{{label:"reason"}}],
      data.observation_queue || [],
      r => `<td class="num">${{esc(r.rank)}}</td><td><span class="tag ${{tagClass(r.action)}}">${{esc(r.action)}}</span></td>
            <td>${{esc(r.source)}}</td><td>${{esc(r.strategy)}}</td><td>${{esc(r.wallet)}}</td>
            <td class="num">${{money(r.suggested_stake_usdc)}}</td><td class="num">${{money(r.max_open_stake_usdc)}}</td>
            <td class="num">${{esc(r.realized_trades)}}/${{esc(r.pending_trades)}}</td>
            <td class="num ${{clsPnL(r.roi)}}">${{pct(r.roi)}}</td><td>${{esc(r.reason)}}</td>`);

    renderTable("optimizerTable",
      [{{label:"钱包"}},{{label:"动作"}},{{label:"仓位",num:true}},{{label:"延迟",num:true}},{{label:"滑点",num:true}},{{label:"gap",num:true}},{{label:"市场上限",num:true}}],
      data.optimizer,
      r => `<td>${{esc(r.wallet)}}</td><td>${{esc(r.recommended_action)}}</td>
            <td class="num">${{money(r.stake_usdc)}}</td><td class="num">${{esc(r.max_source_age_sec)}}s</td>
            <td class="num">${{esc(r.max_slippage_bps)}}bps</td><td class="num">${{esc(r.max_source_to_ask_gap)}}</td>
            <td class="num">${{money(r.max_market_stake_usdc)}}</td>`);

    function statusClass(value) {{
      if (String(value || "").startsWith("OK")) return "tag-main";
      if (String(value || "").startsWith("ATTENTION")) return "tag-pause";
      return "tag-observe";
    }}

    renderTable("runtimeTable",
      [{{label:"策略"}},{{label:"目标"}},{{label:"运行"}},{{label:"PID",num:true}},{{label:"状态"}},{{label:"说明"}}],
      data.runtime_status || [],
      r => `<td>${{esc(r.strategy)}}</td><td>${{esc(r.intended_state)}}</td><td>${{esc(r.runtime_state)}}</td>
            <td class="num">${{esc(r.pid || "-")}}</td>
            <td><span class="tag ${{statusClass(r.status)}}">${{esc(r.status)}}</span></td>
            <td>${{esc(r.note)}}</td>`);

    renderTable("runtimeParamTable",
      [{{label:"策略"}},{{label:"状态"}},{{label:"PID",num:true}},{{label:"stake",num:true}},{{label:"bankroll",num:true}},{{label:"max open",num:true}},{{label:"buffer",num:true}},{{label:"说明"}}],
      data.runtime_parameter_health || [],
      r => `<td>${{esc(r.strategy)}}</td><td><span class="tag ${{statusClass(r.status)}}">${{esc(r.status)}}</span></td>
            <td class="num">${{esc(r.pid || "-")}}</td><td class="num">${{money(r.stake_usdc)}}</td>
            <td class="num">${{money(r.bankroll_usdc)}}</td><td class="num">${{esc(r.max_open_positions)}}</td>
            <td class="num">${{money(r.min_realized_pnl_buffer_usdc)}}</td><td>${{esc(r.reason)}}</td>`);

    renderTable("dashboardRefreshHealthTable",
      [{{label:"状态"}},{{label:"exit",num:true}},{{label:"最近完成"}},{{label:"说明"}}],
      data.dashboard_refresh_health || [],
      r => `<td><span class="tag ${{statusClass(r.status)}}">${{esc(r.status)}}</span></td>
            <td class="num">${{esc(r.last_exit_code || "-")}}</td><td>${{esc(r.last_refresh_done)}}</td><td>${{esc(r.reason)}}</td>`);

    function qualityClass(value) {{
      if (value === "OK") return "tag-main";
      if (value === "NO_DATA" || value === "LOW_FINAL_SAMPLE") return "tag-observe";
      if (value === "LOW_FINAL_COVERAGE") return "tag-down";
      return "tag-pause";
    }}

    renderTable("dataQualityTable",
      [{{label:"策略"}},{{label:"final",num:true}},{{label:"pending",num:true}},{{label:"覆盖率",num:true}},{{label:"pending本金",num:true}},{{label:"最旧pending",num:true}},{{label:"质量"}},{{label:"动作"}}],
      data.data_quality || [],
      r => `<td>${{esc(r.strategy)}}</td><td class="num">${{esc(r.final_rows)}}</td><td class="num">${{esc(r.pending_rows)}}</td>
            <td class="num">${{pct(r.final_coverage_pct)}}</td><td class="num">${{money(r.pending_stake_usdc)}}</td>
            <td class="num">${{fmt.format(Number(r.oldest_pending_age_hours || 0))}}h</td>
            <td><span class="tag ${{qualityClass(r.data_quality)}}">${{esc(r.data_quality)}}</span></td>
            <td>${{esc(r.recommended_action)}}</td>`);

    renderTable("backfillTable",
      [{{label:"时间"}},{{label:"策略"}},{{label:"pending前",num:true}},{{label:"pending后",num:true}},{{label:"新增final",num:true}},{{label:"批量",num:true}},{{label:"状态"}}],
      data.backfill_summary || [],
      r => `<td>${{esc((r.ts || '').slice(5, 19))}}</td><td>${{esc(r.strategy)}}</td>
            <td class="num">${{esc(r.before_pending)}}</td><td class="num">${{esc(r.after_pending)}}</td>
            <td class="num">${{esc(r.new_final)}}</td><td class="num">${{esc(r.batch_limit)}}</td>
            <td>${{esc(r.status)}}</td>`);

    renderTable("pendingExposureTable",
      [{{label:"策略"}},{{label:"pending",num:true}},{{label:"本金",num:true}},{{label:"近final",num:true}},{{label:"closed"}},{{label:"最旧",num:true}},{{label:"日期"}},{{label:"当前价"}},{{label:"方向"}},{{label:"市场"}}],
      data.pending_exposure || [],
      r => `<td>${{esc(r.strategy)}}</td><td class="num">${{esc(r.pending_rows)}}</td>
            <td class="num">${{money(r.pending_stake)}}</td>
            <td class="num">${{esc(r.near_final_rows || "0")}}</td>
            <td>${{esc(r.market_closed || "")}}</td>
            <td class="num">${{fmt.format(Number(r.oldest_age_hours || 0))}}h</td>
            <td>${{esc(r.date_hint)}}</td><td>${{esc(r.current_prices || "")}}</td><td>${{esc(r.outcomes)}}</td>
            <td>${{esc(r.title || r.slug || r.event_slug)}}</td>`);

    renderTable("exposureConsistencyTable",
      [{{label:"策略"}},{{label:"sim open",num:true}},{{label:"audit open",num:true}},{{label:"extra sim",num:true}},{{label:"状态"}},{{label:"动作"}}],
      data.exposure_consistency || [],
      r => `<td>${{esc(r.strategy)}}</td>
            <td class="num">${{esc(r.sim_open_count)}} / ${{money(r.sim_open_stake)}}</td>
            <td class="num">${{esc(r.audit_open_count)}} / ${{money(r.audit_open_stake)}}</td>
            <td class="num">${{esc(r.extra_sim_open_count)}} / ${{money(r.extra_sim_open_stake)}}</td>
            <td><span class="tag ${{tagClass(r.status)}}">${{esc(r.status)}}</span></td><td>${{esc(r.action)}}</td>`);

    renderTable("riskGuardTable",
      [{{label:"策略"}},{{label:"决策"}},{{label:"final",num:true}},{{label:"pending",num:true}},{{label:"W/L",num:true}},{{label:"PnL",num:true}},{{label:"ROI",num:true}},{{label:"原因"}}],
      data.risk_guard_status || [],
      r => `<td>${{esc(r.strategy)}}</td><td>${{esc(r.guard_decision)}}</td>
            <td class="num">${{esc(r.final_since_cutoff)}}</td><td class="num">${{esc(r.pending_since_cutoff)}}</td>
            <td class="num">${{esc(r.wins)}}/${{esc(r.losses)}}</td>
            <td class="num ${{clsPnL(r.pnl)}}">${{money(r.pnl)}}</td>
            <td class="num ${{clsPnL(r.roi)}}">${{pct(r.roi)}}</td>
            <td>${{esc(r.reason || r.status || "")}}</td>`);

    renderTable("rejectTable",
      [{{label:"策略"}},{{label:"原因"}},{{label:"次数",num:true}},{{label:"平均延迟",num:true}},{{label:"平均滑点",num:true}},{{label:"平均gap",num:true}}],
      data.reject_report || [],
      r => `<td>${{esc(r.strategy)}}</td><td>${{esc(r.reason)}}</td><td class="num">${{esc(r.count)}}</td>
            <td class="num">${{fmt.format(Number(r.avg_signal_age_sec || 0))}}s</td>
            <td class="num">${{fmt.format(Number(r.avg_slippage_bps || 0))}}bps</td>
            <td class="num">${{fmt.format(Number(r.avg_source_to_ask_gap || 0))}}</td>`);

    renderTable("activeFunnelTable",
      [{{label:"策略"}},{{label:"原因"}},{{label:"数量",num:true}},{{label:"平均延迟",num:true}}],
      data.active_funnel || [],
      r => `<td>${{esc(r.strategy)}}</td><td>${{esc(r.reason)}}</td><td class="num">${{esc(r.count)}}</td>
            <td class="num">${{fmt.format(Number(r.avg_signal_age_sec || 0))}}s</td>`);

    renderTable("candidateTable",
      [{{label:"类型"}},{{label:"别名"}},{{label:"交易",num:true}},{{label:"观察量",num:true}},{{label:"来源"}}],
      data.candidates,
      r => `<td>${{esc(r.market_type)}}</td><td>${{esc(r.alias)}}</td>
            <td class="num">${{esc(r.trade_count)}}</td><td class="num">${{money(r.observed_volume)}}</td>
            <td>${{esc(r.source)}}</td>`);

    document.getElementById("procCount").textContent = `${{data.processes.length}} running`;
    renderTable("processTable",
      [{{label:"PID",num:true}},{{label:"脚本"}}],
      data.processes,
      r => `<td class="num">${{esc(r.pid)}}</td><td>${{esc(r.script)}}</td>`);

    const logs = Object.entries(data.logs).filter(([_, v]) => v).map(([k, v]) => `=== ${{k}} ===\\n${{v}}`).join("\\n\\n");
    document.getElementById("logBox").textContent = logs || "暂无错误日志。";

    const chartModes = [
      {{"key":"total_equity","label":"总曲线"}},
      {{"key":"active_current_equity","label":"当前配置"}},
      {{"key":"strategy_equity","label":"按策略"}},
      {{"key":"wallet_equity","label":"按钱包"}}
    ];
    let chartMode = "total_equity";
    document.getElementById("chartButtons").innerHTML = chartModes.map(m => `<button data-mode="${{m.key}}" class="${{m.key === chartMode ? "active" : ""}}">${{m.label}}</button>`).join("");
    document.getElementById("chartButtons").addEventListener("click", e => {{
      if (e.target.dataset.mode) {{
        chartMode = e.target.dataset.mode;
        [...document.querySelectorAll("#chartButtons button")].forEach(b => b.classList.toggle("active", b.dataset.mode === chartMode));
        drawChart();
      }}
    }});

    function chartSeries() {{
      if (chartMode === "total_equity") {{
        return [{{name:"总落袋", color:"#235caa", points:data.equity.map((r, i) => [i, Number(r.total_equity || 0)])}}];
      }}
      if (chartMode === "active_current_equity") {{
        const points = (data.current_equity || [])
          .filter(r => r.intended_state !== "PAUSED")
          .map((r, i) => [i, Number(r.active_current_equity || 0)]);
        return [{{name:"当前配置", color:"#16845b", points}}];
      }}
      const groups = new Map();
      for (const r of data.equity) {{
        const name = chartMode === "strategy_equity" ? r.strategy : r.wallet;
        groups.set(name, [ ...(groups.get(name) || []), Number(r[chartMode] || 0) ]);
      }}
      const colors = ["#235caa","#16845b","#b42318","#a15c07","#007c89","#6741d9","#455468","#c2410c"];
      return [...groups.entries()].slice(0, 8).map(([name, vals], idx) => ({{name, color:colors[idx % colors.length], points:vals.map((v, i) => [i, v])}}));
    }}

    function drawChart() {{
      const canvas = document.getElementById("equityChart");
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.max(600, Math.floor(rect.width * dpr));
      canvas.height = Math.floor(rect.height * dpr);
      const ctx = canvas.getContext("2d");
      ctx.scale(dpr, dpr);
      const w = rect.width, h = rect.height;
      ctx.clearRect(0, 0, w, h);
      const pad = {{l:58, r:16, t:18, b:34}};
      const series = chartSeries().filter(s => s.points.length);
      if (!series.length) {{
        ctx.fillStyle = "#687386"; ctx.fillText("暂无 final 收益曲线", 24, 36); return;
      }}
      const all = series.flatMap(s => s.points.map(p => p[1]));
      let minY = Math.min(0, ...all), maxY = Math.max(0, ...all);
      if (minY === maxY) {{ minY -= 1; maxY += 1; }}
      const maxX = Math.max(1, ...series.map(s => s.points.length - 1));
      const x = i => pad.l + (i / maxX) * (w - pad.l - pad.r);
      const y = v => pad.t + (maxY - v) / (maxY - minY) * (h - pad.t - pad.b);

      ctx.strokeStyle = "#d9dee8"; ctx.lineWidth = 1;
      ctx.beginPath();
      for (let i = 0; i <= 4; i++) {{
        const yy = pad.t + i / 4 * (h - pad.t - pad.b);
        ctx.moveTo(pad.l, yy); ctx.lineTo(w - pad.r, yy);
      }}
      ctx.stroke();
      ctx.fillStyle = "#687386"; ctx.font = "12px Segoe UI, Arial";
      for (let i = 0; i <= 4; i++) {{
        const v = maxY - i / 4 * (maxY - minY);
        ctx.fillText(v.toFixed(1) + "U", 8, pad.t + i / 4 * (h - pad.t - pad.b) + 4);
      }}
      for (const s of series) {{
        ctx.strokeStyle = s.color; ctx.lineWidth = 2;
        ctx.beginPath();
        s.points.forEach((p, idx) => idx ? ctx.lineTo(x(p[0]), y(p[1])) : ctx.moveTo(x(p[0]), y(p[1])));
        ctx.stroke();
      }}
      let lx = pad.l, ly = h - 16;
      for (const s of series.slice(0, 6)) {{
        ctx.fillStyle = s.color; ctx.fillRect(lx, ly - 9, 10, 10);
        ctx.fillStyle = "#1d2733"; ctx.fillText(s.name.slice(0, 22), lx + 15, ly);
        lx += Math.min(210, 35 + s.name.length * 7);
        if (lx > w - 180) {{ lx = pad.l; ly -= 18; }}
      }}
    }}

    window.addEventListener("resize", drawChart);
    drawChart();
    setTimeout(() => window.location.reload(), 60000);
  </script>
</body>
</html>
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="Regenerate source reports before rendering the dashboard")
    parser.add_argument("--output", type=Path, default=ROOT / "dashboard.html")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.refresh:
        refresh_reports()
    data = build_data()
    args.output.write_text(render_html(data), encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
