# Live Execution Contract

## Execution Architecture

The preferred architecture is:

1. Simulator detects a wallet-copy signal.
2. Preflight validates freshness, market state, bid/ask, depth, slippage, fees, and strategy authorization.
3. Router writes a stable ticket to `execution_outbox.jsonl`.
4. External executor consumes the ticket and writes a receipt to `external_execution_receipts.csv`.
5. Monitoring separates external receipts from final-only PnL.

## Required Environment Variables

Direct executor scripts must read credentials only from environment variables:

- `PRIVATE_KEY`
- `POLY_API_KEY`
- `POLY_API_SECRET`
- `POLY_API_PASSPHRASE`
- `POLY_SIGNATURE_TYPE`
- `POLY_PROXY_ADDRESS`

Do not store these in code, CSV, JSON, Markdown, or the skill snapshot.

## Optional Direct Executor

`openclaw_outbox_executor.py` can consume `execution_outbox.jsonl`.

Dry-run:

```powershell
python .\openclaw_outbox_executor.py --dry-run
```

Operator-run execution:

```powershell
python .\openclaw_outbox_executor.py --execute --max-trades 1 --max-usdc 10
```

## Receipt Schema

External executors should append to `external_execution_receipts.csv`:

- `receipt_ts`
- `ticket_id`
- `intent_id`
- `source_strategy`
- `execution_status`
- `actual_order_id`
- `actual_fill_price`
- `actual_shares`
- `actual_spent_usdc`
- `actual_fee_usdc`
- `notes`

Allowed statuses include `EXECUTED`, `MARKET_CLOSED`, `EXCEPTION`, and `SKIPPED`.
