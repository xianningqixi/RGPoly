#!/usr/bin/env python3
"""Check local API credential readiness without trading.

This script is intentionally read-only. It checks whether local environment
variables are present, whether the strategy code is locked, and whether the
current strict simulation/preflight reports exist. It never prints secrets,
never reads private keys, and never places orders.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent

REQUIRED_ENV = [
    "POLY_API_KEY",
    "POLY_API_SECRET",
    "POLY_API_PASSPHRASE",
]

OPTIONAL_ENV = [
    "POLY_PROXY_ADDRESS",
    "POLY_SIGNATURE_TYPE",
]

CSV_OUT = ROOT / "api_key_readiness_report.csv"
MD_OUT = ROOT / "api_key_readiness_report.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def env_status(name: str, required: bool) -> dict[str, str]:
    value = os.environ.get(name, "")
    source = "process"
    if not value and os.name == "nt":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value, _ = winreg.QueryValueEx(key, name)
                source = "windows_user"
        except Exception:
            value = ""
    return {
        "section": "env",
        "item": name,
        "status": "OK" if value else "MISSING_REQUIRED" if required else "MISSING_OPTIONAL",
        "detail": f"set:{source}" if value else "not set",
    }


def report_status(path: Path, label: str) -> dict[str, str]:
    return {
        "section": "file",
        "item": label,
        "status": "OK" if path.exists() else "MISSING",
        "detail": str(path.name),
    }


def strict_status() -> list[dict[str, str]]:
    rows = read_csv(ROOT / "strict_simulation_report.csv")
    if not rows:
        return [{"section": "strict_sim", "item": "strict_simulation_report", "status": "MISSING", "detail": "run strict_simulation_report.py"}]
    out = []
    for row in rows:
        strict_rows = fnum(row.get("strict_rows"))
        status = "OK_STRICT_ROWS_PRESENT" if strict_rows > 0 else "WAITING_FOR_NEW_STRICT_ROWS"
        out.append(
            {
                "section": "strict_sim",
                "item": row.get("strategy", ""),
                "status": status,
                "detail": f"strict_rows={row.get('strict_rows', '0')} legacy_rows={row.get('legacy_rows', '0')}",
            }
        )
    return out


def preflight_status() -> list[dict[str, str]]:
    rows = read_csv(ROOT / "live_order_intents.csv")
    if not rows:
        return [{"section": "preflight", "item": "live_order_intents", "status": "NO_ROWS", "detail": "waiting for active fresh shadow signals"}]
    passed = sum(1 for row in rows if row.get("status") == "PREVIEW_ONLY_WOULD_PLACE")
    stale = sum(1 for row in rows if row.get("reason") == "SOURCE_STALE")
    return [
        {
            "section": "preflight",
            "item": "live_order_intents",
            "status": "OK" if passed else "WAITING_FOR_FRESH_PASS",
            "detail": f"rows={len(rows)} passed={passed} source_stale={stale}",
        }
    ]


def build_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    rows.extend(env_status(name, True) for name in REQUIRED_ENV)
    rows.extend(env_status(name, False) for name in OPTIONAL_ENV)
    sig = next((row for row in rows if row["item"] == "POLY_SIGNATURE_TYPE"), {})
    proxy = next((row for row in rows if row["item"] == "POLY_PROXY_ADDRESS"), {})
    if sig.get("status") == "MISSING_OPTIONAL" or proxy.get("status") == "MISSING_OPTIONAL":
        rows.append(
            {
                "section": "execution_account",
                "item": "deposit_wallet_flow",
                "status": "CHECK_MANUALLY",
                "detail": "deposit wallet users normally need correct signature_type/funder plus Polymarket wallet onboarding/allowance before external execution",
            }
        )
    rows.append(report_status(ROOT / "strategy_lock_manifest.csv", "strategy_lock_manifest"))
    rows.append(report_status(ROOT / "strict_simulation_report.csv", "strict_simulation_report"))
    rows.append(report_status(ROOT / "pre_live_validation_report.csv", "pre_live_validation_report"))
    rows.extend(strict_status())
    rows.extend(preflight_status())
    return rows


def write_outputs(rows: list[dict[str, str]]) -> str:
    with CSV_OUT.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["section", "item", "status", "detail"])
        writer.writeheader()
        writer.writerows(rows)
    generated = datetime.now(timezone.utc).isoformat()
    lines = [
        "# API Key Readiness Report",
        "",
        f"Generated: {generated}",
        "",
        "Read-only check. This report never prints secrets and never places orders.",
        "",
        "| section | item | status | detail |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append(f"| {row['section']} | {row['item']} | {row['status']} | {row['detail']} |")
    text = "\n".join(lines)
    MD_OUT.write_text(text + "\n", encoding="utf-8")
    return text


def main() -> int:
    print(write_outputs(build_rows()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
