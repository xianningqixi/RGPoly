#!/usr/bin/env python3
"""Summarize simulated bot performance from local CSV logs."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from realized_pnl_report import render as render_realized_pnl


def fnum(value: str) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def latest_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            row_id = row.get("id") or row.get("slug") or row.get("question") or str(len(rows))
            rows[row_id] = row
    return rows


def summarize_btc(path: Path) -> str:
    rows = latest_rows(path)
    if not rows:
        return "BTC: no simulated trades yet."
    resolved = [row for row in rows.values() if row.get("status") == "RESOLVED"]
    open_rows = [row for row in rows.values() if row.get("status") == "OPEN"]
    wins = [row for row in resolved if row.get("result") == "WIN"]
    losses = [row for row in resolved if row.get("result") == "LOSS"]
    pnl = sum(fnum(row.get("pnl", "0")) for row in resolved)
    staked = sum(fnum(row.get("stake", "0")) for row in resolved)
    win_rate = len(wins) / len(resolved) * 100 if resolved else 0
    roi = pnl / staked * 100 if staked else 0
    return (
        "BTC simulated performance\n"
        f"- latest unique positions: {len(rows)}\n"
        f"- resolved: {len(resolved)}, open: {len(open_rows)}\n"
        f"- wins: {len(wins)}, losses: {len(losses)}, win_rate: {win_rate:.2f}%\n"
        f"- resolved stake: {staked:.2f}U, pnl: {pnl:.4f}U, roi_on_resolved_stake: {roi:.2f}%"
    )


def summarize_arb(path: Path) -> str:
    if not path.exists():
        return "Basket arb: no simulated trades yet."
    with path.open("r", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    expected = sum(fnum(row.get("expected_profit", "0")) for row in rows)
    return f"Basket arb simulated records\n- records: {len(rows)}\n- expected profit sum: {expected:.4f}U"


def summarize_cream(path: Path) -> str:
    if not path.exists():
        return "CreamCream watcher: no new activity records yet."
    with path.open("r", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    total = sum(fnum(row.get("usdcSize", "0")) for row in rows)
    return f"CreamCream watcher\n- new activity records: {len(rows)}\n- observed notional: {total:.4f}U"


def summarize_cream_copy(path: Path) -> str:
    rows = latest_rows(path)
    if not rows:
        return "CreamCream copy sim: no simulated copy trades yet."
    marked = [row for row in rows.values() if row.get("status") in {"MARK", "RESOLVED"}]
    open_rows = [row for row in rows.values() if row.get("status") == "OPEN"]
    pnl = sum(fnum(row.get("pnl", "0")) for row in marked)
    stake = sum(fnum(row.get("stake", "0")) for row in marked)
    roi = pnl / stake * 100 if stake else 0
    winners = [row for row in marked if fnum(row.get("pnl", "0")) > 0]
    return (
        "CreamCream copy sim\n"
        f"- latest unique simulated trades: {len(rows)}\n"
        f"- marked/resolved: {len(marked)}, open: {len(open_rows)}\n"
        f"- positive marks: {len(winners)}, pnl_mark_to_market: {pnl:.4f}U, roi_on_marked_stake: {roi:.2f}%"
    )


def summarize_smart_copy(path: Path) -> str:
    rows = latest_rows(path)
    if not rows:
        return "Smart wallet copy sim: no simulated copy trades yet."
    marked = [row for row in rows.values() if row.get("status") in {"MARK", "RESOLVED"}]
    open_rows = [row for row in rows.values() if row.get("status") == "OPEN"]
    pnl = sum(fnum(row.get("pnl", "0")) for row in marked)
    stake = sum(fnum(row.get("stake", "0")) for row in marked)
    roi = pnl / stake * 100 if stake else 0
    positive = [row for row in marked if fnum(row.get("pnl", "0")) > 0]
    return (
        "Smart wallet copy sim\n"
        f"- latest unique simulated trades: {len(rows)}\n"
        f"- marked/resolved: {len(marked)}, open: {len(open_rows)}\n"
        f"- positive marks: {len(positive)}, pnl_mark_to_market: {pnl:.4f}U, roi_on_marked_stake: {roi:.2f}%"
    )


def summarize_smart_direction_retest(path: Path) -> str:
    text = summarize_smart_copy(path)
    return text.replace("Smart wallet copy sim", "Smart direction retest sim", 1)


def summarize_btc_directional_copy(path: Path) -> str:
    rows = latest_rows(path)
    if not rows:
        return "BTC directional wallet copy sim: no simulated copy trades yet."
    marked = [row for row in rows.values() if row.get("status") in {"MARK", "RESOLVED"}]
    open_rows = [row for row in rows.values() if row.get("status") == "OPEN"]
    pnl = sum(fnum(row.get("pnl", "0")) for row in marked)
    stake = sum(fnum(row.get("stake", "0")) for row in marked)
    roi = pnl / stake * 100 if stake else 0
    positive = [row for row in marked if fnum(row.get("pnl", "0")) > 0]
    wallets: dict[str, int] = {}
    for row in rows.values():
        name = row.get("wallet_name") or "unknown"
        wallets[name] = wallets.get(name, 0) + 1
    wallet_text = ", ".join(f"{name}:{count}" for name, count in sorted(wallets.items()))
    return (
        "BTC directional wallet copy sim\n"
        f"- latest unique simulated trades: {len(rows)}\n"
        f"- by wallet: {wallet_text}\n"
        f"- marked/resolved: {len(marked)}, open: {len(open_rows)}\n"
        f"- positive marks: {len(positive)}, pnl_mark_to_market: {pnl:.4f}U, roi_on_marked_stake: {roi:.2f}%"
    )


def summarize_btc_directional_candidate_copy(path: Path) -> str:
    text = summarize_btc_directional_copy(path)
    return text.replace("BTC directional wallet copy sim", "BTC directional candidate wallet copy sim", 1)


def summarize_weather_wallet_copy(path: Path) -> str:
    rows = latest_rows(path)
    if not rows:
        return "Weather wallet copy sim: no simulated copy trades yet."
    marked = [row for row in rows.values() if row.get("status") in {"MARK", "RESOLVED"}]
    open_rows = [row for row in rows.values() if row.get("status") == "OPEN"]
    pnl = sum(fnum(row.get("pnl", "0")) for row in marked)
    stake = sum(fnum(row.get("stake", "0")) for row in marked)
    roi = pnl / stake * 100 if stake else 0
    positive = [row for row in marked if fnum(row.get("pnl", "0")) > 0]
    wallets: dict[str, int] = {}
    for row in rows.values():
        name = row.get("wallet_name") or "unknown"
        wallets[name] = wallets.get(name, 0) + 1
    wallet_text = ", ".join(f"{name}:{count}" for name, count in sorted(wallets.items()))
    return (
        "Weather wallet copy sim\n"
        f"- latest unique simulated trades: {len(rows)}\n"
        f"- by wallet: {wallet_text}\n"
        f"- marked/resolved: {len(marked)}, open: {len(open_rows)}\n"
        f"- positive marks: {len(positive)}, pnl_mark_to_market: {pnl:.4f}U, roi_on_marked_stake: {roi:.2f}%"
    )


def summarize_oracle_sources(path: Path) -> str:
    if not path.exists():
        return "Oracle source map: not built yet."
    with path.open("r", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    categories: dict[str, int] = {}
    sources: dict[str, int] = {}
    for row in rows:
        categories[row.get("category") or "unknown"] = categories.get(row.get("category") or "unknown", 0) + 1
        source = row.get("resolution_source") or "unknown"
        if len(source) > 80:
            source = source[:77] + "..."
        sources[source] = sources.get(source, 0) + 1
    cat_text = ", ".join(f"{name}:{count}" for name, count in sorted(categories.items()))
    top_sources = sorted(sources.items(), key=lambda item: item[1], reverse=True)[:4]
    source_text = "; ".join(f"{name}:{count}" for name, count in top_sources)
    return (
        "Oracle source map\n"
        f"- tracked markets: {len(rows)}\n"
        f"- categories: {cat_text}\n"
        f"- top sources: {source_text}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--btc", type=Path, default=Path("btc_signal_trades.csv"))
    parser.add_argument("--arb", type=Path, default=Path("dry_run_arb_log.csv"))
    parser.add_argument("--cream", type=Path, default=Path("creamcream_activity.csv"))
    parser.add_argument("--cream-copy", type=Path, default=Path("creamcream_copy_sim.csv"))
    parser.add_argument("--smart-copy", type=Path, default=Path("smart_wallet_copy_sim.csv"))
    parser.add_argument("--smart-direction-retest", type=Path, default=Path("smart_direction_retest_sim.csv"))
    parser.add_argument("--btc-directional-copy", type=Path, default=Path("btc_directional_wallet_copy_sim.csv"))
    parser.add_argument("--btc-directional-candidate-copy", type=Path, default=Path("btc_directional_candidate_copy_sim.csv"))
    parser.add_argument("--weather-wallet-copy", type=Path, default=Path("weather_wallet_copy_sim.csv"))
    parser.add_argument("--oracle-sources", type=Path, default=Path("oracle_source_map.csv"))
    args = parser.parse_args()
    print(render_realized_pnl())
    print()
    print(summarize_btc(args.btc))
    print()
    print(summarize_arb(args.arb))
    print()
    print(summarize_cream(args.cream))
    print()
    print(summarize_cream_copy(args.cream_copy))
    print()
    print(summarize_smart_copy(args.smart_copy))
    print()
    print(summarize_smart_direction_retest(args.smart_direction_retest))
    print()
    print(summarize_btc_directional_copy(args.btc_directional_copy))
    print()
    print(summarize_btc_directional_candidate_copy(args.btc_directional_candidate_copy))
    print()
    print(summarize_weather_wallet_copy(args.weather_wallet_copy))
    print()
    print(summarize_oracle_sources(args.oracle_sources))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
