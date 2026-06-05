#!/usr/bin/env python3
"""Generate a concise local daily report for the running simulations."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from summarize_bot_performance import (
    summarize_arb,
    summarize_btc,
    summarize_btc_directional_candidate_copy,
    summarize_btc_directional_copy,
    summarize_cream,
    summarize_cream_copy,
    summarize_oracle_sources,
    summarize_smart_copy,
    summarize_smart_direction_retest,
    summarize_weather_wallet_copy,
)
from realized_pnl_report import render as render_realized_pnl
from strategy_optimizer_report import build_recommendations, render as render_optimizer
from wallet_quality_engine import all_scores, render as render_wallet_quality
from data_quality_report import build_rows as build_data_quality_rows, render as render_data_quality
from runtime_strategy_status import build_rows as build_runtime_rows


def tail(path: Path, n: int = 8) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]


def fnum(value: str | None) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def latest_csv_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            row_id = row.get("id") or str(len(rows))
            rows[row_id] = row
    return rows


def wallet_quality_table(path: Path, title: str, metric: str = "slippage_pnl_1h") -> list[str]:
    rows = [
        row
        for row in latest_csv_rows(path).values()
        if row.get("wallet_name") and row.get(metric) not in {None, ""}
    ]
    if not rows:
        return [f"## {title}", "", "No audit marks with this metric yet.", ""]
    stats: dict[str, dict[str, float]] = {}
    for row in rows:
        wallet = row.get("wallet_name") or "unknown"
        item = stats.setdefault(wallet, {"n": 0, "fills": 0, "pnl": 0.0, "slippage": 0.0, "wins": 0})
        pnl = fnum(row.get(metric))
        item["n"] += 1
        item["fills"] += 1 if str(row.get("would_live_fill")).upper() == "YES" else 0
        item["pnl"] += pnl
        item["slippage"] += fnum(row.get("slippage_bps"))
        item["wins"] += 1 if pnl > 0 else 0
    ranked = sorted(stats.items(), key=lambda item: item[1]["pnl"], reverse=True)
    lines = [
        f"## {title}",
        "",
        f"| wallet | samples | live_fill% | win% | avg_slippage_bps | {metric} |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for wallet, item in ranked[:12]:
        n = item["n"] or 1
        lines.append(
            f"| {wallet} | {int(item['n'])} | {item['fills'] / n * 100:.1f}% | "
            f"{item['wins'] / n * 100:.1f}% | {item['slippage'] / n:.0f} | {item['pnl']:.4f}U |"
        )
    lines.append("")
    return lines


def file_excerpt(path: Path, title: str, n: int = 30) -> list[str]:
    if not path.exists():
        return [f"## {title}", "", "No data yet.", ""]
    return [f"## {title}", "", "```text", *tail(path, n), "```", ""]


def render_runtime(rows: list[dict[str, str]]) -> str:
    lines = [
        "| strategy | intended | runtime | pid | status | note |",
        "|---|---|---|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['strategy']} | {row['intended_state']} | {row['runtime_state']} | "
            f"{row['pid'] or '-'} | {row['status']} | {row['note']} |"
        )
    return "\n".join(lines)


def main() -> int:
    out = Path("daily_report.md")
    quality_rows = all_scores()
    lines = [
        "# Polymarket Daily Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Wallet Quality / 钱包质量",
        "",
        render_wallet_quality(quality_rows),
        "",
        "## Runtime Status / 运行状态",
        "",
        render_runtime(build_runtime_rows()),
        "",
        "## Data Quality / 结算覆盖",
        "",
        render_data_quality(build_data_quality_rows()),
        "",
        *file_excerpt(Path("audit_backfill_summary.csv"), "Audit Backfill / 审计回填", 20),
        *file_excerpt(Path("signal_reject_report.md"), "Signal Rejects / 拒单原因", 30),
        *file_excerpt(Path("active_signal_funnel.md"), "Active Signal Funnel / 活跃信号漏斗", 30),
        *file_excerpt(Path("capital_allocation_report.md"), "Capital Allocation / 仓位分配", 30),
        "## Optimizer Suggestions / 参数建议",
        "",
        render_optimizer(build_recommendations(quality_rows)),
        "",
        *file_excerpt(Path("candidate_wallets.md"), "Candidate Wallets / 候选钱包", 40),
        "## Performance",
        "",
        "### Realized / 落袋口径",
        "",
        "```text",
        render_realized_pnl(),
        "```",
        "",
        *file_excerpt(Path("realized_cohort_report.csv"), "Post-change Cohorts / 调参后真实收益", 20),
        *file_excerpt(Path("current_config_report.md"), "Current Config / 当前配置表现", 30),
        "",
        "### Mark-to-market / 观察口径",
        "",
        "```text",
        summarize_btc(Path("btc_signal_trades.csv")),
        "",
        summarize_arb(Path("dry_run_arb_log.csv")),
        "",
        summarize_cream(Path("creamcream_activity.csv")),
        "",
        summarize_cream_copy(Path("creamcream_copy_sim.csv")),
        "",
        summarize_smart_copy(Path("smart_wallet_copy_sim.csv")),
        "",
        summarize_smart_direction_retest(Path("smart_direction_retest_sim.csv")),
        "",
        summarize_btc_directional_copy(Path("btc_directional_wallet_copy_sim.csv")),
        "",
        summarize_btc_directional_candidate_copy(Path("btc_directional_candidate_copy_sim.csv")),
        "",
        summarize_weather_wallet_copy(Path("weather_wallet_copy_sim.csv")),
        "",
        summarize_oracle_sources(Path("oracle_source_map.csv")),
        "```",
        "",
        *wallet_quality_table(Path("smart_wallet_trade_audit.csv"), "Smart Wallet Audit Quality", "slippage_pnl_10m"),
        *wallet_quality_table(Path("smart_direction_retest_trade_audit.csv"), "Smart Direction Retest Audit Quality", "slippage_pnl_10m"),
        *wallet_quality_table(Path("weather_wallet_trade_audit.csv"), "Weather Wallet Audit Quality"),
        *wallet_quality_table(Path("btc_directional_trade_audit.csv"), "BTC Directional Audit Quality"),
        *wallet_quality_table(Path("btc_directional_candidate_trade_audit.csv"), "BTC Directional Candidate Audit Quality"),
        *wallet_quality_table(Path("ai_signal_trade_audit.csv"), "AI Signal Audit Quality", "slippage_pnl_10m"),
        *file_excerpt(Path("ai_signal_decisions.csv"), "AI Signal Decisions", 20),
        "## Recent BTC Log",
        "",
        "```text",
        *tail(Path("btc_signal_console.log"), 12),
        "```",
        "",
        "## Recent Basket Arb Log",
        "",
        "```text",
        *tail(Path("dry_run_console.log"), 8),
        "```",
        "",
        "## Recent CreamCream Watcher",
        "",
        "```text",
        *tail(Path("creamcream_console.log"), 10),
        "```",
        "",
        "## Recent CreamCream Copy Sim",
        "",
        "```text",
        *tail(Path("creamcream_copy_console.log"), 10),
        "```",
        "",
        "## Recent Smart Wallet Copy Sim",
        "",
        "```text",
        *tail(Path("smart_wallet_copy_console.log"), 10),
        "```",
        "",
        "## Recent Smart Direction Retest",
        "",
        "```text",
        *tail(Path("smart_direction_retest_console.log"), 10),
        "```",
        "",
        "## Recent AI Signal Sim",
        "",
        "```text",
        *tail(Path("ai_signal_console.log"), 10),
        "```",
        "",
        "## Recent Bond-Style Scanner",
        "",
        "```text",
        *tail(Path("bond_style_console.log"), 10),
        "```",
        "",
        "## Latest Bond-Style Alert",
        "",
        "```text",
        *tail(Path("latest_bond_style_alert.txt"), 20),
        "```",
    ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
