---
name: polymarket-strict-sim
description: Operate and migrate the local Polymarket strict simulation, wallet-copy, preflight, dashboard, and final-only PnL reporting system. Use for checking running scripts, preserving data, restarting hidden background simulators, reviewing strategy readiness, generating manual order intents, and migrating the project to another agent environment such as OpenClaw. This skill must not enable automatic real-money Polymarket order placement.
---

# Polymarket Strict Simulation

## Scope

Use this skill in the Polymarket workspace:

`C:\Users\Administrator\Documents\Codex\2026-05-20\polymarket`

Primary objective: keep the system as a strict live-like simulator, preflight engine, and execution handoff layer. It may discover signals, simulate fills, check CLOB orderbooks, generate manual/external execution tickets, report final-only PnL, and preserve migration data.

Do not add, run, or test automatic real-money order placement. API credentials, when present, are only for read-only readiness checks unless the user operates a separate system outside this skill.

## First Commands

Run these from the project root:

```powershell
python .\runtime_strategy_status.py
python .\current_config_report.py --once
python .\pre_live_validation_report.py
python .\strict_simulation_report.py
python .\api_key_readiness_check.py
python .\polymarket_deposit_wallet_readiness.py
python .\execution_intent_router.py --once
python .\execution_layer_status.py
python .\generate_dashboard.py
```

For a compact status:

```powershell
.\view_all_status.ps1
python .\summarize_bot_performance.py
```

## Active Model

- Simulators are hidden background processes, usually launched by `start_*_background.ps1`.
- Realized ROI uses only finalized rows and prefers `fee_adjusted_final_pnl`, then `slippage_final_pnl`.
- Pending or mark-to-market rows are diagnostics only.
- `live_order_preflight.py` outputs `live_order_intents.csv`; rows with `PREVIEW_ONLY_WOULD_PLACE` are manual execution candidates, not automatic orders.
- `execution_intent_router.py` converts fresh preflight passes into `execution_outbox.jsonl`, `execution_outbox.csv`, and `manual_order_tickets.md`.
- `polymarket_deposit_wallet_readiness.py` verifies signature type, funder/deposit wallet, CLOB collateral balance, and allowances without placing orders.
- External executors should consume the outbox and write receipts to `external_execution_receipts.csv`. See `references\external_executor_contract.md`.
- `pre_live_validation_report.py` has two profiles:
  - `STRICT / READY_FOR_MANUAL_REVIEW`: original strict gate.
  - `SMALL_STAKE / READY_FOR_SMALL_STAKE_REVIEW`: looser review gate.

## Current Important Strategies

- `btc_directional_copy`: main BTC wallet-copy simulation.
- `btc_no_dominant_candidate_copy`: BTC No-dominant wallet-copy simulation; currently allowed to reach small-stake review when data supports it.
- `eth_directional_copy`: ETH directional observation simulation.
- `bnb_directional_copy`: BNB directional observation simulation.
- `btc_directional_live_shadow`: 30U strict mirror shadow of BTC directional entries.
- `weather_high_prob_wallet_copy`: weather high-prob simulation; may be paused by runtime overrides.
- `weather_high_prob_live_shadow`: weather strict mirror shadow; may be paused by runtime overrides.
- `live_order_preflight`: strict preflight only; no private key and no order placement.
- `execution_intent_router`: routes preflight passes to manual/external execution outbox; no private key and no order placement.
- `dashboard_auto_refresh`: refreshes `dashboard.html`.

## Preserve Data

Before migration or major edits:

```powershell
.\openclaw_skill\polymarket-strict-sim\scripts\export_manifest.ps1
```

This writes:

`openclaw_skill\polymarket-strict-sim\assets\current_data_manifest.csv`

Use the manifest to verify audit files, reports, strategy files, and large data files are preserved.

For detailed migration notes, read `references\runbook.md`, `references\data_contract.md`, and `references\external_executor_contract.md`.
