# Data Contract

## Core Output Files

- `*_copy_sim.csv`: simulated trade rows.
- `*_trade_audit.csv`: strict audit rows with bid/ask/depth/slippage/final fields.
- `*_rejects.csv`: rejected signals and reason codes.
- `*_seen.json`: dedupe state.
- `latest_*_alert.txt`: operator-facing alert line.
- `realized_pnl_report.csv/md`: final-only realized PnL.
- `realized_equity_curve.csv`: final-only equity curve.
- `runtime_strategy_status.csv`: process/config status.
- `dashboard.html`: local visual dashboard.

## Execution Files

- `live_order_intents.csv`: live-like preflight output.
- `execution_outbox.jsonl`: external executor tickets.
- `execution_outbox.csv`: readable ticket table.
- `manual_order_tickets.md`: manual execution ticket view.
- `external_execution_receipts.csv`: external executor receipts.
- `lobster_execution_monitor.csv`: monitored external execution summary.

## Realized PnL Rules

Use final-only rows:

1. Prefer `fee_adjusted_final_pnl`.
2. Fallback to `slippage_final_pnl`.
3. Exclude `OPEN`, `PENDING`, and `MARK`.

Do not treat `pnl`, `current_price`, or mark-to-market values as landed profit.

## Important Strategy Files

- `btc_no_dominant_candidate_copy_sim.py`
- `btc_high_win_candidate_observation_copy_sim.py`
- `btc_yes_candidate_observation_copy_sim.py`
- `btc_directional_wallet_copy_sim.py`
- `weather_high_prob_wallet_copy_sim.py`
- `wallet_quality_engine.py`
- `btc_candidate_discovery_scheduler.py`
- `btc_candidate_pool_health.py`
- `generate_dashboard.py`
- `summarize_bot_performance.py`
- `execution_layer_status.py`
- `lobster_execution_monitor.py`
