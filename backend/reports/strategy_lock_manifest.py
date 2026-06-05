#!/usr/bin/env python3
"""Create a local strategy lock manifest.

The manifest records hashes for strategy and execution-simulation files so the
operator can verify that API credential setup did not silently change strategy
logic. It does not read secrets and never places orders.
"""

from __future__ import annotations

import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path.cwd()

LOCK_FILES = [
    "trade_audit.py",
    "live_order_preflight.py",
    "execution_intent_router.py",
    "execution_layer_status.py",
    "polymarket_deposit_wallet_readiness.py",
    "btc_directional_wallet_copy_sim.py",
    "weather_high_prob_wallet_copy_sim.py",
    "btc_directional_live_shadow_sim.py",
    "weather_high_prob_live_shadow_sim.py",
    "btc_no_dominant_candidate_copy_sim.py",
    "eth_directional_wallet_copy_sim.py",
    "bnb_directional_wallet_copy_sim.py",
    "strict_simulation_report.py",
    "pre_live_validation_report.py",
    "realized_pnl_report.py",
    "runtime_strategy_status.py",
    "runtime_parameter_health.py",
    "strategy_change_points.csv",
]

CSV_OUT = ROOT / "strategy_lock_manifest.csv"
MD_OUT = ROOT / "strategy_lock_manifest.md"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_rows() -> list[dict[str, str]]:
    locked_at = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, str]] = []
    for name in LOCK_FILES:
        path = ROOT / name
        rows.append(
            {
                "locked_at": locked_at,
                "file": name,
                "exists": "YES" if path.exists() else "NO",
                "sha256": sha256_file(path) if path.exists() else "",
                "bytes": str(path.stat().st_size) if path.exists() else "0",
            }
        )
    return rows


def write_csv(rows: list[dict[str, str]]) -> None:
    with CSV_OUT.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["locked_at", "file", "exists", "sha256", "bytes"])
        writer.writeheader()
        writer.writerows(rows)


def write_md(rows: list[dict[str, str]]) -> str:
    lines = [
        "# Strategy Lock Manifest",
        "",
        "Local manifest only. It records code hashes for strategy/preflight simulation files.",
        "It does not read API keys and does not place orders.",
        "",
        "| file | exists | sha256 | bytes |",
        "|---|---|---|---:|",
    ]
    for row in rows:
        lines.append(f"| {row['file']} | {row['exists']} | `{row['sha256']}` | {row['bytes']} |")
    text = "\n".join(lines)
    MD_OUT.write_text(text + "\n", encoding="utf-8")
    return text


def main() -> int:
    rows = build_rows()
    write_csv(rows)
    print(write_md(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
