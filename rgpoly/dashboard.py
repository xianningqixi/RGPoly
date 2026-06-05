from __future__ import annotations

import csv
import html
from pathlib import Path
from typing import Iterable

from .config import AppConfig, EXECUTION_MODES, ORDER_TYPES
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

MODE_LABELS = {
    "manual": "只监控",
    "dry_run": "模拟运行",
    "live": "实盘下单",
}


def _display_value(key: str, value: object) -> str:
    if key in {"status", "side"}:
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


def _command(text: str) -> str:
    return f"<pre class=\"command\"><code>{html.escape(text)}</code></pre>"


def _config_arg(config_path: Path | None) -> str:
    if not config_path:
        return r".\config\rgpoly.toml"
    text = str(config_path).replace("/", "\\")
    return r".\config\rgpoly.toml" if text.endswith(r"config\rgpoly.toml") else text


def _entry_card(title: str, badge: str, body: str, command: str | None = None, link: str | None = None) -> str:
    command_html = _command(command) if command else ""
    link_html = f"<a class=\"button\" href=\"{html.escape(link)}\">打开</a>" if link else ""
    return (
        "<article class=\"entry-card\">"
        f"<div class=\"entry-head\"><strong>{html.escape(title)}</strong><span>{html.escape(badge)}</span></div>"
        f"<p>{html.escape(body)}</p>"
        f"{link_html}{command_html}"
        "</article>"
    )


