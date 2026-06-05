#!/usr/bin/env python3
"""Watch CreamCream1215 public Polymarket activity.

Read-only watcher. It records new public activity for the account that appears
to specialize in Hong Kong weather markets.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WALLET = "0x01ced860d8dca5d7987579d2a2635df8520d27a2"
DATA_API = "https://data-api.polymarket.com/activity"


def http_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_recent(wallet: str, limit: int) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"user": wallet, "limit": limit, "offset": 0})
    data = http_json(f"{DATA_API}?{query}")
    return data if isinstance(data, list) else []


def key(row: dict[str, Any]) -> str:
    return f"{row.get('transactionHash')}:{row.get('asset')}:{row.get('side')}:{row.get('size')}"


def append_csv(path: Path, row: dict[str, Any]) -> None:
    exists = path.exists()
    fields = [
        "seen_at",
        "timestamp",
        "side",
        "outcome",
        "price",
        "size",
        "usdcSize",
        "title",
        "slug",
        "eventSlug",
        "tx",
    ]
    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "seen_at": datetime.now(timezone.utc).isoformat(),
                "timestamp": row.get("timestamp"),
                "side": row.get("side"),
                "outcome": row.get("outcome"),
                "price": row.get("price"),
                "size": row.get("size"),
                "usdcSize": row.get("usdcSize"),
                "title": row.get("title"),
                "slug": row.get("slug"),
                "eventSlug": row.get("eventSlug"),
                "tx": row.get("transactionHash"),
            }
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wallet", default=WALLET)
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--state", type=Path, default=Path("creamcream_seen.json"))
    parser.add_argument("--log", type=Path, default=Path("creamcream_activity.csv"))
    parser.add_argument("--alert-file", type=Path, default=Path("latest_creamcream_alert.txt"))
    return parser


def load_seen(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return set()


def save_seen(path: Path, seen: set[str]) -> None:
    path.write_text(json.dumps(sorted(seen)[-1000:], ensure_ascii=False), encoding="utf-8")


def main() -> int:
    args = build_parser().parse_args()
    seen = load_seen(args.state)
    initialized = bool(seen)
    while True:
        try:
            rows = fetch_recent(args.wallet, args.limit)
            new_rows = [row for row in reversed(rows) if key(row) not in seen]
            if not initialized:
                for row in rows:
                    seen.add(key(row))
                save_seen(args.state, seen)
                initialized = True
                print(
                    f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CreamCream watcher initialized with {len(rows)} recent rows",
                    flush=True,
                )
            else:
                for row in new_rows:
                    seen.add(key(row))
                    append_csv(args.log, row)
                    title = str(row.get("title") or "")
                    msg = (
                        f"CREAMCREAM ACTIVITY\n"
                        f"time: {datetime.now(timezone.utc).isoformat()}\n"
                        f"side: {row.get('side')} {row.get('outcome')}\n"
                        f"price: {row.get('price')}\n"
                        f"usdc: {row.get('usdcSize')}\n"
                        f"market: {title}\n"
                        f"url: https://polymarket.com/event/{row.get('eventSlug')}\n"
                    )
                    args.alert_file.write_text(msg, encoding="utf-8")
                    print(
                        f"账户跟踪：{row.get('side')} {row.get('outcome')} "
                        f"{row.get('usdcSize')}U @ {row.get('price')} | {title}",
                        flush=True,
                    )
                if new_rows:
                    save_seen(args.state, seen)
                print(
                    f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CreamCream扫描 | 新活动 {len(new_rows)} 条",
                    flush=True,
                )
        except KeyboardInterrupt:
            return 130
        except Exception as exc:
            print(f"CreamCream watcher error: {exc}", flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
