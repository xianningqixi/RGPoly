#!/usr/bin/env python3
"""Report realized simulation PnL only.

Realized means the audit row has a final result and uses slippage-adjusted final
PnL. Mark-to-market values are intentionally excluded.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path


AUDIT_FILES = {
    "CreamCream copy": Path("creamcream_trade_audit.csv"),
    "Smart Wallet copy": Path("smart_wallet_trade_audit.csv"),
    "BTC signal": Path("btc_signal_trades.csv"),
    "BTC directional copy": Path("btc_directional_trade_audit.csv"),
    "ETH directional copy": Path("eth_directional_trade_audit.csv"),
    "SOL directional copy": Path("sol_directional_trade_audit.csv"),
    "BNB directional copy": Path("bnb_directional_trade_audit.csv"),
    "BTC directional candidate copy": Path("btc_directional_candidate_trade_audit.csv"),
    "Smart direction retest": Path("smart_direction_retest_trade_audit.csv"),
    "Weather direction retest": Path("weather_direction_retest_trade_audit.csv"),
    "Weather high-prob wallet copy": Path("weather_high_prob_trade_audit.csv"),
    "BTC directional live shadow": Path("btc_directional_live_shadow_trade_audit.csv"),
    "Weather high-prob live shadow": Path("weather_high_prob_live_shadow_trade_audit.csv"),
    "BTC No-dominant candidate copy": Path("btc_no_dominant_trade_audit.csv"),
    "BTC Yes candidate observation copy": Path("btc_yes_candidate_observation_trade_audit.csv"),
    "BTC high-win candidate observation copy": Path("btc_high_win_candidate_observation_trade_audit.csv"),
    "ETH high-quality directional copy": Path("eth_high_quality_directional_trade_audit.csv"),
    "Weather wallet copy": Path("weather_wallet_trade_audit.csv"),
    "AI signal copy": Path("ai_signal_trade_audit.csv"),
}

STRATEGY_KEYS = {
    "CreamCream copy": "creamcream_copy",
    "Smart Wallet copy": "smart_wallet_copy",
    "BTC signal": "btc_signal",
    "BTC directional copy": "btc_directional_copy",
    "ETH directional copy": "eth_directional_copy",
    "SOL directional copy": "sol_directional_copy",
    "BNB directional copy": "bnb_directional_copy",
    "BTC directional candidate copy": "btc_directional_candidate_copy",
    "Smart direction retest": "smart_direction_retest",
    "Weather direction retest": "weather_direction_retest",
    "Weather high-prob wallet copy": "weather_high_prob_wallet_copy",
    "BTC directional live shadow": "btc_directional_live_shadow",
    "Weather high-prob live shadow": "weather_high_prob_live_shadow",
    "BTC No-dominant candidate copy": "btc_no_dominant_candidate_copy",
    "BTC Yes candidate observation copy": "btc_yes_candidate_observation_copy",
    "BTC high-win candidate observation copy": "btc_high_win_candidate_observation_copy",
    "ETH high-quality directional copy": "eth_high_quality_directional_copy",
    "Weather wallet copy": "weather_wallet_copy",
    "AI signal copy": "ai_signal_copy",
}

CHANGE_POINTS = Path("strategy_change_points.csv")


def fnum(value: str | None) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def latest_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            row_id = row.get("id") or str(len(rows))
            rows[row_id] = row
    return rows


def final_result_value(row: dict[str, str]) -> str:
    result = row.get("final_result") or ""
    if result in {"WIN", "LOSS"}:
        return result
    if row.get("status") == "RESOLVED" and row.get("result") in {"WIN", "LOSS"}:
        return row.get("result") or ""
    return ""


def final_pnl_value(row: dict[str, str]) -> float:
    if row.get("fee_adjusted_final_pnl") not in {"", None}:
        return fnum(row.get("fee_adjusted_final_pnl"))
    if row.get("slippage_final_pnl") not in {"", None}:
        return fnum(row.get("slippage_final_pnl"))
    if row.get("status") == "RESOLVED" and row.get("pnl") not in {"", None}:
        return fnum(row.get("pnl"))
    return 0.0


def is_realized(row: dict[str, str]) -> bool:
    if final_result_value(row) not in {"WIN", "LOSS"}:
        return False
    if row.get("slippage_final_pnl") not in {"", None}:
        return True
    return row.get("status") == "RESOLVED" and row.get("pnl") not in {"", None}


def realized_rows(path: Path) -> list[dict[str, str]]:
    rows = latest_rows(path)
    return [row for row in rows.values() if is_realized(row)]


def parse_dt(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def row_time_value(row: dict[str, str]) -> str:
    return row.get("detected_time") or row.get("signal_time") or row.get("audit_ts") or row.get("ts") or ""


def wallet_value(row: dict[str, str]) -> str:
    if row.get("wallet_name"):
        return row.get("wallet_name") or "unknown"
    if row.get("wallet"):
        return row.get("wallet") or "unknown"
    if row.get("status") == "RESOLVED" and row.get("entry_price_btc"):
        slug = row.get("slug") or ""
        if "15m" in slug:
            return "BTC_signal_15m"
        if "5m" in slug:
            return "BTC_signal_5m"
        if "4h" in slug:
            return "BTC_signal_4h"
        return "BTC_signal"
    return "unknown"


def read_change_points(path: Path = CHANGE_POINTS) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def latest_change_points() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for row in read_change_points():
        key = row.get("strategy") or ""
        cutoff = row.get("cutoff_ts") or ""
        if not key or not cutoff:
            continue
        if key not in out or parse_dt(cutoff) >= parse_dt(out[key].get("cutoff_ts", "")):
            out[key] = row
    return out


def summarize_file(name: str, path: Path) -> dict[str, object]:
    rows = latest_rows(path)
    realized = realized_rows(path)
    stake = sum(fnum(row.get("stake")) for row in realized)
    pnl = sum(final_pnl_value(row) for row in realized)
    wins = [row for row in realized if final_pnl_value(row) > 0]
    losses = [row for row in realized if final_pnl_value(row) < 0]
    roi = pnl / stake * 100 if stake else 0.0
    pending = len(rows) - len(realized)
    return {
        "strategy": name,
        "strategy_key": STRATEGY_KEYS.get(name, name.lower().replace(" ", "_")),
        "total": len(rows),
        "realized": len(realized),
        "pending": pending,
        "wins": len(wins),
        "losses": len(losses),
        "stake": stake,
        "pnl": pnl,
        "roi": roi,
    }


def read_runtime_status(path: Path = Path("runtime_strategy_status.csv")) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return {row.get("strategy", ""): row.get("intended_state", "") for row in csv.DictReader(file)}


def active_summaries() -> list[dict[str, object]]:
    runtime = read_runtime_status()
    cutoffs = latest_change_points()
    rows: list[dict[str, object]] = []
    for name, path in AUDIT_FILES.items():
        key = STRATEGY_KEYS.get(name, name.lower().replace(" ", "_"))
        if runtime.get(key, "ACTIVE") == "PAUSED":
            continue
        cutoff = parse_dt(cutoffs.get(key, {}).get("cutoff_ts", "1970-01-01T00:00:00+00:00"))
        all_rows = [row for row in latest_rows(path).values() if parse_dt(row_time_value(row)) >= cutoff]
        realized = [row for row in all_rows if is_realized(row)]
        stake = sum(fnum(row.get("stake")) for row in realized)
        pnl = sum(final_pnl_value(row) for row in realized)
        wins = [row for row in realized if final_pnl_value(row) > 0]
        losses = [row for row in realized if final_pnl_value(row) < 0]
        summary = {
            "strategy": name,
            "strategy_key": key,
            "total": len(all_rows),
            "realized": len(realized),
            "pending": len(all_rows) - len(realized),
            "wins": len(wins),
            "losses": len(losses),
            "stake": stake,
            "pnl": pnl,
            "roi": pnl / stake * 100 if stake else 0.0,
        }
        rows.append(summary)
    return rows


def summarize_rows(name: str, rows: list[dict[str, str]]) -> dict[str, object]:
    stake = sum(fnum(row.get("stake")) for row in rows)
    pnl = sum(final_pnl_value(row) for row in rows)
    wins = [row for row in rows if final_pnl_value(row) > 0]
    losses = [row for row in rows if final_pnl_value(row) < 0]
    roi = pnl / stake * 100 if stake else 0.0
    return {
        "cohort": name,
        "realized": len(rows),
        "wins": len(wins),
        "losses": len(losses),
        "stake": stake,
        "pnl": pnl,
        "roi": roi,
    }


def rows_since(path: Path, cutoff_ts: str) -> list[dict[str, str]]:
    cutoff = parse_dt(cutoff_ts)
    return [row for row in realized_rows(path) if parse_dt(row_time_value(row)) >= cutoff]


def cohort_summaries() -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for item in read_change_points():
        strategy_key = item.get("strategy") or ""
        label = item.get("label") or strategy_key
        cutoff = item.get("cutoff_ts") or ""
        strategy_name = next((name for name, key in STRATEGY_KEYS.items() if key == strategy_key), "")
        if not strategy_name and strategy_key in AUDIT_FILES:
            strategy_name = strategy_key
        if not strategy_name or not cutoff:
            continue
        rows = rows_since(AUDIT_FILES[strategy_name], cutoff)
        summary = summarize_rows(label, rows)
        summary["strategy"] = strategy_name
        summary["cutoff_ts"] = cutoff
        out.append(summary)
    return out


def wallet_rows(path: Path) -> list[dict[str, object]]:
    by_wallet: dict[str, dict[str, float]] = {}
    for row in realized_rows(path):
        wallet = wallet_value(row)
        item = by_wallet.setdefault(wallet, {"realized": 0, "wins": 0, "losses": 0, "stake": 0.0, "pnl": 0.0})
        pnl = final_pnl_value(row)
        item["realized"] += 1
        item["wins"] += 1 if pnl > 0 else 0
        item["losses"] += 1 if pnl < 0 else 0
        item["stake"] += fnum(row.get("stake"))
        item["pnl"] += pnl
    out: list[dict[str, object]] = []
    for wallet, item in by_wallet.items():
        stake = item["stake"]
        out.append(
            {
                "wallet": wallet,
                "realized": int(item["realized"]),
                "wins": int(item["wins"]),
                "losses": int(item["losses"]),
                "stake": stake,
                "pnl": item["pnl"],
                "roi": item["pnl"] / stake * 100 if stake else 0.0,
            }
        )
    return sorted(out, key=lambda row: float(row["pnl"]), reverse=True)


def render() -> str:
    lines = [
        "Realized PnL only",
        "- Only final WIN/LOSS rows are counted.",
        "- PnL uses slippage_final_pnl, not mark-to-market.",
        "- Pending rows are excluded from realized profit.",
        "",
        "| strategy | total | realized | pending | W/L | realized stake | realized pnl | realized ROI |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, path in AUDIT_FILES.items():
        item = summarize_file(name, path)
        lines.append(
            f"| {item['strategy']} | {item['total']} | {item['realized']} | {item['pending']} | "
            f"{item['wins']}/{item['losses']} | {item['stake']:.2f}U | {item['pnl']:.4f}U | {item['roi']:.2f}% |"
        )

    active = active_summaries()
    if active:
        active_stake = sum(float(item["stake"]) for item in active)
        active_pnl = sum(float(item["pnl"]) for item in active)
        active_realized = sum(int(item["realized"]) for item in active)
        active_roi = active_pnl / active_stake * 100 if active_stake else 0.0
        lines.extend(
            [
                "",
                "Current active-config realized summary",
                "- Excludes paused strategies and rows before each active strategy's latest change point.",
                f"- Active realized trades: {active_realized}",
                f"- Active realized stake: {active_stake:.2f}U",
                f"- Active realized PnL: {active_pnl:.4f}U",
                f"- Active realized ROI: {active_roi:.2f}%",
            ]
        )

    lines.extend(["", "Realized wallet breakdown", ""])
    for name, path in AUDIT_FILES.items():
        rows = wallet_rows(path)
        if not rows:
            lines.extend([f"{name}: no realized rows yet.", ""])
            continue
        lines.extend(
            [
                f"{name}",
                "| wallet | realized | W/L | stake | pnl | ROI |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in rows[:12]:
            lines.append(
                f"| {row['wallet']} | {row['realized']} | {row['wins']}/{row['losses']} | "
                f"{row['stake']:.2f}U | {row['pnl']:.4f}U | {row['roi']:.2f}% |"
            )
        lines.append("")
    cohorts = cohort_summaries()
    if cohorts:
        lines.extend(
            [
                "Post-change cohorts",
                "| cohort | strategy | cutoff | realized | W/L | stake | pnl | ROI |",
                "|---|---|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in cohorts:
            lines.append(
                f"| {row['cohort']} | {row['strategy']} | {row['cutoff_ts']} | {row['realized']} | "
                f"{row['wins']}/{row['losses']} | {row['stake']:.2f}U | {row['pnl']:.4f}U | {row['roi']:.2f}% |"
            )
        lines.append("")
    return "\n".join(lines)


def write_csv(path: Path = Path("realized_pnl_report.csv")) -> None:
    rows = [summarize_file(name, audit_path) for name, audit_path in AUDIT_FILES.items()]
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["strategy", "strategy_key", "total", "realized", "pending", "wins", "losses", "stake", "pnl", "roi"])
        writer.writeheader()
        writer.writerows(rows)


def write_active_csv(path: Path = Path("realized_active_pnl_report.csv")) -> None:
    rows = active_summaries()
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["strategy", "strategy_key", "total", "realized", "pending", "wins", "losses", "stake", "pnl", "roi"])
        writer.writeheader()
        writer.writerows(rows)


def write_cohort_csv(path: Path = Path("realized_cohort_report.csv")) -> None:
    rows = cohort_summaries()
    with path.open("w", encoding="utf-8", newline="") as file:
        fieldnames = ["cohort", "strategy", "cutoff_ts", "realized", "wins", "losses", "stake", "pnl", "roi"]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def write_equity_curve(path: Path = Path("realized_equity_curve.csv")) -> None:
    events: list[dict[str, object]] = []
    for strategy, audit_path in AUDIT_FILES.items():
        for row in realized_rows(audit_path):
            events.append(
                {
                    "ts": row_time_value(row),
                    "strategy": strategy,
                    "wallet": wallet_value(row),
                    "slug": row.get("slug") or "",
                    "pnl": final_pnl_value(row),
                    "stake": fnum(row.get("stake")),
                }
            )
    events.sort(key=lambda item: parse_dt(str(item.get("ts") or "")))
    total_equity = 0.0
    strategy_equity: dict[str, float] = {}
    wallet_equity: dict[str, float] = {}
    with path.open("w", encoding="utf-8", newline="") as file:
        fieldnames = ["ts", "strategy", "wallet", "slug", "stake", "pnl", "total_equity", "strategy_equity", "wallet_equity"]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for item in events:
            strategy = str(item["strategy"])
            wallet = str(item["wallet"])
            key = f"{strategy}:{wallet}"
            pnl = float(item["pnl"])
            total_equity += pnl
            strategy_equity[strategy] = strategy_equity.get(strategy, 0.0) + pnl
            wallet_equity[key] = wallet_equity.get(key, 0.0) + pnl
            writer.writerow(
                {
                    "ts": item["ts"],
                    "strategy": strategy,
                    "wallet": wallet,
                    "slug": item["slug"],
                    "stake": f"{float(item['stake']):.4f}",
                    "pnl": f"{pnl:.4f}",
                    "total_equity": f"{total_equity:.4f}",
                    "strategy_equity": f"{strategy_equity[strategy]:.4f}",
                    "wallet_equity": f"{wallet_equity[key]:.4f}",
                }
            )


def write_current_config_equity_curve(path: Path = Path("realized_current_config_equity_curve.csv")) -> None:
    cutoffs = latest_change_points()
    runtime = read_runtime_status()
    events: list[dict[str, object]] = []
    for strategy, audit_path in AUDIT_FILES.items():
        strategy_key = STRATEGY_KEYS.get(strategy, strategy.lower().replace(" ", "_"))
        cutoff = parse_dt(cutoffs.get(strategy_key, {}).get("cutoff_ts", "1970-01-01T00:00:00+00:00"))
        intended_state = runtime.get(strategy_key, "ACTIVE")
        for row in realized_rows(audit_path):
            ts = row_time_value(row)
            if parse_dt(ts) < cutoff:
                continue
            events.append(
                {
                    "ts": ts,
                    "strategy": strategy,
                    "strategy_key": strategy_key,
                    "intended_state": intended_state,
                    "wallet": wallet_value(row),
                    "slug": row.get("slug") or "",
                    "pnl": final_pnl_value(row),
                    "stake": fnum(row.get("stake")),
                }
            )
    events.sort(key=lambda item: parse_dt(str(item.get("ts") or "")))
    total_equity = 0.0
    active_equity = 0.0
    strategy_equity: dict[str, float] = {}
    with path.open("w", encoding="utf-8", newline="") as file:
        fieldnames = [
            "ts",
            "strategy",
            "strategy_key",
            "intended_state",
            "wallet",
            "slug",
            "stake",
            "pnl",
            "total_current_equity",
            "active_current_equity",
            "strategy_current_equity",
        ]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for item in events:
            strategy = str(item["strategy"])
            intended_state = str(item["intended_state"])
            pnl = float(item["pnl"])
            total_equity += pnl
            if intended_state != "PAUSED":
                active_equity += pnl
            strategy_equity[strategy] = strategy_equity.get(strategy, 0.0) + pnl
            writer.writerow(
                {
                    "ts": item["ts"],
                    "strategy": strategy,
                    "strategy_key": item["strategy_key"],
                    "intended_state": intended_state,
                    "wallet": item["wallet"],
                    "slug": item["slug"],
                    "stake": f"{float(item['stake']):.4f}",
                    "pnl": f"{pnl:.4f}",
                    "total_current_equity": f"{total_equity:.4f}",
                    "active_current_equity": f"{active_equity:.4f}",
                    "strategy_current_equity": f"{strategy_equity[strategy]:.4f}",
                }
            )


def main() -> int:
    text = render()
    Path("realized_pnl_report.md").write_text(text + "\n", encoding="utf-8")
    write_csv()
    write_active_csv()
    write_cohort_csv()
    write_equity_curve()
    write_current_config_equity_curve()
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