def _page(title: str, body: str, subtitle: str = "") -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ margin: 0; font: 14px/1.45 system-ui, -apple-system, Segoe UI, sans-serif; color: #17202a; background: #f6f7f9; }}
    header {{ padding: 20px 24px; background: #102033; color: white; }}
    main {{ padding: 20px 24px 40px; }}
    h1 {{ margin: 0 0 4px; font-size: 24px; }}
    h2 {{ margin: 28px 0 10px; font-size: 17px; }}
    h3 {{ margin: 18px 0 8px; font-size: 15px; }}
    .muted {{ color: #c8d2dc; }}
    .nav {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }}
    .nav a {{ color: white; border: 1px solid rgba(255,255,255,.35); border-radius: 6px; padding: 6px 10px; text-decoration: none; }}
    .notice {{ border: 1px solid #bed7ef; background: #eef7ff; color: #1c4b72; border-radius: 6px; padding: 10px 12px; margin: 12px 0; }}
    .error {{ border-color: #efb8b8; background: #fff1f1; color: #842828; }}
    .entry-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 10px; }}
    .entry-card, .form-section {{ background: white; border: 1px solid #dce2e8; border-radius: 6px; padding: 12px; min-width: 0; }}
    .entry-head {{ display: flex; align-items: center; justify-content: space-between; gap: 8px; }}
    .entry-head strong {{ font-size: 15px; }}
    .entry-head span {{ color: #3b617f; background: #eaf2f8; border-radius: 999px; padding: 2px 8px; font-size: 12px; white-space: nowrap; }}
    .entry-card p {{ margin: 8px 0; color: #4d5965; }}
    .button, button {{ display: inline-flex; align-items: center; justify-content: center; border: 1px solid #2b6d9f; background: #2b6d9f; color: white; border-radius: 6px; padding: 7px 12px; text-decoration: none; cursor: pointer; font: inherit; }}
    .button.secondary {{ background: white; color: #2b6d9f; }}
    .command {{ margin: 8px 0 0; padding: 9px; background: #101820; color: #edf6ff; border-radius: 6px; overflow-x: auto; white-space: pre-wrap; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; }}
    .metric {{ background: white; border: 1px solid #dce2e8; border-radius: 6px; padding: 12px; }}
    .metric span {{ display: block; color: #5d6875; font-size: 12px; }}
    .metric strong {{ display: block; font-size: 22px; margin-top: 4px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #dce2e8; }}
    th, td {{ padding: 8px 10px; border-bottom: 1px solid #edf0f3; text-align: left; vertical-align: top; }}
    th {{ background: #eef2f6; font-size: 12px; color: #52606d; }}
    td {{ max-width: 420px; overflow-wrap: anywhere; }}
    form {{ display: grid; gap: 12px; }}
    .form-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; }}
    label {{ display: grid; gap: 4px; color: #52606d; font-size: 12px; }}
    input, select, textarea {{ width: 100%; box-sizing: border-box; border: 1px solid #cdd7e1; border-radius: 6px; padding: 8px; font: 14px/1.35 Consolas, ui-monospace, monospace; background: white; color: #17202a; }}
    textarea {{ min-height: 84px; resize: vertical; }}
    .checkbox {{ display: flex; align-items: center; gap: 8px; font-size: 14px; color: #17202a; }}
    .checkbox input {{ width: auto; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 8px; position: sticky; bottom: 0; background: #f6f7f9; padding: 10px 0; }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(title)}</h1>
    <div class="muted">{html.escape(subtitle)}</div>
    <nav class="nav">
      <a href="/">控制台</a>
      <a href="/config">修改配置</a>
      <a href="/#summary">运行概览</a>
      <a href="/#orders">订单</a>
      <a href="/#signals">信号</a>
      <a href="/#receipts">回执</a>
      <a href="/#activity">钱包活动</a>
    </nav>
  </header>
  <main>{body}</main>
</body>
</html>
"""


def render_html(store: Store, config_path: Path | None = None, execution_mode: str = "") -> str:
    summary = store.summary()
    strategy_rows = [dict(row) for row in store.strategy_counts()]
    intents = [dict(row) for row in store.recent_rows("intents", 20)]
    signals = [dict(row) for row in store.recent_rows("signals", 20)]
    receipts = [dict(row) for row in store.recent_rows("receipts", 20)]
    activity = [dict(row) for row in store.recent_rows("activity", 20)]

    config_arg = _config_arg(config_path)
    mode_label = MODE_LABELS.get(execution_mode, execution_mode or "未知")
    subtitle = f"模式：{mode_label} · 配置：{config_arg} · 数据库：{store.path} · 更新时间：{iso_utc()}"

    summary_cards = "\n".join(
        f"<div class=\"metric\"><span>{html.escape(SUMMARY_LABELS.get(key, key))}</span><strong>{html.escape(str(value))}</strong></div>"
        for key, value in summary.items()
    )

    entry_cards = "\n".join(
        [
            _entry_card("修改配置", "页面编辑", f"打开配置页，直接改钱包、金额、价格上限和模式。", link="/config"),
            _entry_card(
                "模拟运行",
                "不花真钱",
                "先用 dry-run 看信号、拒绝原因和模拟回执。",
                f"python -m rgpoly --config {config_arg} run --dry-run",
            ),
            _entry_card(
                "实盘运行",
                "真钱下单",
                "设置实盘确认变量后再启动，建议保留每轮最多 1 单。",
                f'$env:RGPOLY_LIVE_ENABLED="I_UNDERSTAND_REAL_MONEY_RISK"\npython -m rgpoly --config {config_arg} run --live --execute-limit 1',
            ),
            _entry_card(
                "检查状态",
                "排障入口",
                "检查配置、数据库、策略数量、待执行订单和实盘环境。",
                f"python -m rgpoly --config {config_arg} doctor --live --check-client",
            ),
        ]
    )

    body = f"""
    <section id="entry">
      <h2>操作入口</h2>
      <div class="entry-grid">{entry_cards}</div>
    </section>
    <section id="summary">
      <h2>运行概览</h2>
      <div class="metrics">{summary_cards}</div>
    </section>
    <section id="strategies">
      <h2>策略统计</h2>
      {_table([("strategy", "策略"), ("signals", "信号数"), ("approved", "通过"), ("rejected", "拒绝")], strategy_rows)}
    </section>
    <section id="orders">
      <h2>待执行 / 最近订单</h2>
      {_table([("id", "订单ID"), ("strategy", "策略"), ("status", "状态"), ("amount_usdc", "金额USDC"), ("max_price", "最高价"), ("tick_size", "Tick"), ("neg_risk", "负风险"), ("outcome", "结果"), ("title", "市场标题"), ("created_at", "创建时间")], intents)}
    </section>
    <section id="signals">
      <h2>最近信号</h2>
      {_table([("id", "信号ID"), ("strategy", "策略"), ("status", "状态"), ("reason", "原因"), ("wallet_alias", "钱包别名"), ("outcome", "结果"), ("source_price", "来源价格"), ("best_ask", "卖一价"), ("title", "市场标题"), ("created_at", "创建时间")], signals)}
    </section>
    <section id="receipts">
      <h2>最近执行回执</h2>
      {_table([("id", "回执ID"), ("intent_id", "订单ID"), ("status", "状态"), ("order_id", "CLOB订单ID"), ("spent_usdc", "花费USDC"), ("error", "错误"), ("created_at", "创建时间")], receipts)}
    </section>
    <section id="activity">
      <h2>最近钱包活动</h2>
      {_table([("key", "活动ID"), ("wallet_alias", "钱包别名"), ("side", "方向"), ("outcome", "结果"), ("price", "价格"), ("usdc_size", "金额USDC"), ("slug", "市场Slug"), ("seen_at", "发现时间")], activity)}
    </section>
    """
    return _page("RGPoly 控制台", body, subtitle=subtitle)


def _select(name: str, label: str, options: tuple[str, ...], value: str) -> str:
    option_html = "".join(
        f"<option value=\"{html.escape(option)}\" {'selected' if option == value else ''}>{html.escape(option)}</option>"
        for option in options
    )
    return f"<label>{html.escape(label)}<select name=\"{html.escape(name)}\">{option_html}</select></label>"


def _input(name: str, label: str, value: object, input_type: str = "text", step: str = "") -> str:
    step_attr = f" step=\"{html.escape(step)}\"" if step else ""
    return (
        f"<label>{html.escape(label)}"
        f"<input name=\"{html.escape(name)}\" type=\"{html.escape(input_type)}\" value=\"{html.escape(str(value))}\"{step_attr}>"
        "</label>"
    )


def _checkbox(name: str, label: str, checked: bool) -> str:
    checked_attr = " checked" if checked else ""
    return (
        f"<label class=\"checkbox\"><input name=\"{html.escape(name)}\" type=\"checkbox\" value=\"1\"{checked_attr}>"
        f"{html.escape(label)}</label>"
    )


def _textarea(name: str, label: str, value: str, rows: int = 3) -> str:
    return f"<label>{html.escape(label)}<textarea name=\"{html.escape(name)}\" rows=\"{rows}\">{html.escape(value)}</textarea></label>"


def _csv(values: tuple[str, ...]) -> str:
    return ", ".join(values)


def _wallet_lines(wallets: dict[str, str]) -> str:
    return "\n".join(f"{alias} = {wallet}" for alias, wallet in wallets.items())


def render_config_html(
    config: AppConfig,
    config_path: Path,
    message: str = "",
    error: str = "",
) -> str:
    notice = f"<div class=\"notice\">{html.escape(message)}</div>" if message else ""
    error_html = f"<div class=\"notice error\">{html.escape(error)}</div>" if error else ""
    strategy_forms = []
    for idx, strategy in enumerate(config.wallet_copy):
        strategy_forms.append(
            f"""
            <section class="form-section">
              <h3>{html.escape(strategy.name)}</h3>
              <input type="hidden" name="strategy_{idx}_name" value="{html.escape(strategy.name)}">
              <div class="form-grid">
                {_checkbox(f"strategy_{idx}_enabled", "启用策略", strategy.enabled)}
                {_input(f"strategy_{idx}_stake_usdc", "每单金额 USDC", strategy.stake_usdc, "number", "0.01")}
                {_input(f"strategy_{idx}_min_entry_price", "最低入场价", strategy.min_entry_price, "number", "0.001")}
                {_input(f"strategy_{idx}_max_price", "最高接受价", strategy.max_price, "number", "0.001")}
                {_input(f"strategy_{idx}_max_source_to_ask_gap", "最大跟单价差", strategy.max_source_to_ask_gap, "number", "0.001")}
                {_input(f"strategy_{idx}_min_ask_depth_usdc", "最低卖盘深度 USDC", strategy.min_ask_depth_usdc, "number", "0.01")}
                {_input(f"strategy_{idx}_min_source_usdc", "来源最小金额 USDC", strategy.min_source_usdc, "number", "0.01")}
                {_input(f"strategy_{idx}_max_signal_age_sec", "信号最长有效秒数", strategy.max_signal_age_sec, "number", "1")}
              </div>
              <div class="form-grid">
                {_textarea(f"strategy_{idx}_required_title_keywords", "必须包含关键词，逗号分隔", _csv(strategy.required_title_keywords), 2)}
                {_textarea(f"strategy_{idx}_blocked_title_keywords", "屏蔽关键词，逗号分隔", _csv(strategy.blocked_title_keywords), 2)}
                {_textarea(f"strategy_{idx}_allowed_outcomes", "允许结果，逗号分隔", _csv(strategy.allowed_outcomes), 2)}
                {_textarea(f"strategy_{idx}_wallets", "钱包列表，每行 alias = 0x...", _wallet_lines(strategy.wallets), 5)}
              </div>
            </section>
            """
        )
    body = f"""
    {notice}
    {error_html}
    <div class="notice">保存会写入 {html.escape(str(config_path))}。如果交易进程已经在 run，需要重启交易进程才会使用新配置。私钥和 API key 不会保存在这里。</div>
    <form method="post" action="/config">
      <input type="hidden" name="strategy_count" value="{len(config.wallet_copy)}">
      <section class="form-section">
        <h2>运行配置</h2>
        <div class="form-grid">
          {_input("engine_db_path", "数据库路径", config.engine.db_path)}
          {_input("engine_poll_interval_ms", "轮询间隔毫秒", config.engine.poll_interval_ms, "number", "1")}
          {_input("engine_activity_limit", "每轮活动条数", config.engine.activity_limit, "number", "1")}
          {_input("engine_http_timeout_sec", "HTTP 超时秒数", config.engine.http_timeout_sec, "number", "0.1")}
        </div>
      </section>
      <section class="form-section">
        <h2>执行与风控</h2>
        <div class="form-grid">
          {_select("execution_mode", "执行模式", EXECUTION_MODES, config.execution.mode)}
          {_input("execution_execute_limit_per_loop", "每轮最多执行订单数", config.execution.execute_limit_per_loop, "number", "1")}
          {_input("execution_max_daily_usdc", "每日最大 USDC", config.execution.max_daily_usdc, "number", "0.01")}
          {_input("execution_max_open_intents", "最大待执行订单数", config.execution.max_open_intents, "number", "1")}
          {_input("execution_tick_size", "默认 Tick Size", config.execution.tick_size)}
          {_select("execution_order_type", "订单类型", ORDER_TYPES, config.execution.order_type)}
          {_checkbox("execution_default_neg_risk", "默认负风险市场", config.execution.default_neg_risk)}
        </div>
      </section>
      <h2>跟单策略</h2>
      {''.join(strategy_forms)}
      <div class="actions">
        <button type="submit">保存配置</button>
        <a class="button secondary" href="/">返回控制台</a>
      </div>
    </form>
    """
    return _page("修改 RGPoly 配置", body, subtitle=f"当前配置：{config_path}")


def write_dashboard(
    store: Store,
    path: Path,
    config_path: Path | None = None,
    execution_mode: str = "",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(store, config_path=config_path, execution_mode=execution_mode), encoding="utf-8")


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
