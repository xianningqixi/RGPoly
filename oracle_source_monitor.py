#!/usr/bin/env python3
"""Track Polymarket resolution-source metadata for simulated trades.

This does not trade. It reads local simulated trade CSV files, fetches matching
Gamma market metadata, extracts resolution-source clues, and writes a compact
CSV so strategy performance can be compared against the actual settlement source.
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


GAMMA_MARKETS = "https://gamma-api.polymarket.com/markets"


FIELDS = [
    "updated_at",
    "slug",
    "question",
    "category",
    "resolution_source",
    "source_url",
    "key_metric",
    "precision",
    "end_date",
    "description_excerpt",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def http_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Connection": "close"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=35) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            time.sleep(0.7 * (attempt + 1))
    raise last_error or RuntimeError(f"request failed: {url}")


def market_by_slug(slug: str) -> dict[str, Any] | None:
    if not slug:
        return None
    query = urllib.parse.urlencode({"slug": slug})
    data = http_json(f"{GAMMA_MARKETS}?{query}")
    if isinstance(data, list) and data:
        return data[0]
    return None


def read_existing(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as file:
        return {row["slug"]: row for row in csv.DictReader(file) if row.get("slug")}


def write_all(path: Path, rows: dict[str, dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for row in sorted(rows.values(), key=lambda item: item.get("slug", "")):
            writer.writerow({field: row.get(field, "") for field in FIELDS})


def slugs_from_csv(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out: set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            slug = row.get("slug") or row.get("event_slug")
            if slug:
                out.add(slug)
    return out


def classify(question: str, slug: str, description: str) -> str:
    text = f"{question} {slug} {description}".lower()
    if "bitcoin up or down" in text or "btc-updown" in text:
        return "btc_updown"
    if "highest temperature" in text or "lowest temperature" in text or "weather" in text:
        return "weather_temperature"
    return "other"


def first_url(text: str) -> str:
    match = re.search(r"https?://[^\s)]+", text)
    return match.group(0).rstrip(".,") if match else ""


def extract_resolution_source(market: dict[str, Any]) -> dict[str, str]:
    question = str(market.get("question") or "")
    slug = str(market.get("slug") or "")
    description = str(market.get("description") or "")
    explicit = str(market.get("resolutionSource") or "")
    category = classify(question, slug, description)

    source = explicit
    if not source:
        match = re.search(r"resolution source for this market (?:will be|is) information from ([^.,\n]+)", description, re.I)
        if match:
            source = match.group(1).strip()
    if not source and "chainlink" in description.lower():
        source = "Chainlink BTC/USD Data Stream"
    if not source and "hong kong observatory" in description.lower():
        source = "Hong Kong Observatory"

    metric = ""
    for pattern in [
        r"specifically the \"([^\"]+)\"",
        r"specifically the ([^.\n]+)",
        r"will resolve to .*? if ([^.\n]+)",
    ]:
        match = re.search(pattern, description, re.I)
        if match:
            metric = match.group(1).strip()
            break

    precision = ""
    match = re.search(r"measures temperatures in ([^.]+?)(?:\.| Thus|,)", description, re.I)
    if match:
        precision = match.group(1).strip()
    elif "data stream" in description.lower():
        precision = "Chainlink stream value at start/end timestamps"

    return {
        "updated_at": now_utc(),
        "slug": slug,
        "question": question,
        "category": category,
        "resolution_source": source,
        "source_url": first_url(description) or explicit,
        "key_metric": metric,
        "precision": precision,
        "end_date": str(market.get("endDate") or market.get("endDateIso") or ""),
        "description_excerpt": " ".join(description.split())[:700],
    }


def run_once(args: argparse.Namespace) -> int:
    slugs: set[str] = set()
    for source in args.sources:
        slugs |= slugs_from_csv(source)
    existing = read_existing(args.output)
    scanned = 0
    updated = 0
    for slug in sorted(slugs):
        if slug in existing and not args.refresh:
            continue
        market = market_by_slug(slug)
        if not market:
            continue
        existing[slug] = extract_resolution_source(market)
        scanned += 1
        updated += 1
        time.sleep(0.12)
    write_all(args.output, existing)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] oracle source scan | slugs {len(slugs)} | fetched {scanned} | updated {updated}", flush=True)
    return updated


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sources",
        type=Path,
        nargs="+",
        default=[
            Path("creamcream_copy_sim.csv"),
            Path("weather_wallet_copy_sim.csv"),
            Path("smart_wallet_copy_sim.csv"),
            Path("btc_signal_trades.csv"),
        ],
    )
    parser.add_argument("--output", type=Path, default=Path("oracle_source_map.csv"))
    parser.add_argument("--interval", type=float, default=600.0)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--once", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    while True:
        try:
            run_once(args)
        except KeyboardInterrupt:
            return 130
        except Exception as exc:
            print(f"oracle source scan error: {exc}", flush=True)
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
