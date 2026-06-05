#!/usr/bin/env python3
"""Discover candidate Polymarket wallets for observation.

The default mode is local-only: it mines wallets already present in local logs
and reports them as candidate wallets. Optional --seed-wallet can fetch public
activity for additional wallets, but discovered wallets are still observation
candidates only and are not added to any live copy script.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FIELDS = [
    "wallet",
    "alias",
    "source",
    "market_type",
    "observed_volume",
    "trade_count",
    "first_seen",
    "last_seen",
    "notes",
]

LOCAL_SOURCES = [
    Path("creamcream_activity.csv"),
    Path("weather_wallet_copy_sim.csv"),
    Path("smart_wallet_copy_sim.csv"),
    Path("btc_directional_wallet_copy_sim.csv"),
]


def now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def fnum(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def classify_market(title: str, slug: str) -> str:
    text = f"{title} {slug}".lower()
    if "highest temperature" in text or "lowest temperature" in text or "weather" in text:
        return "weather"
    if "up or down" in text or "updown" in text:
        return "crypto_short_window"
    if "bitcoin" in text or "btc" in text:
        return "btc_directional"
    if "bond_style" in text:
        return "bond_style"
    return "other"


def wallet_from_row(row: dict[str, str]) -> tuple[str, str]:
    wallet = row.get("wallet") or row.get("wallet_address") or row.get("user") or ""
    alias = row.get("wallet_name") or row.get("alias") or row.get("name") or ""
    if not wallet and alias:
        wallet = alias
    if not alias and wallet:
        alias = wallet[:12]
    return wallet, alias


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def merge_candidate(
    candidates: dict[tuple[str, str], dict[str, Any]],
    *,
    wallet: str,
    alias: str,
    source: str,
    market_type: str,
    volume: float,
    seen_at: str,
    note: str,
) -> None:
    if not wallet:
        return
    key = (wallet, market_type)
    item = candidates.setdefault(
        key,
        {
            "wallet": wallet,
            "alias": alias or wallet[:12],
            "source": source,
            "market_type": market_type,
            "observed_volume": 0.0,
            "trade_count": 0,
            "first_seen": seen_at or now_text(),
            "last_seen": seen_at or now_text(),
            "notes": set(),
        },
    )
    item["observed_volume"] += volume
    item["trade_count"] += 1
    if seen_at:
        item["first_seen"] = min(str(item["first_seen"]), seen_at)
        item["last_seen"] = max(str(item["last_seen"]), seen_at)
    item["notes"].add(note)


def mine_local(candidates: dict[tuple[str, str], dict[str, Any]]) -> None:
    for path in LOCAL_SOURCES:
        for row in read_csv(path):
            wallet, alias = wallet_from_row(row)
            title = row.get("title") or row.get("question") or ""
            slug = row.get("slug") or row.get("event_slug") or ""
            market_type = classify_market(title, slug)
            volume = fnum(row.get("source_usdc") or row.get("usdcSize") or row.get("stake"))
            seen_at = row.get("ts") or row.get("seen_at") or row.get("source_timestamp") or ""
            merge_candidate(
                candidates,
                wallet=wallet,
                alias=alias,
                source=path.name,
                market_type=market_type,
                volume=volume,
                seen_at=seen_at,
                note="local_sim_or_activity",
            )


def http_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Connection": "close"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            time.sleep(0.5 * (attempt + 1))
    raise last_error or RuntimeError("request failed")


def fetch_activity(wallet: str, limit: int) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"user": wallet, "limit": limit, "offset": 0})
    data = http_json(f"https://data-api.polymarket.com/activity?{query}")
    return data if isinstance(data, list) else []


def mine_seed_wallets(candidates: dict[tuple[str, str], dict[str, Any]], wallets: list[str], limit: int) -> None:
    for wallet in wallets:
        rows = fetch_activity(wallet, limit)
        for row in rows:
            if row.get("type") != "TRADE":
                continue
            title = str(row.get("title") or "")
            slug = str(row.get("slug") or "")
            merge_candidate(
                candidates,
                wallet=wallet.lower(),
                alias=wallet[:12],
                source="data-api.polymarket.com/activity",
                market_type=classify_market(title, slug),
                volume=fnum(row.get("usdcSize")),
                seen_at=datetime.fromtimestamp(fnum(row.get("timestamp")), tz=timezone.utc).isoformat()
                if fnum(row.get("timestamp")) > 0
                else "",
                note="seed_wallet_public_activity",
            )
        time.sleep(0.2)


def load_bond_candidates(candidates: dict[tuple[str, str], dict[str, Any]], path: Path) -> None:
    for row in read_csv(path):
        pseudo_wallet = f"bond:{row.get('category') or 'unknown'}"
        merge_candidate(
            candidates,
            wallet=pseudo_wallet,
            alias=pseudo_wallet,
            source=path.name,
            market_type="bond_style",
            volume=fnum(row.get("ask_depth_usdc")),
            seen_at=row.get("ts") or "",
            note=f"candidate_market:{row.get('slug')}",
        )


def write_report(candidates: dict[tuple[str, str], dict[str, Any]], output: Path) -> list[dict[str, Any]]:
    rows = sorted(candidates.values(), key=lambda row: (str(row["market_type"]), -float(row["observed_volume"])))
    with output.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["observed_volume"] = f"{fnum(out.get('observed_volume')):.6f}"
            out["notes"] = "; ".join(sorted(out.get("notes") or []))
            writer.writerow({field: out.get(field, "") for field in FIELDS})
    return rows


def render(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Candidate Wallets",
        "",
        "Observation candidates only. No wallet is automatically added to a copy script.",
        "",
        "| market_type | alias | wallet | trades | observed_volume | source | notes |",
        "|---|---|---|---:|---:|---|---|",
    ]
    for row in rows[:80]:
        notes = "; ".join(sorted(row.get("notes") or []))
        notes = re.sub(r"\|", "/", notes)
        lines.append(
            f"| {row['market_type']} | {row['alias']} | {row['wallet']} | {row['trade_count']} | "
            f"{fnum(row['observed_volume']):.2f} | {row['source']} | {notes[:120]} |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run one discovery pass and exit")
    parser.add_argument("--seed-wallet", action="append", default=[], help="Optional wallet address to fetch public activity from")
    parser.add_argument("--seed-limit", type=int, default=100)
    parser.add_argument("--output", type=Path, default=Path("candidate_wallets.csv"))
    parser.add_argument("--bond-candidates", type=Path, default=Path("bond_style_candidates.csv"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    mine_local(candidates)
    if args.bond_candidates.exists():
        load_bond_candidates(candidates, args.bond_candidates)
    if args.seed_wallet:
        mine_seed_wallets(candidates, args.seed_wallet, args.seed_limit)
    rows = write_report(candidates, args.output)
    text = render(rows)
    Path("candidate_wallets.md").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
