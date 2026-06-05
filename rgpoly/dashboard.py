from __future__ import annotations

import csv
import html
from pathlib import Path
from typing import Iterable

from .models import iso_utc
from .store import Store


Column = tuple[str, str]


SUMMARY_LABELS = {
    "activity": "钱包活动",
    "signals": "信号总数",
    "signals_approved": "通过信号",
    "signals_rejected": "拒绝信号",
    "intents_ready": "待执行订单",
    "intents_dry_run": "模拟成交",
    "intents_executed": "实盘成交",
    "intents_failed": "失败订单",
    "receipts": "执行回执",
}

VALUE_LABELS = {
    "READY": "待执行",
    "DRY_RUN_FILLED": "模拟成交",
    "EXECUTED": "实盘成交",
    "FAILED": "失败",
    "CANCELLED": "已取消",
    "APPROVED": "通过",
    "REJECTED": "拒绝",
    "BUY": "买入",
    "SELL": "卖出",
}

REASON_LABELS = {
    "approved": "通过",
    "strategy_disabled": "策略已关闭",
    "not_trade_activity": "不是交易活动",
    "source_not_buy": "来源不是买入",
    "outcome_not_allowed": "结果不在允许范围",
    "source_size_too_small": "来源金额太小",
    "signal_too_old": "信号太旧",
    "keyword_missing": "缺少关键词",
    "keyword_blocked": "命中屏蔽关键词",
    "orderbook_missing": "缺少订单簿",
    "best_ask_missing": "缺少卖一价",
    "best_ask_below_min_entry": "卖一价低于最低入场价",
    "best_ask_above_max_price": "卖一价高于最高价",
    "ask_depth_too_thin": "卖盘深度不足",
    "source_to_ask_gap_too_wide": "跟单价差过大",
    "open_intent_limit": "待执行订单过多",
    "daily_usdc_limit": "触发每日金额上限",
}


def _display_value(key: str, value: object) -> str:
    if key == "status" or key == "side":
        return VALUE_LABELS.get(str(value), str(value))
    if key == "reason":
        return REASON_LABELS.get(str(value), str(value))
    if key == "neg_risk":
        return "是" if str(value) in {"1", "True", "true"} else "否"
    return str(value)


def _table(columns: list[Column], rows: Iterable[dict[str, object]]) -> str:
    head = "".join(f"<th>{html.escape(label)}</th>" for _, label in columns)
    body_rows = []
    for row in rows:
        cells = "".join(
            f"<td>{html.escape(_display_value(key, row.get(key, '')))}</td>"
            for key, _ in columns
        )
        body_rows.append(f"<tr>{cells}</tr>")
    body = "\n".join(body_rows) or f"<tr><td colspan=\"{len(columns)}\">暂无数据</td></tr>"
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_html(store: Store) -> str:
    summary = store.summary()
    strategy_rows = [dict(row) for row in store.strategy_counts()]
    intents = [dict(row) for row in store.recent_rows("intents", 20)]
    signals = [dict(row) for row in store.recent_rows("signals", 20)]
    receipts = [dict(row) for row in store.recent_rows("receipts", 20)]
    activity = [dict(row) for row in store.recent_rows("activity", 20)]

    summary_cards = "\n".join(
        f"<div class=\"metric\"><span>{html.escape(SUMMARY_LABELS.get(key, key))}</span><strong>{html.escape(str(value))}</strong></div>"
        for key, value in summary.items()
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RGPoly 控制台</title>
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
    <h1>RGPoly 控制台</h1>
    <div class="muted">生成时间：{html.escape(iso_utc())} · 数据库：{html.escape(str(store.path))}</div>
  </header>
  <main>
    <section class="metrics">{summary_cards}</section>
    <h2>策略统计</h2>
    {_table([("strategy", "策略"), ("signals", "信号数"), ("approved", "通过"), ("rejected", "拒绝")], strategy_rows)}
    <h2>待执行 / 最近订单</h2>
    {_table([("id", "订单ID"), ("strategy", "策略"), ("status", "状态"), ("amount_usdc", "金额USDC"), ("max_price", "最高价"), ("tick_size", "Tick"), ("neg_risk", "负风险"), ("outcome", "结果"), ("title", "市场标题"), ("created_at", "创建时间")], intents)}
    <h2>最近信号</h2>
    {_table([("id", "信号ID"), ("strategy", "策略"), ("status", "状态"), ("reason", "原因"), ("wallet_alias", "钱包别名"), ("outcome", "结果"), ("source_price", "来源价格"), ("best_ask", "卖一价"), ("title", "市场标题"), ("created_at", "创建时间")], signals)}
    <h2>最近执行回执</h2>
    {_table([("id", "回执ID"), ("intent_id", "订单ID"), ("status", "状态"), ("order_id", "CLOB订单ID"), ("spent_usdc", "花费USDC"), ("error", "错误"), ("created_at", "创建时间")], receipts)}
    <h2>最近钱包活动</h2>
    {_table([("key", "活动ID"), ("wallet_alias", "钱包别名"), ("side", "方向"), ("outcome", "结果"), ("price", "价格"), ("usdc_size", "金额USDC"), ("slug", "市场Slug"), ("seen_at", "发现时间")], activity)}
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
