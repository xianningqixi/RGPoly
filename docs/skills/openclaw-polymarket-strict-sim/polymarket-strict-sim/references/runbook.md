# Runbook

## Startup

From the project root, run active strategies with their existing scripts:

```powershell
.\start_auto_dry_run_background.ps1
.\start_creamcream_watcher_background.ps1
.\start_btc_candidate_discovery_scheduler.ps1
.\start_btc_directional_wallet_copy_background.ps1
.\start_eth_directional_wallet_copy_background.ps1
.\start_bnb_directional_wallet_copy_background.ps1
.\start_btc_no_dominant_candidate_copy_background.ps1
.\start_btc_directional_live_shadow_background.ps1
.\start_bond_style_scanner_background.ps1
.\start_oracle_source_monitor_background.ps1
.\start_dashboard_auto_refresh.ps1
.\start_live_order_preflight_background.ps1
.\start_execution_intent_router_background.ps1
```

Do not start paused strategies unless reviewing their runtime overrides first:

```powershell
Import-Csv .\runtime_strategy_overrides.csv | Sort-Object updated_at | Format-Table -AutoSize
python .\runtime_strategy_status.py
```

## Status

```powershell
.\view_all_status.ps1
python .\runtime_strategy_status.py
python .\current_config_report.py --once
python .\realized_pnl_report.py
python .\pre_live_validation_report.py
python .\strict_simulation_report.py
python .\polymarket_deposit_wallet_readiness.py
python .\execution_intent_router.py --once
python .\execution_layer_status.py
python .\generate_dashboard.py
```

Manual preflight candidates:

```powershell
Import-Csv .\live_order_intents.csv |
  Where-Object { $_.status -eq 'PREVIEW_ONLY_WOULD_PLACE' } |
  Select-Object ts,source_strategy,wallet_name,outcome,intended_stake_usdc,sim_fill_price,total_cost_usdc,slippage_bps,url |
  Format-Table -AutoSize
```

Execution handoff tickets:

```powershell
python .\execution_intent_router.py --once
Get-Content .\manual_order_tickets.md -Tail 80
python .\execution_layer_status.py
```

## Hidden Background Process Check

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*polymarket*' } |
  Select-Object ProcessId,Name,CommandLine
```

Prefer `pythonw.exe` or `Start-Process -WindowStyle Hidden` for long-running tasks.

## Migration To OpenClaw

1. Stop background processes only if the destination copy needs a stable snapshot.
2. Run the manifest exporter:

```powershell
.\openclaw_skill\polymarket-strict-sim\scripts\export_manifest.ps1
```

3. Copy the whole project directory to the target machine or OpenClaw workspace. Preserve CSV, JSON, MD, HTML, PY, and PS1 files.
4. Do not copy local secrets. Do not write API key values into files.
5. On the target, install Python dependencies used by the scripts. If a dependency is missing, run the failing script once and install only the missing package.
6. Run status/report commands before starting background scripts.
7. Start only active strategies from `runtime_strategy_status.py`.

## Decision Rules

- Final PnL is the only ROI source.
- Pending rows are not profit.
- `PREVIEW_ONLY_WOULD_PLACE` is a manual execution candidate.
- `execution_outbox.jsonl` is the external executor handoff file.
- `external_execution_receipts.csv` is the optional fill/receipt return file.
- `BLOCKED/SOURCE_STALE` means the source signal is too old for live-like execution.
- A paused strategy stays paused unless explicitly re-enabled in `runtime_strategy_overrides.csv` or by its start script policy.
