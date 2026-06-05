# Data Contract

## Core Files

- `*_trade_audit.csv`: authoritative strategy audit logs.
- `*_sim.csv`: simulated trade/open-event logs.
- `*_rejects.csv`: rejected candidate signals and reasons.
- `*_seen.json`: de-duplication state. Preserve these to avoid re-opening historical signals.
- `runtime_strategy_status.csv`: current runtime process/status report.
- `runtime_strategy_overrides.csv`: latest intended active/paused state.
- `strategy_change_points.csv`: cutoffs for current-configuration reporting.
- `live_order_intents.csv`: strict preflight output. Manual candidates have `status=PREVIEW_ONLY_WOULD_PLACE`.
- `execution_outbox.jsonl`: external/manual execution ticket stream generated from preflight passes.
- `execution_outbox.csv`: tabular execution tickets.
- `manual_order_tickets.md`: human-readable order cards.
- `external_execution_receipts.csv`: optional receipt/fill return file from a separate executor.
- `dashboard.html`: local dashboard snapshot.

## PnL Fields

Use this priority:

1. `fee_adjusted_final_pnl`
2. `slippage_final_pnl`
3. `final_pnl`

Only count rows with final status/result. Do not include pending rows, mark PnL, or unrealized values in ROI.

## Strict Execution Fields

Important live-like fields:

- `execution_source`
- `token_id`
- `fill_status`
- `spent_usdc`
- `unfilled_usdc`
- `levels_used`
- `fee_rate`
- `fee_usdc`
- `total_cost_usdc`
- `fee_adjusted_final_pnl`
- `would_live_fill`

Under strict simulation, a row should have realtime orderbook execution, token id, FULL fill, fee fields, and cost-adjusted final PnL.

## Sensitive Data

Do not store API secrets in project files. Exclude:

- `.env`
- raw private keys
- raw API key secrets
- temporary credential dumps

Read-only readiness checks may report whether variables are present, but must not print values.
