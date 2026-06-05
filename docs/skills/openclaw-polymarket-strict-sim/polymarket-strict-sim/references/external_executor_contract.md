# External Executor Contract

This project exposes a complete execution handoff layer without placing orders.

## Input

External executors consume:

- `execution_outbox.jsonl`
- `execution_outbox.csv`

Rows are created by:

```powershell
python .\execution_intent_router.py --once
```

Only `live_order_intents.csv` rows with `status=PREVIEW_ONLY_WOULD_PLACE` become tickets.

## JSONL Schema

Each line:

```json
{
  "schema_version": "polymarket.execution_intent.v1",
  "safety": {
    "does_not_place_order": true,
    "credential_required_by_this_script": false
  },
  "ticket": {
    "ticket_id": "ticket_...",
    "intent_id": "locked_live_preflight:...",
    "source_strategy": "btc_no_dominant_candidate_copy",
    "action": "BUY",
    "order_type": "FOK_MARKET_BUY_PREVIEW",
    "token_id": "...",
    "tick_size": "0.01",
    "neg_risk": "FALSE",
    "order_price_min": "0.010000",
    "order_price_max": "0.990000",
    "outcome": "No",
    "intended_stake_usdc": "10.0000",
    "sim_fill_price": "0.500000",
    "best_ask": "0.500000",
    "total_cost_usdc": "10.100000",
    "url": "https://polymarket.com/event/..."
  }
}
```

## Receipt File

If another system executes a ticket, write receipts to:

`external_execution_receipts.csv`

Use this header:

```csv
receipt_ts,ticket_id,intent_id,source_strategy,execution_status,actual_order_id,actual_fill_price,actual_shares,actual_spent_usdc,actual_fee_usdc,notes
```

`execution_layer_status.py` reads this file and reports receipt counts.

## Required Idempotency

An external executor must treat `ticket_id` or `intent_id` as an idempotency key. It must not submit more than one order for the same ticket unless the operator explicitly resets state.

## Order Options

Every external order builder must pass the ticket's `tick_size` and `neg_risk` values into the CLOB order options. If `sim_fill_price` or the executor's worst-price limit is outside `order_price_min` and `order_price_max`, skip the ticket instead of submitting it.

Deposit wallet accounts must also use the correct signature type and funder/proxy address for that wallet mode. API keys alone do not prove that the maker/funder address is onboarded or approved.

## Boundaries

The Codex/OpenClaw skill can generate and audit tickets. It does not call authenticated trading endpoints. If the operator uses a separate executor, that executor is outside this skill and must handle credentials, jurisdiction checks, balances, order submission, and cancellation policy.
