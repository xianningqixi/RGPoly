#!/usr/bin/env python3
"""Repair audit CSV files to the current trade_audit schema.

Older audit files were created before the EV/price-bucket columns existed. If a
newer row is appended to an older header, CSV readers shift milestone/final
columns and realized ROI becomes unreliable. This script backs up each file and
rewrites rows under the current AUDIT_FIELDS order.
"""

from __future__ import annotations

import argparse
import csv
import shutil
from datetime import datetime, timezone
from pathlib import Path

from trade_audit import AUDIT_FIELDS


ROOT = Path(__file__).resolve().parent
DEFAULT_FILES = sorted(ROOT.glob("*_trade_audit.csv"))


def repair_file(path: Path, dry_run: bool = False) -> tuple[int, int, bool]:
    if not path.exists():
        return 0, 0, False
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.reader(file)
        header = next(reader, [])
        raw_rows = list(reader)

    repaired: list[dict[str, str]] = []
    changed = header != AUDIT_FIELDS
    for raw in raw_rows:
        if len(raw) == len(AUDIT_FIELDS):
            row = dict(zip(AUDIT_FIELDS, raw))
            if header != AUDIT_FIELDS:
                changed = True
        else:
            row = dict(zip(header, raw))
            if len(raw) != len(header):
                changed = True
        repaired.append({field: row.get(field, "") for field in AUDIT_FIELDS})

    if changed and not dry_run:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup = path.with_suffix(path.suffix + f".bak_schema_{stamp}")
        shutil.copy2(path, backup)
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=AUDIT_FIELDS)
            writer.writeheader()
            writer.writerows(repaired)
    return len(raw_rows), len(repaired), changed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("files", nargs="*", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    files = [ROOT / item if not item.is_absolute() else item for item in args.files] if args.files else DEFAULT_FILES
    for path in files:
        raw_count, repaired_count, changed = repair_file(path, dry_run=args.dry_run)
        status = "would_repair" if args.dry_run and changed else "repaired" if changed else "ok"
        print(f"{path.name}: {status} rows={raw_count}->{repaired_count}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
