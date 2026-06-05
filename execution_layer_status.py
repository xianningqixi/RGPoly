#!/usr/bin/env python3
"""Report execution-layer handoff status.

Read-only. It summarizes preflight passes, outbox tickets, and optional external
execution receipts.
"""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from lobster_execution_monitor import normalize_receipt


ROOT = Path(__file__).resolve().parent


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def count_by(rows: list[dict[str, str]], *fields: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in rows:
        key = " | ".join(row.get(field, "") for field in fields)
        counter[key] += 1
    return counter


def main() -> int:
    intents = read_csv(ROOT / "live_order_intents.csv")
    outbox = read_csv(ROOT / "execution_outbox.csv")
    receipts = [normalize_receipt(row) for row in read_csv(ROOT / "external_execution_receipts.csv")]

    print("# Execution Layer Status")
    print("")
    print("Read-only handoff layer. It does not place orders.")
    print("")
    print(f"- preflight rows: {len(intents)}")
    print(f"- preflight pass rows: {sum(1 for row in intents if row.get('status') == 'PREVIEW_ONLY_WOULD_PLACE')}")
    print(f"- outbox tickets: {len(outbox)}")
    print(f"- external receipts: {len(receipts)}")
    print("")

    print("## Preflight Breakdown")
    for key, value in count_by(intents, "source_strategy", "status", "reason").most_common(12):
        print(f"- {value}: {key}")
    print("")

    print("## Outbox Breakdown")
    for key, value in count_by(outbox, "source_strategy", "status").most_common(12):
        print(f"- {value}: {key}")
    print("")

    if receipts:
        print("## Receipt Breakdown")
        for key, value in count_by(receipts, "source_strategy", "execution_status").most_common(12):
            print(f"- {value}: {key}")
    else:
        print("## Receipt Breakdown")
        print("- no external_execution_receipts.csv rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
