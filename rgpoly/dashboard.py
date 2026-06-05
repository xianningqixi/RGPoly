from __future__ import annotations

import csv
import html
from pathlib import Path
from typing import Iterable

from .models import iso_utc
from .store import Store


def _table(headers: list[str], rows: Iterable[dict[str, object]]) -> str:
    head = "".join(f"<th>{html.escape(name)}</th>" for name in headers)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{html.escape(str(row.get(name, '')))}</td>" for name in headers)
        body_rows.append(f"<tr>{cells}</tr>")
    body = "\n".join(body_rows) or f"<tr><td colspan=\"{len(headers)}\">No rows</td></tr>"
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_html(store: Store) -> str:
    summary = store.summary()
    strategy_rows = [dict(row) for row in store.strategy_counts()]
    intents = [dict(row) for row in store.recent_rows("intents", 20)]
    signals = [dict(row) for row in store.recent_rows("signals", 20)]
    receipts = [dict(row) for row in store.recent_rows("receipts", 20)]
    activity = [dict(row) for row in store.recent_rows("activity", 20)]

    summary_cards = "\n".join(
        f"<div class=\"metric\"><span>{html.escape(key)}</span><strong>{html.escape(str(value))}</strong></div>"
        for key, value in summary.items()
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RGPoly v2 Dashboard</title>
  <style>
    body {{ margin: 0; font: 14px/1.45 system-ui, -apple-system, Segoe UI, sans-serif; color: #17202a; background: #f6f7f9; }}
    header {{ padding: 20px 24px; background: #102033; color: white; }}
    main {{ padding: 20px 24px 40px; }}
    h1 {{ margin: 0 0 4px; font-size: 24px; }}
    h2 {{ margin: 28px 0 10px; font-size: 17px; }}
    .muted {{ color: #6b7580; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; }}
    .metric {{ background: white; border: 1px solid #dce2e8; border-radius: 6px; padding: 12px; }}
    .metric span {{ display: block; color: #5d6875; font-size: 12px; }}
    .metric strong {{ display: block; font-size: 22px; margin-top: 4px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dce2e8; }}
    th, td {{ padding: 8px 10px; border-bottom: 1px solid #edf0f3; text-align: left; vertical-align: top; }}
    th {{ background: #eef2f6; font-size: 12px; text-transform: uppercase; color: #52606d; }}
    td {{ max-width: 420px; overflow-wrap: anywhere; }}
  </style>
</head>
<body>
  <header>
    <h1>RGPoly v2 Dashboard</h1>
    <div class="muted">Generated {html.escape(iso_utc())}</div>
  </header>
  <main>
    <section class="metrics">{summary_cards}</section>
    <h2>Strategy Counts</h2>
    {_table(["strategy", "signals", "approved", "rejected"], strategy_rows)}
    <h2>Ready / Recent Intents</h2>
    {_table(["id", "strategy", "status", "amount_usdc", "max_price", "outcome", "title", "created_at"], intents)}
    <h2>Recent Signals</h2>
    {_table(["id", "strategy", "status", "reason", "wallet_alias", "outcome", "source_price", "best_ask", "title", "created_at"], signals)}
    <h2>Recent Receipts</h2>
    {_table(["id", "intent_id", "status", "order_id", "spent_usdc", "error", "created_at"], receipts)}
    <h2>Recent Activity</h2>
    {_table(["key", "wallet_alias", "side", "outcome", "price", "usdc_size", "slug", "seen_at"], activity)}
  </main>
</body>
</html>
"""


def write_dashboard(store: Store, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(store), encoding="utf-8")


def export_table(store: Store, table: str, path: Path) -> None:
    rows = [dict(row) for row in store.recent_rows(table, 10_000)]
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

