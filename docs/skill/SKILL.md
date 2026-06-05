---
name: polymarket-copytrading-full-stack
description: Operate, migrate, restore, and extend the local Polymarket wallet-copy trading system, including simulation, wallet discovery, final-only PnL reporting, dashboard refresh, preflight, execution outbox, OpenClaw handoff, and optional live CLOB executor integration when the operator supplies credentials and explicitly runs execution.
---

# Polymarket Copytrading Full Stack

## Scope

Use this skill for the Polymarket project originally located at:

`C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket`

The system includes:

- wallet discovery and candidate scoring
- BTC/ETH/SOL/BNB/weather wallet-copy simulations
- strict live-like fill, slippage, fee, depth, and signal-age checks
- final-only realized PnL reports
- dashboard generation and auto-refresh
- live-order preflight
- execution outbox/router
- OpenClaw/external executor receipt monitoring
- optional local CLOB executor scripts, disabled unless the operator supplies credentials and runs execution

Never embed private keys or API credentials in files. Use environment variables only.

## First Status Commands

From the project root:

```powershell
.\view_all_status.ps1
python .\summarize_bot_performance.py
python .\lobster_execution_monitor.py
python .\execution_layer_status.py
python .\runtime_strategy_status.py
```

Report simulation, external execution receipts, and redeem-confirmed/final-only PnL separately.

## Restore From Skill Snapshot

If the project snapshot is present in this skill:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:USERPROFILE\.codex\skills\polymarket-copytrading-full-stack\scripts\restore_project_snapshot.ps1" -Destination "C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket-restored"
```

Then `cd` into the restored directory and run the first status commands.

## Active Strategy Layers

Primary simulation and observation layers:

- `btc_no_dominant_candidate_copy`: strongest BTC No-dominant wallet-copy simulation.
- `btc_high_win_candidate_observation_copy`: 15-wallet Bitcoin Up/Down observation pool.
- `btc_yes_candidate_observation_copy`: YES-side BTC observation pool.
- `btc_directional_copy`: legacy BTC directional wallet-copy simulation.
- `weather_high_prob_wallet_copy`: weather high-prob wallet-copy simulation.
- `eth_directional_copy`, `sol_directional_copy`, `bnb_directional_copy`: asset directional observations.

Execution/handoff layers:

- `live_order_preflight.py`: checks whether simulated tickets would pass live-like execution filters.
- `execution_intent_router.py`: converts preflight pass rows into `execution_outbox.jsonl/csv` and `manual_order_tickets.md`.
- `openclaw_outbox_executor.py`: optional outbox-consuming CLOB executor; requires env vars and explicit `--execute`.
- `wallet_copy_executor.py`: older direct executor wrapper; default is dry-run.
- `external_execution_receipts.csv`: external executor receipts.
- `lobster_execution_monitor.py`: monitors OpenClaw/Dragon/Lobster receipts.

## Data Rules

- True realized performance uses only final rows.
- Prefer `fee_adjusted_final_pnl`, then `slippage_final_pnl`.
- Pending and mark-to-market rows are diagnostics only.
- Do not mix simulated PnL, external execution receipts, and redeem-confirmed/live-settled PnL.
- When evaluating a wallet, require enough final samples before promotion.

## Optional Live Executor Contract

The skill contains live-execution-capable scripts because the project needs a complete execution interface. They must remain inert unless the operator explicitly runs execution in their own environment.

Required environment variables for direct CLOB execution:

```powershell
$env:PRIVATE_KEY="..."
$env:POLY_API_KEY="..."
$env:POLY_API_SECRET="..."
$env:POLY_API_PASSPHRASE="..."
$env:POLY_SIGNATURE_TYPE="3"
$env:POLY_PROXY_ADDRESS="0x..."
```

Dry-run:

```powershell
python .\openclaw_outbox_executor.py --dry-run
```

Execution mode, operator-run only:

```powershell
python .\openclaw_outbox_executor.py --execute --max-trades 1 --max-usdc 10
```

Before any execution, check:

```powershell
python .\polymarket_deposit_wallet_readiness.py
python .\execution_layer_status.py
```

## References

Read only when needed:

- `references/runbook.md`: operational runbook.
- `references/data_contract.md`: important files and schemas.
- `references/live_execution_contract.md`: execution environment and handoff rules.
